"""Department core formulary filtering for CPOE shortcuts and dashboard."""

from __future__ import annotations

from src.utils import normalize_text


class DepartmentFormularyFilter:
    """Filter and rank drugs against a department core formulary list."""

    def __init__(self, core_formulary: list[str] | None = None) -> None:
        self._canonical = {normalize_text(d) for d in (core_formulary or []) if normalize_text(d)}

    @property
    def drugs(self) -> list[str]:
        return sorted(self._canonical)

    def is_core(self, drug_name: str) -> bool:
        return normalize_text(drug_name) in self._canonical

    def filter_names(self, drug_names: list[str]) -> list[str]:
        if not self._canonical:
            return list(drug_names)
        matched = [name for name in drug_names if self.is_core(name)]
        return matched if matched else list(drug_names)

    def rank_first(self, drug_names: list[str]) -> list[str]:
        if not self._canonical:
            return list(drug_names)
        core = [name for name in drug_names if self.is_core(name)]
        other = [name for name in drug_names if not self.is_core(name)]
        return core + other
