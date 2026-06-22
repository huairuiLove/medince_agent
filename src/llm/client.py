"""LLM API client — OpenAI-compatible only; no mock / fake responses."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import httpx

from src.config import get_config
from src.llm.errors import LLMNotConfiguredError
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


def get_llm_client() -> LLMClient:
    cfg = get_config()
    llm_cfg = cfg.get("llm", {})
    provider = str(llm_cfg.get("provider", "")).lower()
    api_key = llm_cfg.get("api_key") or os.getenv("MEDSAFE_LLM_API_KEY", "")

    if provider == "mock":
        raise LLMNotConfiguredError(
            "Multi-agent LLM",
            hint="config.yaml llm.provider 不能为 mock。请设为 openai / deepseek / qwen 并配置 api_key。",
        )
    if not api_key:
        raise LLMNotConfiguredError(
            "Multi-agent LLM",
            hint="设置 MEDSAFE_LLM__API_KEY 或 config.yaml llm.api_key。",
        )

    return OpenAICompatibleClient(
        api_key=api_key,
        base_url=llm_cfg.get("base_url", "https://api.openai.com/v1"),
        model=llm_cfg.get("model", "gpt-4o-mini"),
        timeout=float(llm_cfg.get("timeout", 60)),
    )


def is_llm_configured() -> bool:
    try:
        get_llm_client()
        return True
    except LLMNotConfiguredError:
        return False
