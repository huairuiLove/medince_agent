"""Allergy specialist agent stays within allergy / ADR scope."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.agents.allergy_specialist import AllergySpecialistAgent, filter_allergy_evidence
from src.schemas import CandidateDrug, PatientContext, RuleEvidence


def _ddi_evidence() -> RuleEvidence:
    return RuleEvidence(
        rule_id="ddi_clarithromycin_simvastatin_muscle",
        category="drug_interaction",
        risk_level="high",
        summary="克拉霉素与辛伐他汀联用可显著增加肌病和横纹肌溶解风险。",
        mechanism="CYP3A4 抑制导致辛伐他汀暴露升高。",
        implicated_drugs=["simvastatin", "clarithromycin"],
        recommendation="避免联用。",
    )


def test_filter_allergy_evidence_excludes_ddi():
    ddi = _ddi_evidence()
    allergy = RuleEvidence(
        rule_id="alg_penicillin_amoxicillin",
        category="allergy_contraindication",
        risk_level="high",
        summary="青霉素过敏患者不宜使用阿莫西林。",
    )
    filtered = filter_allergy_evidence([ddi, allergy])
    assert [item.rule_id for item in filtered] == ["alg_penicillin_amoxicillin"]


def test_nkda_clarithromycin_simvastatin_does_not_block_on_ddi():
    agent = AllergySpecialistAgent(MagicMock())
    opinion = agent.review(
        PatientContext(
            age=65,
            gender="M",
            allergies=["NKDA"],
            current_medications=[
                CandidateDrug(name="clarithromycin", ingredient="clarithromycin"),
            ],
        ),
        [CandidateDrug(name="simvastatin", ingredient="simvastatin")],
        [_ddi_evidence()],
    )

    assert opinion.block_decision is False
    assert opinion.risk_level == "low"
    assert not any("DDI" in r or "CYP3A4" in r or "横纹肌" in r for r in opinion.reasons)
    assert not any("ddi_" in e for e in opinion.evidence_cited)
    assert "过敏" in opinion.summary or "ADR" in opinion.summary or "临床药师" in opinion.summary
    agent.llm.chat_json.assert_not_called()


def test_allergy_rule_hit_blocks_without_llm():
    agent = AllergySpecialistAgent(MagicMock())
    allergy_evidence = RuleEvidence(
        rule_id="alg_penicillin_amoxicillin",
        category="allergy_contraindication",
        risk_level="high",
        summary="已知青霉素过敏患者使用阿莫西林存在过敏风险。",
        alternatives=["评估非青霉素方案。"],
        clarification_fields=["allergies"],
    )
    opinion = agent.review(
        PatientContext(allergies=["penicillin"]),
        [CandidateDrug(name="amoxicillin", ingredient="amoxicillin")],
        [allergy_evidence, _ddi_evidence()],
    )

    assert opinion.block_decision is True
    assert opinion.risk_level == "high"
    assert any("alg_penicillin_amoxicillin" in e for e in opinion.evidence_cited)
    agent.llm.chat_json.assert_not_called()


def test_llm_ddi_drift_is_normalized():
    llm = MagicMock()
    llm.chat_json.return_value = {
        "risk_level": "high",
        "block_decision": True,
        "reasons": ["根据 ddi_clarithromycin_simvastatin_muscle，CYP3A4 抑制导致横纹肌溶解风险。"],
        "alternatives": [],
        "need_clarification": False,
        "clarification_targets": [],
        "confidence": 0.95,
        "evidence_cited": ["rule_evidence中ddi_clarithromycin_simvastatin_muscle"],
        "summary": "高危药物相互作用，建议阻断。",
    }
    agent = AllergySpecialistAgent(llm)
    opinion = agent.review(
        PatientContext(allergies=["磺胺"]),
        [CandidateDrug(name="simvastatin", ingredient="simvastatin")],
        [_ddi_evidence()],
    )

    assert opinion.block_decision is False
    assert not any("ddi_" in e for e in opinion.evidence_cited)


def test_missing_allergy_history_requests_clarification_not_block():
    agent = AllergySpecialistAgent(MagicMock())
    opinion = agent.review(
        PatientContext(allergies=[], missing_fields=["allergies"]),
        [CandidateDrug(name="amoxicillin", ingredient="amoxicillin")],
        [],
    )

    assert opinion.block_decision is False
    assert opinion.need_clarification is True
    assert "allergies" in opinion.clarification_targets
    agent.llm.chat_json.assert_not_called()
