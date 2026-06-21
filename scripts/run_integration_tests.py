"""Integration tests for Stage 3 (rule engine) and Stage 4 (multi-agent)."""
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
print("STAGE 3: Rule Engine Tests")
print("=" * 70)

case1 = load_json(PROJECT_ROOT / "data/demo_cases/review_case_01.json")
pc1 = PatientContext.model_validate(case1["request"]["patient_context"])
cd1 = [CandidateDrug.model_validate(d) for d in case1["request"]["candidate_drugs"]]
r1 = review_engine.review(pc1, cd1)
record("S3-C1: high risk warfarin+ibuprofen", r1.risk_level == "high" and r1.block_decision)
record("S3-C1: DDI evidence", any(e.category == "drug_interaction" for e in r1.evidence))

case2 = load_json(PROJECT_ROOT / "data/demo_cases/review_case_02.json")
pc2 = PatientContext.model_validate(case2["request"]["patient_context"])
cd2 = [CandidateDrug.model_validate(d) for d in case2["request"]["candidate_drugs"]]
r2 = review_engine.review(pc2, cd2)
record("S3-C2: allergy missing clarify", r2.need_clarification and "allergies" in r2.clarification_targets)

case3 = load_json(PROJECT_ROOT / "data/demo_cases/review_case_03.json")
pc3 = PatientContext.model_validate(case3["request"]["patient_context"])
cd3 = [CandidateDrug.model_validate(d) for d in case3["request"]["candidate_drugs"]]
r3 = review_engine.review(pc3, cd3)
record("S3-C3: pregnancy clarify", "pregnancy_status" in r3.clarification_targets)

cl1 = load_json(PROJECT_ROOT / "data/demo_cases/clarify_case_01.json")
cl_out1 = clarify_engine.clarify(
    PatientContext.model_validate(cl1["request"]["patient_context"]),
    [CandidateDrug.model_validate(d) for d in cl1["request"]["candidate_drugs"]],
    ReviewOutput.model_validate(cl1["request"]["review_output"]),
)
record("S3-D1: clarify questions", cl_out1.status == "need_user_input" and len(cl_out1.questions) >= 2)

cl2 = load_json(PROJECT_ROOT / "data/demo_cases/clarify_case_02.json")
cl_out2 = clarify_engine.clarify(
    PatientContext.model_validate(cl2["request"]["patient_context"]),
    [CandidateDrug.model_validate(d) for d in cl2["request"]["candidate_drugs"]],
    ReviewOutput.model_validate(cl2["request"]["review_output"]),
    unable_to_answer=True,
)
record("S3-D2: conservative fallback", cl_out2.status == "conservative_fallback")

print("\n" + "=" * 70)
print("STAGE 2: LLM Extract Tests (mock)")
print("=" * 70)

demo_text = "病人基本信息：性别M，年龄67。主诉胸痛。既往有高血压。当前服用 warfarin 和 metoprolol。"
raw, ext = extract_agent.extract(demo_text)
record("S2-E1: extract parses", ext is not None)
record("S2-E2: extract age", ext is not None and ext.age == 67)
record("S2-E3: extract meds", ext is not None and "warfarin" in ext.current_medications)

print("\n" + "=" * 70)
print("STAGE 4: Multi-Agent Orchestrator Tests")
print("=" * 70)

ma1 = orchestrator.run(pc1, cd1)
record("S4-M1: multi-agent opinions", len(ma1.agent_opinions) >= 4,
       f"agents={len(ma1.agent_opinions)}")
record("S4-M2: arbitration block high risk", ma1.arbitration.consensus_block_decision)
record("S4-M3: rule evidence preserved", len(ma1.rule_output.evidence) >= 1)
record("S4-M4: pharmacist present",
       any(o.agent_id == "clinical_pharmacist" for o in ma1.agent_opinions))
record("S4-M5: pharmacy present",
       any(o.agent_id == "pharmacy_inventory" for o in ma1.agent_opinions))

ma2 = orchestrator.run(pc2, cd2)
record("S4-M6: clarify triggered", ma2.clarify_output is not None or ma2.arbitration.need_clarification)

ma3 = orchestrator.run(pc3, cd3, unable_to_answer=True)
record("S4-M7: conservative path", ma3.clarify_output is not None)

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
record("S4-F1: case persisted", replayed.case_id == case.case_id)
record("S4-F2: agent opinions in case", len(replayed.agent_opinions) >= 4)
record("S4-F3: arbitration in case", replayed.arbitration is not None)

save_json(replayed.model_dump(), PROJECT_ROOT / "data/demo_cases/complete_case_log.json")

print("\n" + "=" * 70)
print("STAGE 4b: Multi-Round Debate Tests")
print("=" * 70)

ma_debate = orchestrator.run(pc1, cd1)
record("S4-D1: debate enabled", ma_debate.debate is not None and ma_debate.debate.enabled)
record(
    "S4-D2: multi-round debate",
    ma_debate.debate is not None and len(ma_debate.debate.rounds) >= 2,
    f"rounds={len(ma_debate.debate.rounds) if ma_debate.debate else 0}",
)
record(
    "S4-D3: safety panel",
    ma_debate.safety_panel is not None and len(ma_debate.safety_panel.flags) >= 1,
)
record(
    "S4-D4: debate consensus or flag",
    ma_debate.debate.final_consensus or ma_debate.debate.flagged_for_human,
)
record(
    "S4-D5: min confidence tracked",
    ma_debate.debate.min_confidence > 0,
    f"min_conf={ma_debate.debate.min_confidence:.2f}",
)

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
