"""Vision LLM clients — Qwen3-VL (cloud) and DeepSeek multi-agent synthesis."""
from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

from src.config import get_config
from src.utils import extract_json_payload


class VisionLLMClient(ABC):
    model_name: str

    @abstractmethod
    def analyze_images(
        self,
        images: list[str],
        patient_summary: str,
        modality: str,
        task: str = "clinical_and_medication",
    ) -> dict[str, Any]:
        raise NotImplementedError


class OpenAIVisionClient(VisionLLMClient):
    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_name = model
        self.timeout = timeout

    def _encode_image(self, path: str) -> dict[str, Any]:
        p = Path(path)
        data = base64.b64encode(p.read_bytes()).decode("ascii")
        suffix = p.suffix.lower().lstrip(".")
        mime = "jpeg" if suffix in {"jpg", "jpeg"} else "png" if suffix == "png" else "jpeg"
        return {
            "type": "image_url",
            "image_url": {"url": f"data:image/{mime};base64,{data}"},
        }

    def analyze_images(
        self,
        images: list[str],
        patient_summary: str,
        modality: str,
        task: str = "clinical_and_medication",
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"你是临床影像与用药专家。模态：{modality}。\n"
                    f"病历摘要：{patient_summary}\n\n"
                    "请结合影像（含分割 overlay 如有）输出 JSON：\n"
                    "{"
                    '"clinical_analysis","imaging_findings","medication_recommendation",'
                    '"recommended_drugs":[{"name","dose","route","indication"}],'
                    '"allergies","diagnoses","symptoms","chief_complaint",'
                    '"anesthesia_surgery","reasoning","risk_level"'
                    "}"
                ),
            }
        ]
        for img in images[:12]:
            if Path(img).exists():
                content.append(self._encode_image(img))

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是 MedSafe 临床视觉分析助手，仅输出 JSON。"},
                {"role": "user", "content": content},
            ],
            "temperature": 0.1,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
        parsed = extract_json_payload(raw)
        return parsed if isinstance(parsed, dict) else {"clinical_analysis": raw, "reasoning": raw}


class MockVisionClient(VisionLLMClient):
    model_name = "mock-qwen-vl"

    def analyze_images(
        self,
        images: list[str],
        patient_summary: str,
        modality: str,
        task: str = "clinical_and_medication",
    ) -> dict[str, Any]:
        return {
            "clinical_analysis": f"基于{modality}影像与病历，患者存在需进一步评估的临床发现（mock）。{patient_summary[:200]}",
            "imaging_findings": f"已分析 {len(images)} 张视觉图（含截图/overlay）。未见 mock 明确急症征象。",
            "medication_recommendation": "建议按指南进行保守用药，待实验室结果回报后调整。",
            "recommended_drugs": [{"name": "对乙酰氨基酚", "dose": "500mg", "route": "PO", "indication": "镇痛"}],
            "allergies": [],
            "diagnoses": ["待确认"],
            "symptoms": [],
            "chief_complaint": patient_summary[:80] if patient_summary else "",
            "anesthesia_surgery": "当前未进入明确手术麻醉流程。",
            "reasoning": "Mock VLM：串行分割结果已与视觉图一并审阅。",
            "risk_level": "medium",
        }


class DeepSeekSynthesisClient:
    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_name = model
        self.timeout = timeout

    def synthesize_report(
        self,
        clinical_text: str,
        vlm_analysis: dict,
        agent_opinions: list[dict],
        arbitration: dict,
        rule_output: dict,
        chain_hint: str = "",
    ) -> dict[str, Any]:
        system = (
            "你是 DeepSeek 临床多智能体会诊主席。"
            "整合视觉分析、规则引擎与各专家意见，生成结构化用药安全报告段落。"
            "输出 JSON，包含：clinical_analysis, imaging_findings, medication_recommendation, "
            "pharmacy_assessment, allergy_analysis, anesthesia_surgery, risk_summary, chain_of_thought。"
            "chain_of_thought 需展示逐步推理链。"
        )
        user = json.dumps(
            {
                "clinical_text": clinical_text,
                "vlm_analysis": vlm_analysis,
                "agent_opinions": agent_opinions,
                "arbitration": arbitration,
                "rule_output": rule_output,
                "chain_hint": chain_hint,
            },
            ensure_ascii=False,
        )
        if not self.api_key:
            return self._mock_synthesis(vlm_analysis, agent_opinions, arbitration, chain_hint)

        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
        parsed = extract_json_payload(raw)
        return parsed if isinstance(parsed, dict) else {"risk_summary": raw, "chain_of_thought": raw}

    @staticmethod
    def _mock_synthesis(vlm: dict, opinions: list[dict], arbitration: dict, chain_hint: str) -> dict[str, Any]:
        return {
            "clinical_analysis": vlm.get("clinical_analysis", ""),
            "imaging_findings": vlm.get("imaging_findings", ""),
            "medication_recommendation": vlm.get("medication_recommendation", ""),
            "pharmacy_assessment": next((o.get("summary", "") for o in opinions if o.get("agent_id") == "clinical_pharmacist"), ""),
            "allergy_analysis": next((o.get("summary", "") for o in opinions if o.get("agent_id") == "allergy_specialist"), ""),
            "anesthesia_surgery": vlm.get("anesthesia_surgery", ""),
            "risk_summary": arbitration.get("final_recommendation", ""),
            "chain_of_thought": chain_hint or "Mock DeepSeek：规则 evidence 优先 → 视觉发现 → 各专家意见 → 共识结论。",
        }


class MockDeepSeekClient(DeepSeekSynthesisClient):
    model_name = "mock-deepseek"

    def __init__(self) -> None:
        super().__init__(api_key="", base_url="", model="mock-deepseek")

    def synthesize_report(self, **kwargs: Any) -> dict[str, Any]:
        return self._mock_synthesis(
            kwargs.get("vlm_analysis", {}),
            kwargs.get("agent_opinions", []),
            kwargs.get("arbitration", {}),
            kwargs.get("chain_hint", ""),
        )


def get_qwen_vlm_client() -> VisionLLMClient:
    cfg = get_config().get("vision_llm", {})
    api_key = cfg.get("api_key") or os.getenv("MEDSAFE_VISION_LLM__API_KEY", "")
    provider = cfg.get("provider", "mock").lower()
    if provider == "mock" or not api_key:
        return MockVisionClient()
    return OpenAIVisionClient(
        api_key=api_key,
        base_url=cfg.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        model=cfg.get("model", "qwen-vl-max-latest"),
        timeout=float(cfg.get("timeout", 120)),
    )


def get_deepseek_client() -> DeepSeekSynthesisClient:
    cfg = get_config().get("deepseek_llm", {})
    api_key = cfg.get("api_key") or os.getenv("MEDSAFE_DEEPSEEK__API_KEY", "")
    if not api_key:
        return MockDeepSeekClient()
    return DeepSeekSynthesisClient(
        api_key=api_key,
        base_url=cfg.get("base_url", "https://api.deepseek.com/v1"),
        model=cfg.get("model", "deepseek-chat"),
        timeout=float(cfg.get("timeout", 120)),
    )
