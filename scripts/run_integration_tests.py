"""Integration tests for rule engine, extract, multi-agent, and debate."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.schemas import CandidateDrug, PatientContext, ReviewOutput
from src.knowledge_base import SafetyKnowledgeBase
from src.review_engine import ReviewEngine
from src.clarify_engine import ClarifyEngine
from src.case_store import CaseStore
from src.orchestrator import MultiAgentOrchestrator
from src.agents.extract_agent import ExtractAgent
from src.llm.client import MockLLMClient
from src.utils import load_json, save_json

load_config()
kb = SafetyKnowledgeBase()
review_engine = ReviewEngine(kb=kb)
clarify_engine = ClarifyEngine()
case_store = CaseStore()
orchestrator = MultiAgentOrchestrator()
extract_agent = ExtractAgent(MockLLMClient())

results_log = {"timestamp": datetime.now().isoformat(), "tests": [], "summary": {}}


def record(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    results_log["tests"].append({"name": name, "status": status, "detail": detail})
    print(f"  [{status}] {name}: {detail}")


print("=" * 70)
print("RULE ENGINE TESTS")
print("=" * 70)

case1 = load_json(PROJECT_ROOT / "data/demo_cases/review_case_01.json")
pc1 = PatientContext.model_validate(case1["request"]["patient_context"])
cd1 = [CandidateDrug.model_validate(d) for d in case1["request"]["candidate_drugs"]]
r1 = review_engine.review(pc1, cd1)
record("rule: high risk warfarin+ibuprofen", r1.risk_level == "high" and r1.block_decision)
record("rule: DDI evidence", any(e.category == "drug_interaction" for e in r1.evidence))

case2 = load_json(PROJECT_ROOT / "data/demo_cases/review_case_02.json")
pc2 = PatientContext.model_validate(case2["request"]["patient_context"])
cd2 = [CandidateDrug.model_validate(d) for d in case2["request"]["candidate_drugs"]]
r2 = review_engine.review(pc2, cd2)
record("rule: allergy missing clarify", r2.need_clarification and "allergies" in r2.clarification_targets)

case3 = load_json(PROJECT_ROOT / "data/demo_cases/review_case_03.json")
pc3 = PatientContext.model_validate(case3["request"]["patient_context"])
cd3 = [CandidateDrug.model_validate(d) for d in case3["request"]["candidate_drugs"]]
r3 = review_engine.review(pc3, cd3)
record("rule: pregnancy clarify", "pregnancy_status" in r3.clarification_targets)

cl1 = load_json(PROJECT_ROOT / "data/demo_cases/clarify_case_01.json")
cl_out1 = clarify_engine.clarify(
    PatientContext.model_validate(cl1["request"]["patient_context"]),
    [CandidateDrug.model_validate(d) for d in cl1["request"]["candidate_drugs"]],
    ReviewOutput.model_validate(cl1["request"]["review_output"]),
)
record("clarify: questions", cl_out1.status == "need_user_input" and len(cl_out1.questions) >= 2)

cl2 = load_json(PROJECT_ROOT / "data/demo_cases/clarify_case_02.json")
cl_out2 = clarify_engine.clarify(
    PatientContext.model_validate(cl2["request"]["patient_context"]),
    [CandidateDrug.model_validate(d) for d in cl2["request"]["candidate_drugs"]],
    ReviewOutput.model_validate(cl2["request"]["review_output"]),
    unable_to_answer=True,
)
record("clarify: conservative fallback", cl_out2.status == "conservative_fallback")

print("\n" + "=" * 70)
print("LLM EXTRACT TESTS (mock)")
print("=" * 70)

demo_text = "病人基本信息：性别M，年龄67。主诉胸痛。既往有高血压。当前服用 warfarin 和 metoprolol。"
raw, ext = extract_agent.extract(demo_text)
record("extract: parses", ext is not None)
record("extract: age", ext is not None and ext.age == 67)
record("extract: meds", ext is not None and "warfarin" in ext.current_medications)

print("\n" + "=" * 70)
print("MULTI-AGENT ORCHESTRATOR TESTS")
print("=" * 70)

ma1 = orchestrator.run(pc1, cd1)
record("agent: multi-agent opinions", len(ma1.agent_opinions) >= 4,
       f"agents={len(ma1.agent_opinions)}")
record("agent: arbitration block high risk", ma1.arbitration.consensus_block_decision)
record("agent: rule evidence preserved", len(ma1.rule_output.evidence) >= 1)
record("agent: pharmacist present",
       any(o.agent_id == "clinical_pharmacist" for o in ma1.agent_opinions))
record("agent: pharmacy present",
       any(o.agent_id == "pharmacy_inventory" for o in ma1.agent_opinions))

ma2 = orchestrator.run(pc2, cd2)
record("agent: clarify triggered", ma2.clarify_output is not None or ma2.arbitration.need_clarification)

ma3 = orchestrator.run(pc3, cd3, unable_to_answer=True)
record("agent: conservative path", ma3.clarify_output is not None)

consult_case = load_json(PROJECT_ROOT / "data/demo_cases/consult_case_01.json")
consult_pc = PatientContext.model_validate(consult_case["request"]["patient_context"])
consult_cd = [CandidateDrug.model_validate(d) for d in consult_case["request"]["candidate_drugs"]]
ma4 = orchestrator.run(consult_pc, consult_cd)
case = case_store.upsert_case(
    patch={
        "patient_context": consult_pc.model_dump(),
        "candidate_drugs": [d.model_dump() for d in consult_cd],
        "review_output": ma4.rule_output.model_dump(),
        "agent_opinions": [o.model_dump() for o in ma4.agent_opinions],
        "arbitration": ma4.arbitration.model_dump(),
        "final_recommendation": ma4.final_recommendation,
        "status": "complete",
    },
    stage="agent_review",
    payload={"mode": "multi_agent"},
)
case_store.upsert_case(case_id=case.case_id, stage="arbitration", payload=ma4.arbitration.model_dump())
case_store.upsert_case(case_id=case.case_id, stage="final", payload={"final_recommendation": ma4.final_recommendation})
replayed = case_store.get_case(case.case_id)
record("case: persisted", replayed.case_id == case.case_id)
record("case: agent opinions", len(replayed.agent_opinions) >= 4)
record("case: arbitration", replayed.arbitration is not None)

save_json(replayed.model_dump(), PROJECT_ROOT / "data/demo_cases/complete_case_log.json")

print("\n" + "=" * 70)
print("MULTI-ROUND DEBATE TESTS")
print("=" * 70)

ma_debate = orchestrator.run(pc1, cd1)
record("debate: enabled", ma_debate.debate is not None and ma_debate.debate.enabled)
record(
    "debate: multi-round",
    ma_debate.debate is not None and len(ma_debate.debate.rounds) >= 2,
    f"rounds={len(ma_debate.debate.rounds) if ma_debate.debate else 0}",
)
record(
    "debate: safety panel",
    ma_debate.safety_panel is not None and len(ma_debate.safety_panel.flags) >= 1,
)
record(
    "debate: consensus or flag",
    ma_debate.debate.final_consensus or ma_debate.debate.flagged_for_human,
)
record(
    "debate: min confidence tracked",
    ma_debate.debate.min_confidence > 0,
    f"min_conf={ma_debate.debate.min_confidence:.2f}",
)

print("\n" + "=" * 70)
print("DRUG CATALOG / CPOE TESTS")
print("=" * 70)

import tempfile
import shutil
from src.drug_catalog.csv_import import FormularyCsvImporter
from src.drug_catalog.catalog_service import DrugCatalogService
from src.drug_catalog.review_facade import CpoeReviewFacade
from src.schemas import (
    CpoeMedicationReviewRequest,
    CpoeMedicationOrder,
    CpoePatientSnapshot,
    DrugItem,
)

_test_db_dir = tempfile.mkdtemp(prefix="medsafe_catalog_test_")
_test_db = Path(_test_db_dir) / "test_formulary.db"
_sample_csv = PROJECT_ROOT / "data/hospital/formulary_sample.csv"

try:
    import_result = FormularyCsvImporter(_test_db).import_csv(_sample_csv, sync_version="test_v1")
    record("catalog: csv import", import_result["rows_upserted"] >= 15, f"upserted={import_result['rows_upserted']}")

    test_catalog = DrugCatalogService(_test_db)
    warfarin = test_catalog.get_by_id("H001001")
    record("catalog: lookup by id", warfarin is not None and warfarin.canonical_key == "warfarin")

    ibu = test_catalog.resolve_by_name("布洛芬")
    record("catalog: resolve chinese name", ibu is not None and ibu.hospital_drug_id == "H001004")

    cpoe = CpoeReviewFacade(catalog=test_catalog)
    cpoe_req = CpoeMedicationReviewRequest(
        encounter_id="ENC_TEST",
        patient=CpoePatientSnapshot(patient_id="P001", age=72, gender="M"),
        orders=[
            CpoeMedicationOrder(
                order_id="ORD1",
                hospital_drug_id="H001004",
                dose="0.3g",
                route="PO",
                frequency="TID",
            )
        ],
        existing_medications=[
            DrugItem(hospital_drug_id="H001001", name="华法林钠 2.5mg", dose="2.5mg", route="PO", frequency="QD"),
        ],
    )
    cpoe_resp = cpoe.review(cpoe_req)
    record(
        "cpoe: warfarin+ibuprofen blocked",
        cpoe_resp.overall_status == "blocked",
        f"status={cpoe_resp.overall_status}, alerts={len(cpoe_resp.alerts)}",
    )
    record(
        "cpoe: DDI alert present",
        any(a.rule_id == "ddi_warfarin_ibuprofen_bleeding" for a in cpoe_resp.alerts),
    )

    oos_req = CpoeMedicationReviewRequest(
        encounter_id="ENC_TEST2",
        patient=CpoePatientSnapshot(patient_id="P002", age=45, gender="F"),
        orders=[
            CpoeMedicationOrder(order_id="ORD2", hospital_drug_id="H001013", display_name="克拉霉素"),
        ],
    )
    oos_resp = cpoe.review(oos_req)
    record(
        "cpoe: out of stock warning",
        any(a.rule_id == "OUT_OF_STOCK" for a in oos_resp.alerts),
    )
finally:
    shutil.rmtree(_test_db_dir, ignore_errors=True)

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
passed = sum(1 for t in results_log["tests"] if t["status"] == "PASS")
failed = sum(1 for t in results_log["tests"] if t["status"] == "FAIL")
total = len(results_log["tests"])
results_log["summary"] = {
    "total": total, "passed": passed, "failed": failed,
    "pass_rate": f"{passed/total*100:.1f}%" if total else "N/A",
}
print(f"Total: {total}, Passed: {passed}, Failed: {failed}")
save_json(results_log, PROJECT_ROOT / "data/integration_test_results.json")
sys.exit(1 if failed else 0)
