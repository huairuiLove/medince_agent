from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from transformers import AutoTokenizer, BertConfig, BertModel

from src.config import get_config, resolve_path
from src.llm.errors import DdiModelNotReadyError
from src.safety_models.smiles_lookup import SmilesLookup

logger = logging.getLogger(__name__)

DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "ddi_bert"
_HF_REPO_ID = "ltmai/Bio_ClinicalBERT_DDI_finetuned"


def is_ddi_bert_enabled() -> bool:
    cfg = get_config().get("safety_models", {})
    return bool(cfg.get("enabled", True) and cfg.get("ddi_bert", {}).get("enabled", True))


class BioClinicalBertClassification(nn.Module):
    """Architecture matching ltmai/Bio_ClinicalBERT_DDI_finetuned checkpoint."""

    def __init__(self, config: BertConfig) -> None:
        super().__init__()
        self.bert_model = BertModel(config)
        hidden1 = getattr(config, "hidden_size1", 68)
        hidden2 = getattr(config, "hidden_size2", 54)
        hidden3 = getattr(config, "hidden_size3", 40)
        self.hidden_layer = nn.Linear(config.hidden_size, hidden1)
        self.hidden_layer2 = nn.Linear(hidden1, hidden2)
        self.hidden_layer3 = nn.Linear(hidden2, hidden3)
        self.classification = nn.Linear(hidden3, config.num_labels)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
        token_type_ids: torch.Tensor | None = None,
    ) -> torch.Tensor:
        outputs = self.bert_model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
        )
        pooled = outputs.pooler_output
        x = torch.relu(self.hidden_layer(pooled))
        x = torch.relu(self.hidden_layer2(x))
        x = torch.relu(self.hidden_layer3(x))
        return self.classification(x)


