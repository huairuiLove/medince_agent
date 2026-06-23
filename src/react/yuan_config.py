"""Chat agent configuration — bridges MedSafe config.yaml to ReAct/MCP stack."""
from __future__ import annotations

import os
from pathlib import Path

from src.config import load_config, resolve_path
from src.llm.embedding_client import resolve_embedding_config


class ChatConfig:
    """Unified config for ReAct chat + Graph RAG + MCP tools."""

    def __init__(self) -> None:
        cfg = load_config()
        chat = cfg.get("chat", {})
        llm = cfg.get("llm", {})
        deepseek = cfg.get("deepseek_llm", {})
        emb = resolve_embedding_config()

        self.provider: str = chat.get("provider") or llm.get("provider") or "deepseek"
        self.api_key: str = (
            chat.get("api_key")
            or deepseek.get("api_key")
            or llm.get("api_key")
            or os.getenv("DEEPSEEK_API_KEY", "")
        )
        self.base_url: str = (
            chat.get("base_url")
            or deepseek.get("base_url")
            or "https://api.deepseek.com/v1"
        )
        self.model: str = chat.get("model") or deepseek.get("model") or "deepseek-chat"
        self.embedding_provider: str = emb["provider"]
        self.embedding_backend: str = emb["backend"]
        self.embedding_api_key: str = emb["api_key"]
        self.embedding_base_url: str = emb["base_url"]
        self.embedding_model: str = emb["model"]
        self.timeout: int = int(chat.get("timeout") or deepseek.get("timeout") or 120)
        self.max_retries: int = int(chat.get("max_retries", 2))
        self.fallback_enabled: bool = chat.get("fallback_enabled", True)
        kg_rel = chat.get("knowledge_graph", "datasets/knowledge/drug_kg.json")
        self.knowledge_graph_path: Path = resolve_path(kg_rel)

    @property
    def DEEPSEEK_API_KEY(self) -> str:
        return self.api_key

    @property
    def DEEPSEEK_BASE_URL(self) -> str:
        return self.base_url

    @property
    def DEEPSEEK_MODEL(self) -> str:
        return self.model

    @property
    def DEEPSEEK_EMBEDDING_MODEL(self) -> str:
        return self.embedding_model

    @property
    def EMBEDDING_BASE_URL(self) -> str:
        return self.embedding_base_url

    @property
    def EMBEDDING_API_KEY(self) -> str:
        return self.embedding_api_key

    @property
    def LLM_TIMEOUT(self) -> int:
        return self.timeout

    @property
    def LLM_MAX_RETRIES(self) -> int:
        return self.max_retries

    @property
    def FALLBACK_ENABLED(self) -> bool:
        return self.fallback_enabled

    @property
    def is_configured(self) -> bool:
        if self.provider == "mock":
            return False
        return bool(self.api_key)

    def validate(self) -> list[str]:
        if self.provider == "mock":
            return ["chat.provider 不能为 mock，请设为 deepseek 并配置 api_key"]
        missing = []
        if not self.api_key:
            missing.append("MEDSAFE_CHAT__API_KEY or DEEPSEEK_API_KEY")
        return missing


config = ChatConfig()
