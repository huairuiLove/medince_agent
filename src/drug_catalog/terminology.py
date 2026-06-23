from __future__ import annotations

from src.drug_catalog.catalog_service import DrugCatalogService
from src.drug_catalog.models import HospitalDrug
from src.knowledge_base import SafetyKnowledgeBase


class CatalogAwareKnowledgeBase(SafetyKnowledgeBase):
    """Safety KB with hospital formulary terminology resolution."""

    def __init__(
        self,
        catalog: DrugCatalogService | None = None,
        kb_path: str | None = None,
    ) -> None:
        super().__init__(kb_path)
        self.catalog = catalog

    def resolve_drug(self, name: str, hospital_drug_id: str | None = None) -> str:
        if self.catalog and self.catalog.is_loaded():
            if hospital_drug_id:
                record = self.catalog.get_by_id(hospital_drug_id)
                if record and record.canonical_key:
                    return record.canonical_key
            if name:
                record = self.catalog.resolve_by_name(name)
                if record and record.canonical_key:
                    return record.canonical_key
        return super().resolve_drug(name)

    def resolve_hospital_drug(
        self,
        name: str = "",
        hospital_drug_id: str | None = None,
    ) -> HospitalDrug | None:
        if not self.catalog or not self.catalog.is_loaded():
            return None
        if hospital_drug_id:
            record = self.catalog.get_by_id(hospital_drug_id)
            if record:
                return record
        if name:
            return self.catalog.resolve_by_name(name)
        return None
