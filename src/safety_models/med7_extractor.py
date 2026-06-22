from __future__ import annotations

import logging
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.config import get_config, resolve_path
from src.schemas import DrugItem, ExtractionOutput

logger = logging.getLogger(__name__)

MED7_LABELS = {"DRUG", "STRENGTH", "FORM", "ROUTE", "DOSAGE", "FREQUENCY", "DURATION"}


class Med7Extractor:
    """Clinical medication NER via en_core_med7_lg (MIMIC-III trained)."""

    def __init__(self, wheel_path: str | Path | None = None) -> None:
        cfg = get_config().get("safety_models", {}).get("med7", {})
        self.wheel_path = Path(
            resolve_path(wheel_path or cfg.get("wheel_path", "models/med7/en_core_med7_lg-1.1.0-py3-none-any.whl"))
        )
        self._nlp: Any | None = None
        self._ready = False
        self._load_error: str | None = None

    @property
    def available(self) -> bool:
        if self._ready:
            return True
        if self._load_error:
            return False
        return self.wheel_path.exists()

    def _install_wheel_if_needed(self) -> None:
        try:
            import en_core_med7_lg  # noqa: F401
            return
        except ImportError:
            pass
        if not self.wheel_path.exists():
            raise FileNotFoundError(f"Med7 wheel not found: {self.wheel_path}")
        logger.info("Installing Med7 from %s", self.wheel_path)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q", str(self.wheel_path)],
        )

    def _ensure_loaded(self) -> bool:
        if self._ready:
            return True
        if self._load_error:
            return False
        try:
            self._install_wheel_if_needed()
            import spacy

            self._nlp = spacy.load("en_core_med7_lg")
            self._ready = True
            logger.info("Med7 extractor loaded")
            return True
        except Exception as exc:
            self._load_error = str(exc)
            logger.warning("Med7 load failed: %s", exc)
            return False

    def extract_medications(self, text: str) -> list[DrugItem]:
        if not text.strip() or not self._ensure_loaded():
            return []
        assert self._nlp is not None
        doc = self._nlp(text)
        drugs: list[DrugItem] = []
        current: dict[str, str] = {}
        for ent in doc.ents:
            if ent.label_ == "DRUG":
                if current.get("name"):
                    drugs.append(self._to_drug_item(current))
                    current = {}
                current["name"] = ent.text.strip()
            elif ent.label_ == "STRENGTH":
                current["dose"] = ent.text.strip()
            elif ent.label_ == "ROUTE":
                current["route"] = ent.text.strip()
            elif ent.label_ == "FREQUENCY":
                current["frequency"] = ent.text.strip()
        if current.get("name"):
            drugs.append(self._to_drug_item(current))
        return drugs

    @staticmethod
    def _to_drug_item(payload: dict[str, str]) -> DrugItem:
        return DrugItem(
            name=payload.get("name", ""),
            dose=payload.get("dose", ""),
            route=payload.get("route", ""),
            frequency=payload.get("frequency", ""),
        )

    def enrich_extraction(self, text: str, extraction: ExtractionOutput | None) -> ExtractionOutput | None:
        meds = self.extract_medications(text)
        if not meds:
            return extraction
        if extraction is None:
            return ExtractionOutput(current_medications=[m.name for m in meds])
        merged = list(extraction.current_medications)
        seen = {name.lower() for name in merged}
        for item in meds:
            if item.name.lower() not in seen:
                merged.append(item.name)
                seen.add(item.name.lower())
        return extraction.model_copy(update={"current_medications": merged})

    def status(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "loaded": self._ready,
            "wheel_path": str(self.wheel_path),
            "error": self._load_error,
        }


@lru_cache(maxsize=1)
def get_med7_extractor() -> Med7Extractor:
    cfg = get_config().get("safety_models", {})
    if not cfg.get("enabled", True) or not cfg.get("med7", {}).get("enabled", True):
        return Med7Extractor(wheel_path=Path("__disabled__"))
    return Med7Extractor()
