from __future__ import annotations

import logging
import threading
from typing import Any

import numpy as np

from src.config import get_config
from src.drug_catalog.models import HospitalDrug
from src.llm.embedding_client import embed_texts, embedding_status, is_embedding_configured, resolve_embedding_config
from src.llm.errors import DrugSearchModelNotReadyError

logger = logging.getLogger("drug-semantic-search")

_INDEX_LOCK = threading.Lock()
_INDEX: "DrugSemanticIndex | None" = None


def _drug_document(drug: HospitalDrug) -> str:
    parts = [
        drug.generic_name_cn,
        drug.generic_name_en,
        drug.trade_name_cn,
        drug.atc_code,
        drug.hospital_drug_id,
        drug.manufacturer,
    ]
    return " | ".join(p.strip() for p in parts if p and p.strip())


class DrugSemanticIndex:
    """Multilingual embedding index for hospital formulary semantic retrieval."""

    def __init__(self) -> None:
        self._embeddings: np.ndarray | None = None
        self._drug_ids: list[str] = []
        self._load_error: str | None = None

    @property
    def model_present(self) -> bool:
        return is_embedding_configured()

    def status(self) -> dict[str, Any]:
        emb = embedding_status()
        return {
            "backend": emb.get("backend"),
            "provider": emb.get("provider"),
            "model": emb.get("model"),
            "model_dir": emb.get("model_dir"),
            "base_url": emb.get("base_url"),
            "model_present": self.model_present,
            "index_built": self._embeddings is not None,
            "indexed_drugs": len(self._drug_ids),
            "load_error": self._load_error or emb.get("error"),
        }

    def _encode(self, texts: list[str], kind: str = "passage") -> np.ndarray:
        return embed_texts(texts, kind="query" if kind == "query" else "passage")

    def build(self, drugs: list[HospitalDrug]) -> None:
        if not drugs:
            self._embeddings = None
            self._drug_ids = []
            return
        if not self.model_present:
            cfg = resolve_embedding_config()
            if cfg["backend"] == "local":
                self._load_error = (
                    f"Model not found at {cfg['model_dir']}. "
                    "Run: python scripts/download_models.py --drug-search"
                )
            else:
                self._load_error = "Embedding API 未配置，请检查 embedding.base_url / embedding.model"
            return
        try:
            docs = [_drug_document(d) for d in drugs]
            self._drug_ids = [d.hospital_drug_id for d in drugs]
            batch_size = max(1, int(resolve_embedding_config().get("batch_size", 32)))
            chunks: list[np.ndarray] = []
            for start in range(0, len(docs), batch_size):
                chunks.append(self._encode(docs[start : start + batch_size], kind="passage"))
            self._embeddings = np.vstack(chunks) if chunks else None
            self._load_error = None
            logger.info("Built drug semantic index: %d drugs", len(self._drug_ids))
        except Exception as exc:
            self._load_error = str(exc)
            logger.warning("Failed to build drug semantic index: %s", exc)

    def search(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        if not query.strip() or self._embeddings is None or not self._drug_ids:
            return []
        if not self.model_present:
            return []
        try:
            q = self._encode([query.strip()], kind="query")
            scores = (self._embeddings @ q.T).squeeze(-1)
            min_score = float(
                get_config().get("drug_catalog", {}).get("semantic_search", {}).get("min_score", 0.25)
            )
            top_idx = np.argsort(scores)[::-1][:limit]
            return [
                (self._drug_ids[int(i)], float(scores[int(i)]))
                for i in top_idx
                if scores[int(i)] > min_score
            ]
        except Exception as exc:
            logger.warning("Drug semantic search failed: %s", exc)
            return []


def get_semantic_index(reload: bool = False) -> DrugSemanticIndex:
    global _INDEX
    if _INDEX is not None and not reload:
        return _INDEX
    _INDEX = DrugSemanticIndex()
    return _INDEX


def rebuild_semantic_index(drugs: list[HospitalDrug]) -> dict[str, Any]:
    cfg = get_config().get("drug_catalog", {}).get("semantic_search", {})
    if not cfg.get("enabled", True):
        return {"enabled": False}

    emb_cfg = resolve_embedding_config()
    if emb_cfg["backend"] == "local":
        download_hint = "python scripts/download_models.py --drug-search"
    else:
        download_hint = (
            "配置 embedding.provider=lmstudio、embedding.base_url=http://localhost:1234/v1，"
            "并在 LM Studio 中加载 embedding 模型"
        )

    with _INDEX_LOCK:
        index = get_semantic_index(reload=True)
        if not index.model_present:
            raise DrugSearchModelNotReadyError("Embedding 未就绪", download_hint)
        index.build(drugs)
        status = index.status()
        if not status.get("index_built") or status["indexed_drugs"] == 0:
            detail = status.get("load_error") or "索引构建失败"
            raise DrugSearchModelNotReadyError(detail, download_hint)
        return status
