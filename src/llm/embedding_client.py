"""Embedding client — OpenAI-compatible API (LM Studio / DeepSeek / OpenAI) or local transformers."""
from __future__ import annotations

import logging
import os
from typing import Any, Literal

import httpx
import numpy as np

from src.config import get_config, resolve_path
from src.llm.errors import LLMNotConfiguredError

logger = logging.getLogger("embedding-client")

InputKind = Literal["query", "passage"]

_LOCAL_TOKENIZER = None
_LOCAL_MODEL = None
_RESOLVED_API_MODEL: dict[str, str] = {}


def _fetch_api_models(cfg: dict[str, Any]) -> list[str]:
    url = f"{cfg['base_url']}/models"
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    with httpx.Client(timeout=min(cfg["timeout"], 10.0)) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        payload = response.json()
    return [str(item.get("id", "")).strip() for item in payload.get("data", []) if item.get("id")]


def _pick_embedding_model(configured: str, model_ids: list[str]) -> str:
    if not model_ids:
        raise LLMNotConfiguredError(
            "Embedding",
            hint="LM Studio 未返回可用模型。请在 LM Studio 中加载 embedding 模型并启动 Local Server。",
        )
    configured = configured.strip()
    if configured in model_ids:
        return configured

    needle = configured.lower()
    embed_models = [m for m in model_ids if "embed" in m.lower()]
    candidates = embed_models or model_ids

    for model_id in candidates:
        hay = model_id.lower()
        if needle and (needle in hay or hay in needle):
            return model_id

    for token in ("nomic", "bge", "e5", "minilm"):
        if token in needle:
            for model_id in candidates:
                if token in model_id.lower():
                    return model_id

    return candidates[0]


def _resolve_api_model(cfg: dict[str, Any], *, refresh: bool = False) -> str:
    cache_key = f"{cfg['base_url']}|{cfg['model']}"
    if not refresh and cache_key in _RESOLVED_API_MODEL:
        return _RESOLVED_API_MODEL[cache_key]

    if cfg["provider"] == "lmstudio":
        try:
            model_ids = _fetch_api_models(cfg)
            resolved = _pick_embedding_model(str(cfg["model"]), model_ids)
        except httpx.HTTPError as exc:
            raise LLMNotConfiguredError(
                "Embedding",
                hint=(
                    f"无法连接 LM Studio ({cfg['base_url']}): {exc}. "
                    "请确认 Local Server 已启动并加载 embedding 模型。"
                ),
            ) from exc
        if resolved != cfg["model"]:
            logger.info(
                "Resolved LM Studio embedding model %r -> %r",
                cfg["model"],
                resolved,
            )
        _RESOLVED_API_MODEL[cache_key] = resolved
        return resolved

    return str(cfg["model"])


def _embedding_api_error_hint(cfg: dict[str, Any], exc: httpx.HTTPStatusError) -> str:
    body = ""
    try:
        body = str(exc.response.json().get("error", ""))
    except Exception:
        body = exc.response.text[:200]

    hint = (
        f"Embedding API 返回 HTTP {exc.response.status_code}"
        + (f": {body}" if body else "")
        + f"。当前配置 model={cfg['model']!r}，base_url={cfg['base_url']!r}。"
    )
    if cfg["provider"] == "lmstudio":
        try:
            model_ids = _fetch_api_models(cfg)
            embed_ids = [m for m in model_ids if "embed" in m.lower()] or model_ids
            hint += f" LM Studio 可用 embedding 模型: {', '.join(embed_ids)}。"
            hint += " 可将 MEDSAFE_EMBEDDING__MODEL 设为上述完整 id，或保留 nomic-embed-text 由系统自动匹配。"
        except Exception:
            hint += " 请在 LM Studio 中加载 embedding 模型并启动 Local Server。"
    return hint


