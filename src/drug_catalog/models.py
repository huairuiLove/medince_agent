from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HospitalDrug:
    hospital_drug_id: str
    generic_name_cn: str = ""
    generic_name_en: str = ""
    trade_name_cn: str = ""
    strength: str = ""
    dosage_form: str = ""
    route: str = ""
    atc_code: str = ""
    rxnorm_rxcui: str = ""
    insurance_code: str = ""
    manufacturer: str = ""
    in_formulary: bool = True
    in_stock: bool = True
    high_alert: bool = False
    antibiotic_level: str = ""
    narcotic_class: str = ""
    restricted_dept: str = ""
    alternatives: list[str] = field(default_factory=list)
    canonical_key: str = ""
    sync_version: str = ""

    @property
    def display_name(self) -> str:
        parts = [self.trade_name_cn or self.generic_name_cn, self.strength, self.dosage_form]
        return " ".join(p for p in parts if p).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "hospital_drug_id": self.hospital_drug_id,
            "generic_name_cn": self.generic_name_cn,
            "generic_name_en": self.generic_name_en,
            "trade_name_cn": self.trade_name_cn,
            "strength": self.strength,
            "dosage_form": self.dosage_form,
            "route": self.route,
            "atc_code": self.atc_code,
            "rxnorm_rxcui": self.rxnorm_rxcui,
            "insurance_code": self.insurance_code,
            "manufacturer": self.manufacturer,
            "in_formulary": self.in_formulary,
            "in_stock": self.in_stock,
            "high_alert": self.high_alert,
            "antibiotic_level": self.antibiotic_level,
            "narcotic_class": self.narcotic_class,
            "restricted_dept": self.restricted_dept,
            "alternatives": list(self.alternatives),
            "canonical_key": self.canonical_key,
            "sync_version": self.sync_version,
            "display_name": self.display_name,
        }
