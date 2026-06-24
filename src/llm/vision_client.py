"""Vision LLM clients — Qwen3-VL (cloud) and DeepSeek multi-agent synthesis. No mock."""
from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from src.config import get_config
from src.llm.errors import LLMNotConfiguredError, VisionLLMError
from src.utils import coerce_llm_str_list, extract_json_payload
from src.imaging.volume_io import is_vlm_compatible_image


BAILIAN_CONSOLE_URL = "https://bailian.console.aliyun.com/cn-beijing"
BAILIAN_VL_DOC_URL = "https://help.aliyun.com/zh/model-studio/qwen-vl-compatible-with-openai"


def _normalize_vlm_analysis(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    for key in ("allergies", "symptoms", "diagnoses"):
        if key in out:
            out[key] = coerce_llm_str_list(out.get(key))
    return out


_REGION_ALIASES: dict[str, str] = {
    "cn-beijing": "cn-beijing",
    "beijing": "cn-beijing",
    "华北2": "cn-beijing",
    "ap-southeast-1": "ap-southeast-1",
    "singapore": "ap-southeast-1",
    "新加坡": "ap-southeast-1",
    "ap-northeast-1": "ap-northeast-1",
    "tokyo": "ap-northeast-1",
    "东京": "ap-northeast-1",
    "eu-central-1": "eu-central-1",
    "frankfurt": "eu-central-1",
    "us": "us",
    "virginia": "us",
}


def resolve_bailian_vision_base_url(cfg: dict[str, Any] | None = None) -> str:
    """Resolve OpenAI-compatible base URL for 百炼 (Model Studio) Qwen-VL."""
    cfg = cfg or get_config().get("vision_llm", {})
    explicit = str(
        cfg.get("base_url") or os.getenv("MEDSAFE_VISION_LLM__BASE_URL", "") or ""
    ).strip()
    workspace_id = str(
        cfg.get("workspace_id") or os.getenv("MEDSAFE_VISION_LLM__WORKSPACE_ID", "") or ""
    ).strip()
    region = str(
        cfg.get("region") or os.getenv("MEDSAFE_VISION_LLM__REGION", "cn-beijing") or "cn-beijing"
    ).strip().lower()
    region_key = _REGION_ALIASES.get(region, region)

    if explicit and "{WorkspaceId}" not in explicit and "{workspace_id}" not in explicit:
        return explicit.rstrip("/")

    if workspace_id:
        if region_key == "us":
            return "https://dashscope-us.aliyuncs.com/compatible-mode/v1"
        return f"https://{workspace_id}.{region_key}.maas.aliyuncs.com/compatible-mode/v1"

    if explicit:
        return explicit.replace("{WorkspaceId}", workspace_id).replace("{workspace_id}", workspace_id).rstrip("/")

    return "https://dashscope.aliyuncs.com/compatible-mode/v1"


def get_vision_llm_settings() -> dict[str, Any]:
    cfg = get_config().get("vision_llm", {})
    api_key = str(cfg.get("api_key") or os.getenv("MEDSAFE_VISION_LLM__API_KEY", "") or "")
    model = str(cfg.get("model") or os.getenv("MEDSAFE_VISION_LLM__MODEL", "qwen3-vl-plus") or "qwen3-vl-plus")
    workspace_id = str(
        cfg.get("workspace_id") or os.getenv("MEDSAFE_VISION_LLM__WORKSPACE_ID", "") or ""
    ).strip()
    region = str(
        cfg.get("region") or os.getenv("MEDSAFE_VISION_LLM__REGION", "cn-beijing") or "cn-beijing"
    )
    base_url = resolve_bailian_vision_base_url(cfg)
    return {
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
        "workspace_id": workspace_id,
        "region": region,
        "timeout": float(cfg.get("timeout", 120)),
    }


def _validate_bailian_vision_config(api_key: str, base_url: str, workspace_id: str) -> None:
    uses_legacy = "dashscope.aliyuncs.com" in base_url and "maas.aliyuncs.com" not in base_url
    is_bailian_key = api_key.startswith("sk-ws-")
    if is_bailian_key and (uses_legacy or not workspace_id):
        raise LLMNotConfiguredError(
            "Qwen VLM",
            hint=(
                "检测到百炼业务空间 Key（sk-ws-…），需配置业务空间 ID 与百炼域名。"
                f"在 {BAILIAN_CONSOLE_URL} 打开「业务空间」复制空间 ID，"
                "设置 MEDSAFE_VISION_LLM__WORKSPACE_ID，并将 base_url 留空或设为 "
                "https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1。"
                f"文档：{BAILIAN_VL_DOC_URL}"
            ),
        )
    if uses_legacy and not workspace_id:
        raise LLMNotConfiguredError(
            "Qwen VLM",
            hint=(
                "通义千问已迁移至阿里云百炼，旧 dashscope.aliyuncs.com 域名可能返回 403。"
                f"请在 {BAILIAN_CONSOLE_URL} 获取 API Key 与业务空间 ID，"
                "设置 MEDSAFE_VISION_LLM__WORKSPACE_ID 与 region=cn-beijing（base_url 可留空自动拼接）。"
            ),
        )


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


def _upstream_error_detail(response: httpx.Response | None) -> str:
    if response is None:
        return ""
    try:
        data = response.json()
    except Exception:
        text = (response.text or "").strip()
        return text[:500] if text else f"HTTP {response.status_code}"
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("code")
            if msg:
                return str(msg)
        for key in ("message", "detail", "msg"):
            if data.get(key):
                return str(data[key])
    return f"HTTP {response.status_code}"


def _raise_vision_upstream_error(exc: Exception, *, model: str) -> None:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else None
        detail = _upstream_error_detail(exc.response)
        if status in {401, 403}:
            hint = (
                "请确认已在百炼控制台开通视觉模型，且 base_url / workspace_id / model 与 Key 地域一致。"
                f"控制台：{BAILIAN_CONSOLE_URL} ；文档：{BAILIAN_VL_DOC_URL}"
            )
        elif status == 429:
            hint = "百炼请求频率或配额已达上限，请稍后重试或升级套餐。"
        elif detail and "illegal" in detail.lower():
            hint = (
                "提交的图片格式无效（可能混入了 NIfTI 体数据或非 PNG/JPEG 文件）。"
                "请仅勾选分割 overlay，或在 2D 切片模式下勾选原图；3D MPR 请用截图。"
            )
        else:
            hint = "请检查百炼服务状态、模型名称与网络连接。"
        raise VisionLLMError("Qwen VLM", detail, status_code=status, hint=hint) from exc
    if isinstance(exc, httpx.RequestError):
        raise VisionLLMError(
            "Qwen VLM",
            str(exc) or "网络请求失败",
            hint="请确认可访问百炼 maas.aliyuncs.com 域名，或增大 vision_llm.timeout。",
        ) from exc
    raise VisionLLMError("Qwen VLM", str(exc)) from exc


class OpenAIVisionClient(VisionLLMClient):
    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_name = model
        self.timeout = timeout

    def _encode_image(self, path: str) -> dict[str, Any]:
        p = Path(path)
        if not p.is_file():
            raise VisionLLMError("Qwen VLM", f"影像文件不存在：{path}")
        try:
            with Image.open(p) as img:
                img.load()
                fmt = (img.format or "PNG").upper()
        except Exception as exc:
            raise VisionLLMError(
                "Qwen VLM",
                f"无法读取影像文件 {p.name}：{exc}",
                hint="请确认 overlay 为有效的 PNG/JPEG，3D 体数据需先分割生成 overlay。",
            ) from exc
        mime_map = {"JPEG": "jpeg", "PNG": "png", "WEBP": "webp", "BMP": "bmp", "GIF": "gif"}
        mime = mime_map.get(fmt, "png")
        data = base64.b64encode(p.read_bytes()).decode("ascii")
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
            if is_vlm_compatible_image(img):
                content.append(self._encode_image(img))

        if len(content) <= 1:
            raise VisionLLMError(
                "Qwen VLM",
                "未找到可读取的影像文件",
                hint="请确认 overlay 路径存在且为 PNG/JPEG。",
            )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是 MedSafe 临床视觉分析助手，仅输出 JSON。"},
                {"role": "user", "content": content},
            ],
            "temperature": 0.1,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                resp.raise_for_status()
                raw = resp.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            _raise_vision_upstream_error(exc, model=self.model)
        parsed = extract_json_payload(raw)
        if isinstance(parsed, dict):
            return _normalize_vlm_analysis(parsed)
        return {"clinical_analysis": raw, "reasoning": raw}


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
    settings = get_vision_llm_settings()
    api_key = settings["api_key"]
    provider = str(cfg.get("provider", "")).lower()
    if provider == "mock":
        raise LLMNotConfiguredError(
            "Qwen VLM",
            hint="config.yaml vision_llm.provider 不能为 mock。请设为 qwen 并配置 api_key。",
        )
    if not api_key:
        raise LLMNotConfiguredError(
            "Qwen VLM",
            hint=f"设置 MEDSAFE_VISION_LLM__API_KEY（百炼控制台 {BAILIAN_CONSOLE_URL}）。",
        )
    _validate_bailian_vision_config(api_key, settings["base_url"], settings["workspace_id"])
    return OpenAIVisionClient(
        api_key=api_key,
        base_url=settings["base_url"],
        model=settings["model"],
        timeout=settings["timeout"],
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