def resolve_embedding_config() -> dict[str, Any]:
    """Merge embedding config with legacy chat.embedding_model fallback."""
    cfg = get_config()
    emb = dict(cfg.get("embedding") or {})
    chat = cfg.get("chat", {})

    provider = str(emb.get("provider", "")).lower()
    if not provider:
        if chat.get("embedding_model"):
            provider = str(chat.get("provider", "deepseek")).lower()
            emb.setdefault("api_key", chat.get("api_key", ""))
            emb.setdefault("base_url", chat.get("base_url", "https://api.deepseek.com/v1"))
            emb.setdefault("model", chat.get("embedding_model"))
            emb.setdefault("timeout", chat.get("timeout", 120))
        else:
            provider = "local"

    backend = "local" if provider == "local" else "api"
    base_url = str(emb.get("base_url") or "http://localhost:1234/v1").rstrip("/")
    api_key = (
        emb.get("api_key")
        or os.getenv("MEDSAFE_EMBEDDING__API_KEY", "")
        or ("lm-studio" if provider == "lmstudio" else "")
    )
    model_dir = resolve_path(emb.get("model_dir", "models/drug_search"))

    return {
        "provider": provider,
        "backend": backend,
        "api_key": api_key,
        "base_url": base_url,
        "model": emb.get("model", "nomic-embed-text"),
        "timeout": float(emb.get("timeout", 60)),
        "query_prefix": emb.get("query_prefix", ""),
        "passage_prefix": emb.get("passage_prefix", "passage: "),
        "model_dir": model_dir,
        "model_id": emb.get("model_id", "intfloat/multilingual-e5-small"),
        "batch_size": int(emb.get("batch_size", 32)),
    }


def embedding_status() -> dict[str, Any]:
    cfg = resolve_embedding_config()
    status: dict[str, Any] = {
        "provider": cfg["provider"],
        "backend": cfg["backend"],
        "model": cfg["model"],
        "base_url": cfg["base_url"] if cfg["backend"] == "api" else None,
        "model_dir": str(cfg["model_dir"]) if cfg["backend"] == "local" else None,
        "configured": False,
        "resolved_model": None,
        "error": None,
    }
    try:
        status["configured"] = is_embedding_configured()
        if status["configured"] and cfg["backend"] == "api" and cfg["provider"] == "lmstudio":
            status["resolved_model"] = _resolve_api_model(cfg)
    except LLMNotConfiguredError as exc:
        status["error"] = str(exc)
    except Exception as exc:
        status["error"] = str(exc)
    return status


def is_embedding_configured() -> bool:
    cfg = resolve_embedding_config()
    if cfg["provider"] == "mock":
        raise LLMNotConfiguredError(
            "Embedding",
            hint="embedding.provider 不能为 mock。请设为 lmstudio / openai / deepseek / local。",
        )
    if cfg["backend"] == "local":
        return (cfg["model_dir"] / "config.json").exists()
    if not cfg.get("model"):
        return False
    if not cfg.get("base_url"):
        return False
    if cfg["provider"] != "lmstudio" and not cfg.get("api_key"):
        return False
    return True


def _require_configured() -> dict[str, Any]:
    cfg = resolve_embedding_config()
    if not is_embedding_configured():
        if cfg["backend"] == "local":
            hint = (
                f"本地模型缺失：{cfg['model_dir']}。"
                "请运行 python scripts/download_models.py --drug-search，"
                "或将 embedding.provider 设为 lmstudio 并配置 base_url。"
            )
        else:
            hint = (
                "请配置 embedding.base_url / embedding.model，"
                "或设置 MEDSAFE_EMBEDDING__BASE_URL / MEDSAFE_EMBEDDING__MODEL。"
                "LM Studio 示例：provider=lmstudio, base_url=http://localhost:1234/v1"
            )
        raise LLMNotConfiguredError("Embedding", hint=hint)
    return cfg