class DdiClassifier:
    """Bio_ClinicalBERT DDI pair scorer — SMILES [SEP] SMILES → interaction probability."""

    def __init__(
        self,
        model_dir: str | Path | None = None,
        smiles_lookup: SmilesLookup | None = None,
        high_threshold: float = 0.75,
        medium_threshold: float = 0.55,
        device: str | None = None,
    ) -> None:
        cfg = get_config().get("safety_models", {}).get("ddi_bert", {})
        self.model_dir = Path(resolve_path(model_dir or cfg.get("model_dir", "models/ddi_bert")))
        self.smiles = smiles_lookup or SmilesLookup(
            resolve_path(cfg.get("smiles_path", "datasets/knowledge/drug_smiles.json"))
        )
        self.high_threshold = float(cfg.get("high_threshold", high_threshold))
        self.medium_threshold = float(cfg.get("medium_threshold", medium_threshold))
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._tokenizer: Any | None = None
        self._model: BioClinicalBertClassification | None = None
        self._ready = False
        self._load_error: str | None = None
        self._enabled = is_ddi_bert_enabled() and self.model_dir.name != "__disabled__"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def available(self) -> bool:
        if self._ready:
            return True
        if self._load_error:
            return False
        return self._checkpoint_exists()

    def _checkpoint_exists(self) -> bool:
        return (self.model_dir / "pytorch_model.bin").exists() and (self.model_dir / "config.json").exists()

    def _ensure_loaded(self) -> bool:
        if self._ready:
            return True
        if self._load_error:
            return False
        if not self._checkpoint_exists():
            self._load_error = f"DDI model not found at {self.model_dir}"
            logger.warning(self._load_error)
            return False
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir))
            config = BertConfig.from_pretrained(str(self.model_dir))
            self._model = BioClinicalBertClassification(config)
            state_dict = torch.load(
                self.model_dir / "pytorch_model.bin",
                map_location="cpu",
                weights_only=False,
            )
            state_dict.pop("bert_model.embeddings.position_ids", None)
            self._model.load_state_dict(state_dict, strict=True)
            self._model.to(self.device)
            self._model.eval()
            self._ready = True
            logger.info("DDI classifier loaded from %s", self.model_dir)
            return True
        except Exception as exc:
            self._load_error = str(exc)
            logger.warning("DDI classifier load failed: %s", exc)
            return False

    def require_ready(self) -> DdiClassifier:
        if not self._enabled:
            raise DdiModelNotReadyError("safety_models.ddi_bert.enabled 为 false，但当前路径要求 DDI 模型。")
        if not self._ensure_loaded():
            detail = self._load_error or f"checkpoint 缺失: {self.model_dir / 'pytorch_model.bin'}"
            raise DdiModelNotReadyError(
                detail,
                hint=f"请运行: python scripts/download_models.py --ddi-bert （HuggingFace: {_HF_REPO_ID}）",
            )
        return self

    def predict_pair(self, drug_a: str, drug_b: str) -> dict[str, Any] | None:
        self.require_ready()
        smiles_a = self.smiles.resolve(drug_a)
        smiles_b = self.smiles.resolve(drug_b)
        if not smiles_a or not smiles_b:
            return None
        text = f"{smiles_a} [SEP] {smiles_b}"
        assert self._tokenizer is not None and self._model is not None
        encoded = self._tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with torch.no_grad():
            logits = self._model(**encoded)
            probs = torch.softmax(logits, dim=-1)[0]
        positive_prob = float(probs[1].item())
        risk_level = "none"
        if positive_prob >= self.high_threshold:
            risk_level = "high"
        elif positive_prob >= self.medium_threshold:
            risk_level = "medium"
        return {
            "drug_a": drug_a,
            "drug_b": drug_b,
            "positive_prob": positive_prob,
            "risk_level": risk_level,
            "smiles_a": smiles_a,
            "smiles_b": smiles_b,
        }

    def predict_pairs(
        self,
        pairs: list[tuple[str, str]],
        batch_size: int = 32,
    ) -> list[dict[str, Any]]:
        """Batch score drug pairs; skips pairs without resolvable SMILES."""
        if not pairs:
            return []
        self.require_ready()

        resolved: list[tuple[str, str, str, str, str]] = []
        for drug_a, drug_b in pairs:
            smiles_a = self.smiles.resolve(drug_a)
            smiles_b = self.smiles.resolve(drug_b)
            if not smiles_a or not smiles_b:
                continue
            text = f"{smiles_a} [SEP] {smiles_b}"
            resolved.append((drug_a, drug_b, smiles_a, smiles_b, text))

        if not resolved:
            return []

        assert self._tokenizer is not None and self._model is not None
        results: list[dict[str, Any]] = []
        total_batches = (len(resolved) + batch_size - 1) // batch_size
        for batch_idx, start in enumerate(range(0, len(resolved), batch_size)):
            if batch_idx % 20 == 0 and batch_idx > 0:
                logger.info("DDI batch %d / %d", batch_idx, total_batches)
            chunk = resolved[start:start + batch_size]
            texts = [item[4] for item in chunk]
            encoded = self._tokenizer(
                texts,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True,
            )
            encoded = {key: value.to(self.device) for key, value in encoded.items()}
            with torch.no_grad():
                logits = self._model(**encoded)
                probs = torch.softmax(logits, dim=-1)
            for idx, (drug_a, drug_b, smiles_a, smiles_b, _) in enumerate(chunk):
                positive_prob = float(probs[idx, 1].item())
                risk_level = "none"
                if positive_prob >= self.high_threshold:
                    risk_level = "high"
                elif positive_prob >= self.medium_threshold:
                    risk_level = "medium"
                if risk_level == "none":
                    continue
                results.append(
                    {
                        "drug_a": drug_a,
                        "drug_b": drug_b,
                        "positive_prob": positive_prob,
                        "risk_level": risk_level,
                        "smiles_a": smiles_a,
                        "smiles_b": smiles_b,
                    }
                )
        return results

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "available": self.available,
            "loaded": self._ready,
            "model_dir": str(self.model_dir),
            "hf_repo": _HF_REPO_ID,
            "high_threshold": self.high_threshold,
            "medium_threshold": self.medium_threshold,
            "smiles_lookup": self.smiles.status(),
            "error": self._load_error,
        }


@lru_cache(maxsize=1)
def get_ddi_classifier() -> DdiClassifier:
    if not is_ddi_bert_enabled():
        return DdiClassifier(model_dir=Path("__disabled__"))
    return DdiClassifier()
