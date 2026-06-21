"""LLM API client — OpenAI-compatible + offline mock for CI/demo."""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from src.config import get_config
from src.utils import extract_json_payload


class LLMClient(ABC):
    @abstractmethod
    def chat(self, system: str, user: str, temperature: float = 0.0) -> str:
        raise NotImplementedError

    def chat_json(self, system: str, user: str, temperature: float = 0.0) -> dict[str, Any] | None:
        raw = self.chat(system, user, temperature=temperature)
        parsed = extract_json_payload(raw)
        return parsed if isinstance(parsed, dict) else None


class OpenAICompatibleClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(self, system: str, user: str, temperature: float = 0.0) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"].strip()


class MockLLMClient(LLMClient):
    """Deterministic offline client for integration tests and demo without API key."""

    def chat(self, system: str, user: str, temperature: float = 0.0) -> str:
        if "结构化抽取" in system or "抽取以下字段" in system:
            return json.dumps(self._mock_extract(user), ensure_ascii=False)
        if "临床药师" in system:
            return json.dumps(self._mock_pharmacist(user), ensure_ascii=False)
        if "内科主治" in system:
            return json.dumps(self._mock_attending(user), ensure_ascii=False)
        if "过敏" in system:
            return json.dumps(self._mock_allergy(user), ensure_ascii=False)
        if "药房" in system or "库存" in system:
            return json.dumps(self._mock_pharmacy(user), ensure_ascii=False)
        if "专科" in system:
            return json.dumps(self._mock_specialist(user), ensure_ascii=False)
        if "会诊主席" in system or "仲裁" in system:
            return json.dumps(self._mock_chief(user), ensure_ascii=False)
        if "对抗审查" in system or "Critic" in system:
            return json.dumps(self._mock_critic(user), ensure_ascii=False)
        if "会诊主持人" in system or "Moderator" in system:
            return json.dumps(self._mock_moderator(user), ensure_ascii=False)
        if "追问" in system or "信息协调" in system:
            return json.dumps(self._mock_coordinator(user), ensure_ascii=False)
        return json.dumps({"summary": "mock response", "risk_level": "unknown"}, ensure_ascii=False)

    def _context_blob(self, user: str) -> str:
        return user.lower()

    def _has(self, user: str, *tokens: str) -> bool:
        blob = self._context_blob(user)
        return any(token.lower() in blob for token in tokens)

    def _mock_extract(self, user: str) -> dict[str, Any]:
        age_match = re.search(r"年龄[：: ]?(\d+)", user)
        gender = "unknown"
        if re.search(r"性别[：: ]?[mM男]", user):
            gender = "M"
        elif re.search(r"性别[：: ]?[fF女]", user):
            gender = "F"

        meds = []
        for drug in ["warfarin", "aspirin", "metoprolol", "ibuprofen", "amoxicillin", "lisinopril"]:
            if drug in user.lower() or drug in user:
                meds.append(drug)

        allergies: list[str] = []
        if "penicillin" in user.lower() or "青霉素" in user:
            allergies.append("penicillin rash")

        pregnancy = "unknown"
        if "怀孕" in user or "pregnant" in user.lower():
            pregnancy = "pregnant"

        missing = []
        if not allergies and self._has(user, "amoxicillin", "阿莫西林"):
            missing.append("allergies")
        if gender == "F" and pregnancy == "unknown" and self._has(user, "lisinopril", "赖诺普利"):
            missing.append("pregnancy_status")

        return {
            "age": int(age_match.group(1)) if age_match else None,
            "gender": gender,
            "pregnancy_status": pregnancy,
            "allergies": allergies,
            "symptoms_or_complaints": ["胸痛", "呼吸困难"] if "胸痛" in user else [],
            "diagnoses": ["高血压", "冠心病"] if "高血压" in user else [],
            "current_medications": meds,
            "missing_fields": missing,
        }

    def _risk_from_evidence(self, user: str) -> tuple[str, bool, list[str]]:
        reasons: list[str] = []
        block = False
        risk = "none"
        if self._has(user, "warfarin", "ibuprofen", "ddi_warfarin"):
            risk, block = "high", True
            reasons.append("华法林与 NSAIDs 联用出血风险显著升高。")
        elif self._has(user, "penicillin", "amoxicillin", "allergy"):
            risk, block = "high", True
            reasons.append("存在青霉素过敏史，阿莫西林存在交叉过敏风险。")
        elif self._has(user, "pregnancy_status", "lisinopril", "unknown"):
            risk, block = "unknown", True
            reasons.append("妊娠状态未知，ACEI 类需先确认。")
        elif self._has(user, "allergies", "missing"):
            risk, block = "unknown", True
            reasons.append("过敏史缺失，无法排除禁忌。")
        return risk, block, reasons

    def _mock_pharmacist(self, user: str) -> dict[str, Any]:
        risk, block, reasons = self._risk_from_evidence(user)
        conf = 0.92 if block else 0.78
        if "修订轮次" in user or "Critic" in user:
            conf = min(0.95, conf + 0.05)
        return {
            "risk_level": risk,
            "block_decision": block,
            "reasons": reasons or ["从药学角度未发现明确高风险相互作用。"],
            "alternatives": ["对乙酰氨基酚"] if self._has(user, "ibuprofen") else [],
            "need_clarification": risk == "unknown",
            "clarification_targets": ["allergies", "pregnancy_status"] if risk == "unknown" else [],
            "confidence": conf,
            "evidence_cited": ["ddi_warfarin_ibuprofen_bleeding"] if self._has(user, "warfarin", "ibuprofen") else [],
            "summary": "临床药师审查完成。",
        }

    def _mock_attending(self, user: str) -> dict[str, Any]:
        risk, block, reasons = self._risk_from_evidence(user)
        if self._has(user, "lisinopril") and self._has(user, "pregnancy"):
            reasons = ["ACEI 禁用于妊娠患者。"]
            risk, block = "high", True
        conf = 0.88 if block else 0.72
        if "修订轮次" in user:
            conf = min(0.93, conf + 0.06)
        return {
            "risk_level": risk,
            "block_decision": block,
            "reasons": reasons or ["适应证与当前诊断基本匹配。"],
            "alternatives": ["调整降压方案"] if self._has(user, "lisinopril") else [],
            "need_clarification": "unknown" in user or risk == "unknown",
            "clarification_targets": ["pregnancy_status"] if self._has(user, "lisinopril") else [],
            "confidence": conf,
            "evidence_cited": [],
            "summary": "内科主治审查完成。",
        }

    def _mock_allergy(self, user: str) -> dict[str, Any]:
        if self._has(user, "penicillin", "allergy", "过敏"):
            return {
                "risk_level": "high",
                "block_decision": True,
                "reasons": ["青霉素过敏与阿莫西林存在交叉过敏风险。"],
                "alternatives": ["阿奇霉素", "多西环素"],
                "need_clarification": False,
                "clarification_targets": [],
                "confidence": 0.95,
                "evidence_cited": ["allergy_penicillin_amoxicillin"],
                "summary": "过敏专员建议阻断阿莫西林。",
            }
        if self._has(user, "allergies", "missing") or ("allergies" in user and "[]" in user):
            return {
                "risk_level": "unknown",
                "block_decision": True,
                "reasons": ["过敏史缺失，无法安全评估。"],
                "alternatives": [],
                "need_clarification": True,
                "clarification_targets": ["allergies"],
                "confidence": 0.88,
                "evidence_cited": [],
                "summary": "需先补充过敏史。",
            }
        return {
            "risk_level": "none",
            "block_decision": False,
            "reasons": ["未发现明确过敏禁忌。"],
            "alternatives": [],
            "need_clarification": False,
            "clarification_targets": [],
            "confidence": 0.8,
            "evidence_cited": [],
            "summary": "过敏审查通过。",
        }

    def _mock_pharmacy(self, user: str) -> dict[str, Any]:
        oos = self._has(user, "clarithromycin", "克拉霉素")
        alts = ["azithromycin"] if oos else []
        return {
            "risk_level": "low" if oos else "none",
            "block_decision": False,
            "reasons": ["克拉霉素当前缺货，需替代。"] if oos else ["候选药物库存充足。"],
            "alternatives": alts,
            "need_clarification": False,
            "clarification_targets": [],
            "confidence": 0.92,
            "evidence_cited": [],
            "summary": "药房库管确认可调配。" if not oos else "建议更换为阿奇霉素。",
        }

    def _mock_specialist(self, user: str) -> dict[str, Any]:
        if self._has(user, "lisinopril", "pregnancy", "unknown", "female", "f"):
            return {
                "risk_level": "unknown",
                "block_decision": True,
                "reasons": ["育龄女性使用 ACEI 前必须确认妊娠状态。"],
                "alternatives": ["甲基多巴", "拉贝洛尔（若确认妊娠）"],
                "need_clarification": True,
                "clarification_targets": ["pregnancy_status"],
                "confidence": 0.9,
                "evidence_cited": ["contraindication_pregnancy_acei"],
                "summary": "专科建议先确认妊娠状态。",
            }
        return {
            "risk_level": "none",
            "block_decision": False,
            "reasons": ["专科未发现额外禁忌。"],
            "alternatives": [],
            "need_clarification": False,
            "clarification_targets": [],
            "confidence": 0.7,
            "evidence_cited": [],
            "summary": "专科审查无额外风险。",
        }

    def _mock_chief(self, user: str) -> dict[str, Any]:
        risk, block, reasons = self._risk_from_evidence(user)
        return {
            "consensus_risk_level": risk,
            "consensus_block_decision": block,
            "final_recommendation": reasons[0] if reasons else "各专家意见一致，可继续标准审查流程。",
            "arbitration_notes": "规则 evidence 优先；辩论汇总后临床药师与过敏专员意见一致时采用阻断策略。",
            "conflict_detected": "block_split" in user or "分歧" in user,
        }

    def _mock_critic(self, user: str) -> dict[str, Any]:
        risk, block, _ = self._risk_from_evidence(user)
        block_split = "block_split" in user and "true" in user.lower()
        low_conf = "low_confidence_agents" in user and "[" in user and "]" not in user.split("low_confidence_agents")[-1][:5]
        round_num = 1
        if '"round":' in user:
            import re
            m = re.search(r'"round":\s*(\d+)', user)
            if m:
                round_num = int(m.group(1))
        consensus = not block_split and risk != "unknown" and round_num >= 2
        dissent: list[str] = []
        if block_split or self._has(user, "warfarin", "ibuprofen"):
            dissent.append("临床药师与药房对阻断优先级存在分歧")
        if risk == "unknown":
            dissent.append("关键字段缺失导致风险等级无法统一")
        return {
            "round_number": round_num,
            "ehr_contradictions": [],
            "evidence_gaps": ["规则 evidence 需在各 Agent 意见中显式引用"] if round_num == 1 else [],
            "safety_misses": [],
            "overall_assessment": "Critic：第二轮起趋向共识。" if round_num >= 2 else "Critic：首轮存在分歧，需修订。",
            "consensus_reached": consensus,
            "dissent_log": dissent,
            "low_confidence_agents": [] if round_num >= 2 else ["internal_medicine"],
            "min_confidence": 0.88 if round_num >= 2 else 0.72,
        }

    def _mock_moderator(self, user: str) -> dict[str, Any]:
        risk, block, reasons = self._risk_from_evidence(user)
        return {
            "consistency_notes": ["临床药师与过敏专员均支持阻断"] if block else ["多数专家允许继续评估"],
            "conflict_notes": ["内科主治置信度偏低"] if not block else [],
            "integration_summary": reasons[0] if reasons else "主持人：各轮辩论已汇总。",
            "recommended_risk_level": risk,
            "recommended_block": block,
            "majority_block_votes": 3 if block else 1,
            "total_agents": 4,
        }

    def _mock_coordinator(self, user: str) -> dict[str, Any]:
        if "unable_to_answer" in user or '"unable_to_answer": true' in user.lower():
            return {
                "status": "conservative_fallback",
                "questions": [],
                "priority_missing_fields": [],
                "conservative_advice": {
                    "summary": "关键信息无法补充，建议暂缓用药并人工复核。",
                    "actions": ["暂缓候选药物", "补充过敏史与妊娠状态后重新审查"],
                    "disclaimer": "本结果为保守策略，不能替代正式医疗决策。",
                },
                "final_message": "已切换为保守降级方案。",
            }
        targets = []
        if "allergies" in user:
            targets.append("allergies")
        if "pregnancy_status" in user:
            targets.append("pregnancy_status")
        questions = [
            {
                "field": t,
                "question": f"请补充 {t} 相关信息。",
                "reason": "该字段缺失影响安全审查。",
                "priority": "high",
            }
            for t in targets[:3]
        ]
        return {
            "status": "need_user_input" if questions else "complete",
            "questions": questions,
            "priority_missing_fields": targets,
            "conservative_advice": None,
            "final_message": "请补充关键信息后继续审查。",
        }


def get_llm_client() -> LLMClient:
    cfg = get_config()
    llm_cfg = cfg.get("llm", {})
    provider = llm_cfg.get("provider", "mock").lower()
    api_key = llm_cfg.get("api_key") or os.getenv("MEDSAFE_LLM_API_KEY", "")

    if provider == "mock" or not api_key:
        return MockLLMClient()

    return OpenAICompatibleClient(
        api_key=api_key,
        base_url=llm_cfg.get("base_url", "https://api.openai.com/v1"),
        model=llm_cfg.get("model", "gpt-4o-mini"),
        timeout=float(llm_cfg.get("timeout", 60)),
    )
