from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import numpy as np

from src.config import get_config, resolve_path
from src.drug_catalog.models import HospitalDrug
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

    def __init__(self, model_dir: Path) -> None:
        self.model_dir = Path(model_dir)
        self.model_id = "intfloat/multilingual-e5-small"
        self._tokenizer = None
        self._model = None
        self._embeddings: np.ndarray | None = None
        self._drug_ids: list[str] = []
        self._load_error: str | None = None

    @property
    def model_present(self) -> bool:
        return (self.model_dir / "config.json").exists()

    def status(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_dir": str(self.model_dir),
            "model_present": self.model_present,
            "index_built": self._embeddings is not None,
            "indexed_drugs": len(self._drug_ids),
            "load_error": self._load_error,
        }

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True
        if not self.model_present:
            self._load_error = f"Model not found at {self.model_dir}. Run: python scripts/download_models.py --drug-search"
            return False
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir))
            self._model = AutoModel.from_pretrained(str(self.model_dir))
            self._model.eval()
            self._load_error = None
            return True
        except Exception as exc:
            self._load_error = str(exc)
            logger.warning("Failed to load drug search model: %s", exc)
            return False

    def _encode(self, texts: list[str]) -> np.ndarray:
        import torch

        assert self._tokenizer is not None and self._model is not None
        prefixed = [f"passage: {t}" for t in texts]
        batch_size = 32
        vectors: list[np.ndarray] = []
        with torch.no_grad():
            for start in range(0, len(prefixed), batch_size):
                batch = prefixed[start : start + batch_size]
                tokens = self._tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=128,
                    return_tensors="pt",
                )
                outputs = self._model(**tokens)
                mask = tokens["attention_mask"].unsqueeze(-1).float()
                summed = (outputs.last_hidden_state * mask).sum(dim=1)
                counts = mask.sum(dim=1).clamp(min=1e-9)
                emb = (summed / counts).cpu().numpy()
                vectors.append(emb)
        matrix = np.vstack(vectors).astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix / np.clip(norms, 1e-9, None)

    def build(self, drugs: list[HospitalDrug]) -> None:
        if not drugs:
            self._embeddings = None
            self._drug_ids = []
            return
        if not self._ensure_model():
            return
        docs = [_drug_document(d) for d in drugs]
        self._drug_ids = [d.hospital_drug_id for d in drugs]
        self._embeddings = self._encode(docs)
        logger.info("Built drug semantic index: %d drugs", len(self._drug_ids))

    def search(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        if not query.strip() or self._embeddings is None or not self._drug_ids:
            return []
        if not self._ensure_model():
            return []
        import torch

        assert self._tokenizer is not None and self._model is not None
        prefixed = f"query: {query.strip()}"
        with torch.no_grad():
            tokens = self._tokenizer(
                prefixed,
                padding=True,
                truncation=True,
                max_length=128,
                return_tensors="pt",
            )
            outputs = self._model(**tokens)
            mask = tokens["attention_mask"].unsqueeze(-1).float()
            vec = (outputs.last_hidden_state * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
            q = vec.cpu().numpy().astype(np.float32)
        q = q / max(float(np.linalg.norm(q)), 1e-9)
        scores = (self._embeddings @ q.T).squeeze(-1)
        top_idx = np.argsort(scores)[::-1][:limit]
        return [(self._drug_ids[int(i)], float(scores[int(i)])) for i in top_idx if scores[int(i)] > 0.25]


def get_semantic_index(reload: bool = False) -> DrugSemanticIndex:
    global _INDEX
    if _INDEX is not None and not reload:
        return _INDEX
    cfg = get_config().get("drug_catalog", {}).get("semantic_search", {})
    model_dir = resolve_path(cfg.get("model_dir", "models/drug_search"))
    _INDEX = DrugSemanticIndex(model_dir)
    return _INDEX


def rebuild_semantic_index(drugs: list[HospitalDrug]) -> dict[str, Any]:
    cfg = get_config().get("drug_catalog", {}).get("semantic_search", {})
    if not cfg.get("enabled", True):
        return {"enabled": False}
    download_hint = "python scripts/download_models.py --drug-search"
    with _INDEX_LOCK:
        index = get_semantic_index(reload=True)
        if not index.model_present:
            raise DrugSearchModelNotReadyError("模型文件缺失", download_hint)
        index.build(drugs)
        status = index.status()
        if not status.get("index_built") or status["indexed_drugs"] == 0:
            raise DrugSearchModelNotReadyError("索引构建失败", download_hint)
        return status