def _apply_prefix(text: str, kind: InputKind, cfg: dict[str, Any]) -> str:
    prefix = cfg["query_prefix"] if kind == "query" else cfg["passage_prefix"]
    if prefix and not text.startswith(prefix.strip()):
        return f"{prefix}{text}"
    return text


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return matrix.astype(np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return (matrix / np.clip(norms, 1e-9, None)).astype(np.float32)


def _embed_local(texts: list[str], cfg: dict[str, Any]) -> np.ndarray:
    global _LOCAL_TOKENIZER, _LOCAL_MODEL
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    import torch
    from transformers import AutoModel, AutoTokenizer

    model_dir = cfg["model_dir"]
    if _LOCAL_TOKENIZER is None or _LOCAL_MODEL is None:
        _LOCAL_TOKENIZER = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
        _LOCAL_MODEL = AutoModel.from_pretrained(str(model_dir), local_files_only=True)
        _LOCAL_MODEL.eval()

    batch_size = cfg["batch_size"]
    vectors: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            tokens = _LOCAL_TOKENIZER(
                batch,
                padding=True,
                truncation=True,
                max_length=128,
                return_tensors="pt",
            )
            outputs = _LOCAL_MODEL(**tokens)
            mask = tokens["attention_mask"].unsqueeze(-1).float()
            summed = (outputs.last_hidden_state * mask).sum(dim=1)
            counts = mask.sum(dim=1).clamp(min=1e-9)
            emb = (summed / counts).cpu().numpy()
            vectors.append(emb)
    return _normalize_rows(np.vstack(vectors))


def _embed_api_sync(texts: list[str], cfg: dict[str, Any]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    model = _resolve_api_model(cfg)
    url = f"{cfg['base_url']}/embeddings"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {"model": model, "input": texts if len(texts) > 1 else texts[0]}

    with httpx.Client(timeout=cfg["timeout"]) as client:
        try:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400 and cfg["provider"] == "lmstudio":
                _RESOLVED_API_MODEL.pop(f"{cfg['base_url']}|{cfg['model']}", None)
                model = _resolve_api_model(cfg, refresh=True)
                payload["model"] = model
                response = client.post(url, headers=headers, json=payload)
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as retry_exc:
                    raise LLMNotConfiguredError("Embedding", hint=_embedding_api_error_hint(cfg, retry_exc)) from retry_exc
            else:
                raise LLMNotConfiguredError("Embedding", hint=_embedding_api_error_hint(cfg, exc)) from exc
        data = response.json()

    items = sorted(data["data"], key=lambda x: x["index"])
    matrix = np.array([item["embedding"] for item in items], dtype=np.float32)
    return _normalize_rows(matrix)


async def _embed_api_async(texts: list[str], cfg: dict[str, Any]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    model = _resolve_api_model(cfg)
    url = f"{cfg['base_url']}/embeddings"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {"model": model, "input": texts if len(texts) > 1 else texts[0]}

    async with httpx.AsyncClient(timeout=cfg["timeout"]) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400 and cfg["provider"] == "lmstudio":
                _RESOLVED_API_MODEL.pop(f"{cfg['base_url']}|{cfg['model']}", None)
                model = _resolve_api_model(cfg, refresh=True)
                payload["model"] = model
                response = await client.post(url, headers=headers, json=payload)
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as retry_exc:
                    raise LLMNotConfiguredError("Embedding", hint=_embedding_api_error_hint(cfg, retry_exc)) from retry_exc
            else:
                raise LLMNotConfiguredError("Embedding", hint=_embedding_api_error_hint(cfg, exc)) from exc
        data = response.json()

    items = sorted(data["data"], key=lambda x: x["index"])
    matrix = np.array([item["embedding"] for item in items], dtype=np.float32)
    return _normalize_rows(matrix)


def embed_texts(texts: list[str], kind: InputKind = "passage") -> np.ndarray:
    cfg = _require_configured()
    prefixed = [_apply_prefix(t, kind, cfg) for t in texts]
    if cfg["backend"] == "local":
        return _embed_local(prefixed, cfg)
    return _embed_api_sync(prefixed, cfg)


async def embed_texts_async(texts: list[str], kind: InputKind = "passage") -> np.ndarray:
    cfg = _require_configured()
    prefixed = [_apply_prefix(t, kind, cfg) for t in texts]
    if cfg["backend"] == "local":
        return _embed_local(prefixed, cfg)
    return await _embed_api_async(prefixed, cfg)


async def embed_text_async(text: str, kind: InputKind = "passage") -> list[float]:
    matrix = await embed_texts_async([text], kind=kind)
    return matrix[0].tolist()
