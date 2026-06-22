"""Vision LLM clients — Qwen3-VL (cloud) and DeepSeek multi-agent synthesis. No mock."""
from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

from src.config import get_config
from src.llm.errors import LLMNotConfiguredError
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


def get_qwen_vlm_client() -> VisionLLMClient:
    cfg = get_config().get("vision_llm", {})
    api_key = cfg.get("api_key") or os.getenv("MEDSAFE_VISION_LLM__API_KEY", "")
    provider = str(cfg.get("provider", "")).lower()
    if provider == "mock":
        raise LLMNotConfiguredError(
            "Qwen VLM",
            hint="config.yaml vision_llm.provider 不能为 mock。请设为 qwen 并配置 api_key。",
        )
    if not api_key:
        raise LLMNotConfiguredError(
            "Qwen VLM",
            hint="设置 MEDSAFE_VISION_LLM__API_KEY 或 config.yaml vision_llm.api_key。",
        )
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
        raise LLMNotConfiguredError(
            "DeepSeek report synthesis",
            hint="设置 MEDSAFE_DEEPSEEK__API_KEY 或 config.yaml deepseek_llm.api_key。",
        )
    return DeepSeekSynthesisClient(
        api_key=api_key,
        base_url=cfg.get("base_url", "https://api.deepseek.com/v1"),
        model=cfg.get("model", "deepseek-chat"),
        timeout=float(cfg.get("timeout", 120)),
    )


def is_vision_llm_configured() -> bool:
    try:
        get_qwen_vlm_client()
        return True
    except LLMNotConfiguredError:
        return False
