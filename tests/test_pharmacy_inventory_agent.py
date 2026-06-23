"""Pharmacy inventory agent stays within formulary/stock scope."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.agents.pharmacy_inventory import PharmacyInventoryAgent
from src.drug_catalog.models import HospitalDrug
from src.schemas import CandidateDrug, PatientContext


def _drug(
    drug_id: str,
    *,
    cn: str,
    in_formulary: bool = True,
    in_stock: bool = True,
    alternatives: list[str] | None = None,
) -> HospitalDrug:
    return HospitalDrug(
        hospital_drug_id=drug_id,
        generic_name_cn=cn,
        trade_name_cn=f"{cn}商品",
        strength="500mg",
        dosage_form="片剂",
        in_formulary=in_formulary,
        in_stock=in_stock,
        alternatives=alternatives or [],
    )


def test_clarithromycin_out_of_stock_suggests_formulary_alternative_not_ddi_block():
    catalog = MagicMock()
    catalog.is_loaded.return_value = True
    catalog.resolve_by_name.side_effect = lambda name: {
        "克拉霉素": _drug(
            "H-DEMO-00039",
            cn="克拉霉素",
            in_stock=False,
            alternatives=["H-DEMO-00038"],
        ),
        "阿奇霉素": _drug("H-DEMO-00038", cn="阿奇霉素", in_stock=True),
    }.get(name)
    catalog.get_by_id.side_effect = lambda drug_id: {
        "H-DEMO-00039": _drug(
            "H-DEMO-00039",
            cn="克拉霉素",
            in_stock=False,
            alternatives=["H-DEMO-00038"],
        ),
        "H-DEMO-00038": _drug("H-DEMO-00038", cn="阿奇霉素", in_stock=True),
    }.get(drug_id)
    catalog.list_alternatives.side_effect = lambda drug_id: (
        [_drug("H-DEMO-00038", cn="阿奇霉素", in_stock=True)]
        if drug_id == "H-DEMO-00039"
        else []
    )

    agent = PharmacyInventoryAgent(MagicMock(), catalog=catalog)
    opinion = agent.review(
        PatientContext(age=65, gender="M"),
        [CandidateDrug(name="克拉霉素", dose="500mg", route="PO", frequency="bid")],
        [],
    )

    assert opinion.block_decision is False
    assert opinion.risk_level in {"low", "medium"}
    assert any("缺货" in r for r in opinion.reasons)
    assert any("阿奇霉素" in alt for alt in opinion.alternatives)
    assert not any("DDI" in r or "CYP3A4" in r or "横纹肌" in r for r in opinion.reasons)
    assert all(e.startswith("formulary:") for e in opinion.evidence_cited)
    assert "替代" in opinion.summary or "缺货" in opinion.summary


def test_non_formulary_drug_blocks():
    catalog = MagicMock()
    catalog.is_loaded.return_value = True
    catalog.resolve_by_name.return_value = _drug(
        "H-X", cn="某药", in_formulary=False, in_stock=True
    )
    catalog.get_by_id.return_value = None
    catalog.list_alternatives.return_value = []

    agent = PharmacyInventoryAgent(MagicMock(), catalog=catalog)
    opinion = agent.review(
        PatientContext(),
        [CandidateDrug(name="某药")],
        [],
    )

    assert opinion.block_decision is True
    assert opinion.risk_level == "high"
    assert any("不在院基本目录" in r for r in opinion.reasons)
