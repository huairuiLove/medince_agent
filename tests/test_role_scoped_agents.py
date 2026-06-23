"""Core agents produce distinct opinions by role-scoped evidence."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.agents.clinical_pharmacist import ClinicalPharmacistAgent
from src.agents.internal_medicine import InternalMedicineAgent
from src.agents.pharmacy_inventory import PharmacyInventoryAgent
from src.agents.specialist_router import SpecialistAgent
from src.drug_catalog.models import HospitalDrug
from src.schemas import CandidateDrug, DiagnosisItem, PatientContext, RuleEvidence


def _ddi() -> RuleEvidence:
    return RuleEvidence(
        rule_id="ddi_clarithromycin_simvastatin_muscle",
        category="drug_interaction",
        risk_level="high",
        summary="克拉霉素与辛伐他汀联用可显著增加肌病风险。",
        implicated_drugs=["clarithromycin", "simvastatin"],
    )


def test_agents_diverge_on_clarithromycin_simvastatin_ddi():
    patient = PatientContext(
        age=65,
        gender="M",
        allergies=["NKDA"],
        diagnoses=[DiagnosisItem(name="社区获得性肺炎"), DiagnosisItem(name="高脂血症")],
        current_medications=[CandidateDrug(name="simvastatin", ingredient="simvastatin")],
    )
    candidates = [CandidateDrug(name="克拉霉素", ingredient="clarithromycin")]
    evidence = [_ddi()]

    pharmacist = ClinicalPharmacistAgent(MagicMock()).review(patient, candidates, evidence)
    attending = InternalMedicineAgent(MagicMock()).review(patient, candidates, evidence)
    specialist = SpecialistAgent(MagicMock()).review(patient, candidates, evidence)

    catalog = MagicMock()
    catalog.is_loaded.return_value = True
    catalog.resolve_by_name.return_value = HospitalDrug(
        hospital_drug_id="H-DEMO-00039",
        generic_name_cn="克拉霉素",
        trade_name_cn="克拉仙",
        strength="0.25g",
        dosage_form="片剂",
        in_formulary=True,
        in_stock=False,
        alternatives=["H-DEMO-00038"],
    )
    catalog.get_by_id.return_value = None
    catalog.list_alternatives.return_value = [
        HospitalDrug(
            hospital_drug_id="H-DEMO-00038",
            generic_name_cn="阿奇霉素",
            trade_name_cn="希舒美",
            strength="0.25g",
            dosage_form="片剂",
            in_formulary=True,
            in_stock=True,
        )
    ]
    inventory = PharmacyInventoryAgent(MagicMock(), catalog=catalog).review(patient, candidates, evidence)

    assert pharmacist.block_decision is True
    assert pharmacist.risk_level == "high"
    assert any("pharmacist:ddi_" in e for e in pharmacist.evidence_cited)

    assert attending.block_decision is False
    assert "适应证" in attending.summary or "临床路径" in attending.summary
    assert not any("ddi_" in e for e in attending.evidence_cited)

    assert specialist.block_decision is False
    assert not any("ddi_" in e for e in specialist.evidence_cited)

    assert inventory.block_decision is False
    assert any("缺货" in r for r in inventory.reasons)
    assert inventory.alternatives
    assert any("H-DEMO-00038" in alt or "希舒美" in alt for alt in inventory.alternatives)
    assert "formulary:" in inventory.evidence_cited[0]

    summaries = {pharmacist.summary, attending.summary, specialist.summary, inventory.summary}
    assert len(summaries) == 4
