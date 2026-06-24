#!/usr/bin/env python3
"""Generate rich clinical case templates per department (rule-review ready)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.case_templates import (
    departments_missing_primary_templates,
    departments_missing_templates,
    list_case_templates,
)
from src.config import datasets_path
from src.review_engine import ReviewEngine
from src.schemas import CandidateDrug, PatientContext
from src.utils import load_json, save_json

OUTPUT = datasets_path("case_templates/department_templates.json")
BENCHMARK_TEMPLATES_OUTPUT = datasets_path("case_templates/department_benchmark_templates.json")
STAGE11_OUTPUT = datasets_path("case_templates/stage11_clinical_cases.json")
RULE_SAMPLES = datasets_path("case_templates/rule_review_samples.json")
BENCHMARK_CASES_DIR = datasets_path("benchmark/cases")

# Benchmark JSON uses short dept ids; catalog.json uses canonical dept_id.
BENCH_DEPT_ALIAS: dict[str, str] = {
    "obgyn": "obstetrics_gynecology",
    "infectious": "infectious_disease",
}

# Negative-control templates (expected no high-risk hit) — skip min-evidence validation.
NEGATIVE_TEMPLATE_IDS = frozenset({"dept_general_internal_safe_01"})

_SUBJECT_BASE = 60_001
_HADM_BASE = 70_001


def _med(
    name: str,
    *,
    dose: str = "",
    route: str = "PO",
    frequency: str = "qd",
    ingredient: str | None = None,
) -> dict[str, str]:
    return {
        "name": name,
        "ingredient": ingredient or name,
        "dose": dose,
        "route": route,
        "frequency": frequency,
    }


def _cand(
    name: str,
    *,
    dose: str = "",
    route: str = "PO",
    frequency: str = "qd",
    indication: str = "",
    ingredient: str | None = None,
) -> dict[str, str]:
    return {
        "name": name,
        "ingredient": ingredient or name,
        "dose": dose,
        "route": route,
        "frequency": frequency,
        "indication": indication,
        "source": "candidate",
    }


def _dx(icd9: str, name: str) -> dict[str, str]:
    return {"icd9_code": icd9, "name": name}


def _patient(
    dept_id: str,
    *,
    idx: int,
    age: int,
    gender: str,
    admission_type: str,
    source_text: str,
    chief_complaint: str,
    history_present_illness: str,
    symptoms: list[str],
    pmh: list[str],
    diagnoses: list[dict[str, str]],
    current_medications: list[dict[str, str]],
    allergies: list[str] | None = None,
    pregnancy_status: str = "not_applicable",
    lactation_status: str = "not_lactating",
    egfr: float | None = None,
    weight_kg: float | None = None,
    missing_fields: list[str] | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "subject_id": _SUBJECT_BASE + idx,
        "hadm_id": _HADM_BASE + idx,
        "age": age,
        "gender": gender,
        "department": dept_id,
        "admission_type": admission_type,
        "source_text": source_text,
        "chief_complaint": chief_complaint,
        "history_present_illness": history_present_illness,
        "symptoms_or_complaints": symptoms,
        "past_medical_history": pmh,
        "diagnoses": diagnoses,
        "current_medications": current_medications,
        "allergies": allergies if allergies is not None else ["NKDA"],
        "pregnancy_status": pregnancy_status,
        "lactation_status": lactation_status,
        "missing_fields": missing_fields if missing_fields is not None else [],
    }
    if egfr is not None:
        ctx["egfr"] = egfr
    if weight_kg is not None:
        ctx["weight_kg"] = weight_kg
    return ctx


# Each entry: id suffix fields + patient builder args + candidate list
DEPT_RICH_CASES: list[dict[str, Any]] = [
    {
        "id": "dept_respiratory_01",
        "title": "COPD 加重：大环内酯 + 他汀",
        "description": "慢阻肺急性加重抗感染，克拉霉素与辛伐他汀存在 CYP3A4 肌病风险",
        "department": "respiratory",
        "patient": _patient(
            "respiratory",
            idx=0,
            age=65,
            gender="M",
            admission_type="INPATIENT",
            source_text="65岁男性，COPD 急性加重入院，长期吸入激素及支气管扩张剂，拟加用大环内酯抗感染；既往高脂血症口服辛伐他汀。",
            chief_complaint="咳嗽、咳痰、气促加重 3 天",
            history_present_illness="黄脓痰增多，活动后气促明显，无发热；吸烟史 30 包年，FEV1 预计值 45%。",
            symptoms=["咳嗽", "咳痰", "气促", "活动耐量下降"],
            pmh=["COPD GOLD III", "高脂血症", "吸烟史"],
            diagnoses=[_dx("491.21", "COPD 急性加重"), _dx("272.4", "高脂血症")],
            current_medications=[
                _med("salbutamol", dose="2 puff", frequency="prn", route="INH"),
                _med("budesonide", dose="400 mcg", frequency="bid", route="INH"),
                _med("clarithromycin", dose="500 mg", frequency="bid"),
            ],
            weight_kg=68.0,
        ),
        "candidate_drugs": [_cand("simvastatin", dose="20 mg", frequency="qd", indication="高脂血症")],
    },
    {
        "id": "dept_respiratory_02",
        "title": "重症肺炎/ARDS：广谱抗感染 + 茶碱 + 大环内酯",
        "description": "ICU 重症社区获得性肺炎，已用万古霉素/哌拉西林他唑巴坦/激素；拟加左氧氟沙星、氨茶碱及克拉霉素，审查重复抗感染与 CYP/QT 风险",
        "department": "respiratory",
        "patient": _patient(
            "respiratory",
            idx=30,
            age=62,
            gender="M",
            admission_type="ICU",
            source_text="62岁男性，重症社区获得性肺炎合并 ARDS 收住 ICU，机械通气；已用万古霉素、哌拉西林他唑巴坦及甲泼尼龙；拟加左氧氟沙星覆盖非典型病原体，并加氨茶碱平喘、克拉霉素抗非典型菌。",
            chief_complaint="高热、呼吸困难、低氧",
            history_present_illness="PaO₂/FiO₂ 110，双肺弥漫渗出；CRP 186 mg/L，PCT 8.2 ng/ml；既往 COPD GOLD II。",
            symptoms=["高热", "呼吸困难", "低氧", "咳脓痰"],
            pmh=["COPD", "吸烟史", "2 型糖尿病"],
            diagnoses=[_dx("486", "重症社区获得性肺炎"), _dx("518.81", "ARDS"), _dx("491.21", "COPD")],
            current_medications=[
                _med("vancomycin", dose="1 g", route="IV", frequency="q12h"),
                _med("piperacillin-tazobactam", dose="4.5 g", route="IV", frequency="q8h"),
                _med("methylprednisolone", dose="40 mg", route="IV", frequency="qd"),
                _med("salbutamol", dose="2.5 mg", route="INH", frequency="q6h"),
            ],
            weight_kg=70.0,
        ),
        "candidate_drugs": [
            _cand("levofloxacin", dose="750 mg", route="IV", frequency="qd", indication="重症肺炎抗感染"),
            _cand("theophylline", dose="200 mg", route="PO", frequency="bid", indication="COPD 平喘"),
            _cand("clarithromycin", dose="500 mg", route="IV", frequency="bid", indication="非典型病原体覆盖"),
        ],
    },
    {
        "id": "dept_neurology_01",
        "title": "癫痫合并房颤：华法林 + NSAIDs",
        "description": "癫痫/房颤患者长期抗凝，因头痛拟加用布洛芬，需评估出血风险",
        "department": "neurology",
        "patient": _patient(
            "neurology",
            idx=1,
            age=55,
            gender="M",
            admission_type="OUTPATIENT",
            source_text="55岁男性，癫痫及非瓣膜性房颤病史，长期丙戊酸及华法林治疗；近期反复头痛，拟短期使用 NSAIDs。",
            chief_complaint="反复头痛 1 周",
            history_present_illness="头痛以双侧颞部胀痛为主，VAS 5/10，无呕吐及意识障碍；INR 近期 2.3。",
            symptoms=["头痛", "偶发头晕"],
            pmh=["癫痫", "非瓣膜性房颤", "高血压"],
            diagnoses=[_dx("345.90", "癫痫"), _dx("427.31", "心房颤动")],
            current_medications=[
                _med("valproate", dose="500 mg", frequency="bid"),
                _med("warfarin", dose="3 mg", frequency="qd"),
                _med("levetiracetam", dose="500 mg", frequency="bid"),
            ],
        ),
        "candidate_drugs": [_cand("ibuprofen", dose="400 mg", frequency="tid", indication="头痛")],
    },
    {
        "id": "dept_neurosurgery_01",
        "title": "颅脑肿瘤术前抗凝桥接",
        "description": "脑膜瘤术前，华法林需桥接低分子肝素，评估出血与血栓风险",
        "department": "neurosurgery",
        "patient": _patient(
            "neurosurgery",
            idx=2,
            age=55,
            gender="M",
            admission_type="ELECTIVE",
            source_text="55岁男性，左侧颅脑占位拟行手术切除，长期服用华法林（机械瓣膜置换术后），术前需抗凝桥接。",
            chief_complaint="发现颅内占位 2 月，拟手术",
            history_present_illness="MRI 提示脑膜瘤，无急性神经功能缺损；末次 INR 2.8。",
            symptoms=["偶发头痛"],
            pmh=["机械瓣膜置换", "脑膜瘤", "癫痫"],
            diagnoses=[_dx("225.2", "脑膜瘤"), _dx("V43.3", "机械心脏瓣膜")],
            current_medications=[
                _med("warfarin", dose="5 mg", frequency="qd"),
                _med("levetiracetam", dose="500 mg", frequency="bid"),
            ],
        ),
        "candidate_drugs": [_cand("enoxaparin", dose="40 mg", route="SC", frequency="bid", indication="术前抗凝桥接")],
    },
    {
        "id": "dept_radiology_01",
        "title": "CT 增强前二甲双胍评估",
        "description": "2 型糖尿病拟行碘造影 CT，需评估二甲双胍与造影剂联用风险",
        "department": "radiology",
        "patient": _patient(
            "radiology",
            idx=3,
            age=62,
            gender="F",
            admission_type="OUTPATIENT",
            source_text="62岁女性，2 型糖尿病及高血压，长期二甲双胍控制血糖；因肺部阴影拟行 CT 增强扫描。",
            chief_complaint="体检发现肺部阴影",
            history_present_illness="HbA1c 7.2%，eGFR 58；无造影剂过敏史。",
            symptoms=[],
            pmh=["2 型糖尿病", "高血压"],
            diagnoses=[_dx("250.00", "2 型糖尿病"), _dx("401.9", "高血压")],
            current_medications=[
                _med("metformin", dose="850 mg", frequency="bid"),
                _med("lisinopril", dose="10 mg", frequency="qd"),
            ],
            egfr=58.0,
        ),
        "candidate_drugs": [_cand("iohexol", dose="350 mgI/ml", route="IV", frequency="once", indication="CT 增强造影")],
    },
    {
        "id": "dept_cardiology_01",
        "title": "心衰房颤 CKD：加用胺碘酮",
        "description": "心衰+房颤+CKD3 期多药联用，新增胺碘酮需审查 QT/地高辛/抗凝相互作用",
        "department": "cardiology",
        "patient": _patient(
            "cardiology",
            idx=4,
            age=72,
            gender="M",
            admission_type="INPATIENT",
            source_text="72岁男性，慢性心衰、持续性房颤及 CKD3 期，长期地高辛、利尿剂、华法林及螺内酯治疗；房颤心室率控制不佳，拟加用胺碘酮。",
            chief_complaint="气促、心悸加重",
            history_present_illness="BNP 890 pg/ml，LVEF 35%，eGFR 42；无甲状腺功能异常史。",
            symptoms=["气促", "心悸", "下肢水肿"],
            pmh=["慢性心衰", "房颤", "CKD3", "高血压"],
            diagnoses=[
                _dx("428.0", "充血性心力衰竭"),
                _dx("427.31", "心房颤动"),
                _dx("585.3", "慢性肾病 3 期"),
            ],
            current_medications=[
                _med("digoxin", dose="0.125 mg", frequency="qd"),
                _med("furosemide", dose="40 mg", frequency="qd"),
                _med("warfarin", dose="3 mg", frequency="qd"),
                _med("spironolactone", dose="20 mg", frequency="qd"),
            ],
            egfr=42.0,
            weight_kg=74.0,
        ),
        "candidate_drugs": [_cand("amiodarone", dose="200 mg", frequency="qd", indication="房颤节律控制")],
    },
    {
        "id": "dept_gastroenterology_01",
        "title": "双抗 + PPI：氯吡格雷 CYP2C19",
        "description": "PCI 后双联抗血小板，加用奥美拉唑可能影响氯吡格雷代谢",
        "department": "gastroenterology",
        "patient": _patient(
            "gastroenterology",
            idx=5,
            age=58,
            gender="M",
            admission_type="INPATIENT",
            source_text="58岁男性，PCI 术后双联抗血小板，既往消化性溃疡史；为预防溃疡复发拟加用 PPI。",
            chief_complaint="PCI 术后上腹不适",
            history_present_illness="支架植入 2 周，偶有烧心；无黑便及呕血。",
            symptoms=["烧心", "上腹不适"],
            pmh=["冠心病 PCI", "消化性溃疡史"],
            diagnoses=[_dx("414.01", "冠心病 PCI 后"), _dx("531.90", "消化性溃疡史")],
            current_medications=[
                _med("aspirin", dose="100 mg", frequency="qd"),
                _med("clopidogrel", dose="75 mg", frequency="qd"),
            ],
        ),
        "candidate_drugs": [_cand("omeprazole", dose="20 mg", frequency="qd", indication="溃疡预防")],
    },
    {
        "id": "dept_oncology_01",
        "title": "化疗 DDI：顺铂 + 酮康唑",
        "description": "顺铂方案联用强 CYP3A4 抑制剂酮康唑，需评估毒性叠加",
        "department": "oncology",
        "patient": _patient(
            "oncology",
            idx=6,
            age=58,
            gender="M",
            admission_type="INPATIENT",
            source_text="58岁男性，非小细胞肺癌接受含顺铂化疗，因真菌感染预防拟加用酮康唑。",
            chief_complaint="肺癌化疗第 2 周期",
            history_present_illness="化疗耐受尚可，中性粒细胞 2.1×10⁹/L；既往无肝肾功能衰竭。",
            symptoms=["乏力", "轻度恶心"],
            pmh=["非小细胞肺癌", "化疗中"],
            diagnoses=[_dx("162.9", "非小细胞肺癌")],
            current_medications=[_med("cisplatin", dose="75 mg/m²", route="IV", frequency="q3w")],
            egfr=78.0,
        ),
        "candidate_drugs": [_cand("ketoconazole", dose="200 mg", frequency="qd", indication="真菌感染预防")],
    },
    {
        "id": "dept_oncology_02",
        "title": "晚期 NSCLC：免疫 + 铂类联合化疗多药审查",
        "description": "非小细胞肺癌一线 pembrolizumab + 卡铂/培美曲塞，合并止吐/激素/抗凝/PPI，审查 DDI 与骨髓抑制叠加",
        "department": "oncology",
        "patient": _patient(
            "oncology",
            idx=31,
            age=64,
            gender="F",
            admission_type="INPATIENT",
            source_text="64岁女性，IV 期非鳞 NSCLC（腺癌），ECOG 1，拟第 1 周期 pembrolizumab + 卡铂 + 培美曲塞；既往 VTE 长期华法林；为预防 CINV 拟地塞米松 + 昂丹司琼，并加奥美拉唑护胃。",
            chief_complaint="肺癌第 1 周期化疗入院",
            history_present_illness="PET-CT 示多发骨转移；中性粒细胞 3.8×10⁹/L，PLT 210×10⁹/L；INR 2.4。",
            symptoms=["乏力", "咳嗽", "骨痛"],
            pmh=["非小细胞肺癌", "深静脉血栓", "华法林抗凝"],
            diagnoses=[_dx("162.9", "非小细胞肺癌"), _dx("453.41", "深静脉血栓")],
            current_medications=[
                _med("warfarin", dose="3 mg", frequency="qd"),
                _med("morphine", dose="5 mg", route="PO", frequency="q4h prn"),
            ],
            egfr=72.0,
            weight_kg=58.0,
        ),
        "candidate_drugs": [
            _cand("pembrolizumab", dose="200 mg", route="IV", frequency="q3w", indication="NSCLC 免疫治疗"),
            _cand("carboplatin", dose="AUC 5", route="IV", frequency="q3w", indication="NSCLC 化疗"),
            _cand("pemetrexed", dose="500 mg/m²", route="IV", frequency="q3w", indication="NSCLC 化疗"),
            _cand("dexamethasone", dose="8 mg", route="IV", frequency="qd", indication="CINV 预防"),
            _cand("ondansetron", dose="8 mg", route="IV", frequency="qd", indication="CINV 预防"),
            _cand("omeprazole", dose="20 mg", frequency="qd", indication="护胃"),
        ],
    },
    {
        "id": "dept_emergency_01",
        "title": "急诊阿片 + 苯二氮卓",
        "description": "多发伤镇痛镇静，吗啡联用地西泮存在呼吸抑制风险",
        "department": "emergency",
        "patient": _patient(
            "emergency",
            idx=7,
            age=45,
            gender="M",
            admission_type="EMERGENCY",
            source_text="45岁男性，交通事故多发伤，肋骨骨折及软组织损伤，急诊需镇痛镇静处理。",
            chief_complaint="车祸伤后剧烈疼痛",
            history_present_illness="右侧肋骨骨折 3 根，SpO₂ 96%，意识清楚；无药物过敏史。",
            symptoms=["胸痛", "活动痛加重", "焦虑"],
            pmh=[],
            diagnoses=[_dx("807.05", "肋骨骨折"), _dx("959.9", "多发伤")],
            current_medications=[],
        ),
        "candidate_drugs": [
            _cand("morphine", dose="5 mg", route="IV", frequency="stat", indication="急性疼痛"),
            _cand("diazepam", dose="5 mg", route="IV", frequency="stat", indication="焦虑/镇静"),
        ],
    },
    {
        "id": "dept_pharmacy_01",
        "title": "高警示：华法林 + NSAIDs",
        "description": "临床药师会诊：房颤抗凝患者加用布洛芬的出血风险审查",
        "department": "pharmacy",
        "patient": _patient(
            "pharmacy",
            idx=8,
            age=67,
            gender="M",
            admission_type="INPATIENT",
            source_text="67岁男性，房颤长期华法林及小剂量阿司匹林，因膝关节骨关节炎疼痛骨科建议 NSAIDs。",
            chief_complaint="膝关节痛要求止痛",
            history_present_illness="INR 2.5，无活动性出血；膝 OA 影像学明确。",
            symptoms=["膝关节痛", "活动受限"],
            pmh=["房颤", "骨关节炎"],
            diagnoses=[_dx("427.31", "心房颤动"), _dx("715.96", "膝骨关节炎")],
            current_medications=[
                _med("warfarin", dose="5 mg", frequency="qd"),
                _med("aspirin", dose="81 mg", frequency="qd"),
            ],
        ),
        "candidate_drugs": [_cand("ibuprofen", dose="400 mg", frequency="tid", indication="骨关节炎疼痛")],
    },
    {
        "id": "dept_general_internal_01",
        "title": "住院多病共存：华法林 + NSAIDs",
        "description": "全科住院患者房颤抗凝基础上加用布洛芬，审查出血风险",
        "department": "general_internal",
        "patient": _patient(
            "general_internal",
            idx=9,
            age=68,
            gender="M",
            admission_type="INPATIENT",
            source_text="68岁男性，房颤、高血压多病共存住院，长期华法林；膝骨关节炎疼痛明显，拟短期布洛芬。",
            chief_complaint="膝关节痛",
            history_present_illness="INR 2.4，无活动性出血；膝 OA 影像学明确。",
            symptoms=["膝关节痛", "活动受限"],
            pmh=["房颤", "高血压", "骨关节炎"],
            diagnoses=[_dx("427.31", "心房颤动"), _dx("401.9", "高血压"), _dx("715.96", "膝骨关节炎")],
            current_medications=[_med("warfarin", dose="5 mg", frequency="qd")],
            egfr=72.0,
        ),
        "candidate_drugs": [_cand("ibuprofen", dose="400 mg", frequency="tid", indication="骨关节炎疼痛")],
    },
    {
        "id": "dept_nephrology_01",
        "title": "CKD4：ACEI + 螺内酯",
        "description": "CKD4 期蛋白尿，拟加用螺内酯，需评估高钾及肾功能风险",
        "department": "nephrology",
        "patient": _patient(
            "nephrology",
            idx=10,
            age=64,
            gender="F",
            admission_type="INPATIENT",
            source_text="64岁女性，CKD4 期糖尿病肾病，已用 ACEI 及袢利尿剂；尿蛋白 2.1 g/24h，拟加用螺内酯。",
            chief_complaint="蛋白尿、水肿",
            history_present_illness="血钾 4.6 mmol/L，eGFR 22；无急性心衰表现。",
            symptoms=["下肢水肿", "泡沫尿"],
            pmh=["糖尿病肾病", "CKD4"],
            diagnoses=[_dx("585.4", "慢性肾病 4 期"), _dx("250.40", "糖尿病肾病")],
            current_medications=[
                _med("lisinopril", dose="10 mg", frequency="qd"),
                _med("furosemide", dose="40 mg", frequency="qd"),
            ],
            egfr=22.0,
        ),
        "candidate_drugs": [_cand("spironolactone", dose="25 mg", frequency="qd", indication="蛋白尿/心衰")],
    },
    {
        "id": "dept_endocrinology_01",
        "title": "低 eGFR 二甲双胍禁忌",
        "description": "2 型糖尿病 eGFR<30，二甲双胍存在乳酸酸中毒风险",
        "department": "endocrinology",
        "patient": _patient(
            "endocrinology",
            idx=11,
            age=65,
            gender="F",
            admission_type="OUTPATIENT",
            source_text="65岁女性，2 型糖尿病 10 年，磺脲类控制欠佳；eGFR 25，内分泌科拟加用二甲双胍。",
            chief_complaint="血糖控制不佳",
            history_present_illness="HbA1c 8.4%，无酮症；已接受糖尿病教育。",
            symptoms=["多饮", "乏力"],
            pmh=["2 型糖尿病", "糖尿病肾病"],
            diagnoses=[_dx("250.00", "2 型糖尿病"), _dx("585.4", "CKD4")],
            current_medications=[_med("glibenclamide", dose="5 mg", frequency="qd")],
            egfr=25.0,
        ),
        "candidate_drugs": [_cand("metformin", dose="850 mg", frequency="bid", indication="2 型糖尿病")],
    },
    {
        "id": "dept_hematology_01",
        "title": "华法林 + 氯吡格雷",
        "description": "血液科患者抗凝基础上加用抗血小板，出血风险显著升高",
        "department": "hematology",
        "patient": _patient(
            "hematology",
            idx=12,
            age=60,
            gender="M",
            admission_type="INPATIENT",
            source_text="60岁男性，原发免疫性血小板减少，合并房颤长期华法林；因 ACS 风险拟加用氯吡格雷。",
            chief_complaint="血小板减少合并房颤",
            history_present_illness="PLT 45×10⁹/L，INR 2.1；无活动性出血。",
            symptoms=["皮肤瘀斑"],
            pmh=["ITP", "房颤"],
            diagnoses=[_dx("287.31", "免疫性血小板减少症"), _dx("427.31", "心房颤动")],
            current_medications=[_med("warfarin", dose="5 mg", frequency="qd")],
        ),
        "candidate_drugs": [_cand("clopidogrel", dose="75 mg", frequency="qd", indication="抗血小板")],
    },
    {
        "id": "dept_geriatrics_01",
        "title": "老年多重用药 + 苯二氮卓",
        "description": "80 岁多病共存，新增劳拉西泮需评估 Beers 准则及跌倒风险",
        "department": "geriatrics",
        "patient": _patient(
            "geriatrics",
            idx=13,
            age=80,
            gender="F",
            admission_type="INPATIENT",
            source_text="80岁女性，高血压、阿尔茨海默病及失眠，长期多种心血管药物；家属要求加用苯二氮卓助眠。",
            chief_complaint="失眠、夜间游走",
            history_present_illness="MMSE 18 分，近 6 月跌倒 1 次；血压 138/78 mmHg。",
            symptoms=["失眠", "夜间定向力下降"],
            pmh=["高血压", "阿尔茨海默病", "跌倒史"],
            diagnoses=[_dx("401.9", "高血压"), _dx("331.0", "阿尔茨海默病"), _dx("780.52", "失眠")],
            current_medications=[
                _med("metoprolol", dose="25 mg", frequency="bid"),
                _med("amlodipine", dose="5 mg", frequency="qd"),
                _med("donepezil", dose="5 mg", frequency="qd"),
            ],
            weight_kg=52.0,
        ),
        "candidate_drugs": [_cand("lorazepam", dose="0.5 mg", frequency="hs", indication="失眠")],
    },
    {
        "id": "dept_rheumatology_01",
        "title": "MTX + NSAIDs",
        "description": "类风湿关节炎，甲氨蝶呤基础上加用布洛芬，需评估 GI/骨髓毒性",
        "department": "rheumatology",
        "patient": _patient(
            "rheumatology",
            idx=14,
            age=52,
            gender="F",
            admission_type="OUTPATIENT",
            source_text="52岁女性，RA 活动期，每周甲氨蝶呤及叶酸；因膝关节肿痛拟短期 NSAIDs。",
            chief_complaint="关节肿痛加重",
            history_present_illness="DAS28 4.2，CRP 28 mg/L；肝肾功能正常。",
            symptoms=["关节肿痛", "晨僵"],
            pmh=["类风湿关节炎"],
            diagnoses=[_dx("714.0", "类风湿关节炎")],
            current_medications=[
                _med("methotrexate", dose="15 mg", frequency="weekly"),
                _med("folic acid", dose="5 mg", frequency="weekly"),
            ],
        ),
        "candidate_drugs": [_cand("ibuprofen", dose="400 mg", frequency="tid", indication="关节痛")],
    },
    {
        "id": "dept_infectious_disease_01",
        "title": "青霉素过敏 + 阿莫西林",
        "description": "社区肺炎候选阿莫西林，明确青霉素过敏史，应触发过敏禁忌",
        "department": "infectious_disease",
        "patient": _patient(
            "infectious_disease",
            idx=15,
            age=34,
            gender="F",
            admission_type="URGENT",
            source_text="34岁女性，社区获得性肺炎，既往青霉素过敏（皮疹）；拟经验性阿莫西林抗感染。",
            chief_complaint="发热咳嗽 3 天",
            history_present_illness="体温 38.5℃，咳黄痰；胸片右下肺浸润影。",
            symptoms=["发热", "咳嗽", "咳痰"],
            pmh=["青霉素过敏"],
            diagnoses=[_dx("486", "社区获得性肺炎")],
            current_medications=[],
            allergies=["penicillin", "青霉素"],
        ),
        "candidate_drugs": [_cand("amoxicillin", dose="500 mg", frequency="tid", indication="社区获得性肺炎")],
    },
    {
        "id": "dept_infectious_disease_02",
        "title": "重症 HAP/VAP：抗感染升阶梯 + 伏立康唑",
        "description": "院内获得性肺炎机械通气，已用头孢曲松；拟升阶梯美罗培南 + 利奈唑胺 + 伏立康唑，审查重复覆盖与 QT/骨髓抑制",
        "department": "infectious_disease",
        "patient": _patient(
            "infectious_disease",
            idx=32,
            age=71,
            gender="M",
            admission_type="ICU",
            source_text="71岁男性，卒中后吸入性肺炎进展为 VAP，机械通气 5 天；已用头孢曲松；痰培养 ESBL 阴性、MRSA 阳性、曲霉抗原阳性；拟升阶梯美罗培南 + 利奈唑胺 + 伏立康唑。",
            chief_complaint="VAP 抗感染方案调整",
            history_present_illness="体温 38.8℃，WBC 18×10⁹/L；PaO₂/FiO₂ 135；既往无伏立康唑过敏。",
            symptoms=["发热", "脓痰", "低氧"],
            pmh=["脑梗死", "吸入性肺炎", "糖尿病"],
            diagnoses=[_dx("482.84", "院内获得性肺炎"), _dx("518.81", "机械通气"), _dx("117.3", "曲霉感染疑诊")],
            current_medications=[
                _med("ceftriaxone", dose="2 g", route="IV", frequency="qd"),
                _med("insulin glargine", dose="18 U", route="SC", frequency="qd"),
            ],
            egfr=55.0,
            weight_kg=68.0,
        ),
        "candidate_drugs": [
            _cand("meropenem", dose="1 g", route="IV", frequency="q8h", indication="VAP 升阶梯抗感染"),
            _cand("linezolid", dose="600 mg", route="IV", frequency="q12h", indication="MRSA 覆盖"),
            _cand("voriconazole", dose="200 mg", route="PO", frequency="bid", indication="侵袭性曲霉病"),
            _cand("levofloxacin", dose="750 mg", route="IV", frequency="qd", indication="非典型菌覆盖"),
        ],
    },
    {
        "id": "dept_obstetrics_gynecology_01",
        "title": "妊娠期 ACEI 禁忌",
        "description": "妊娠 32 周合并高血压，误开赖诺普利需触发妊娠禁忌",
        "department": "obstetrics_gynecology",
        "patient": _patient(
            "obstetrics_gynecology",
            idx=16,
            age=28,
            gender="F",
            admission_type="INPATIENT",
            source_text="28岁女性，G1P0，妊娠 32 周，妊娠期高血压；门诊误开 ACEI，产科会诊用药安全。",
            chief_complaint="妊娠 32 周，血压升高",
            history_present_illness="BP 158/98 mmHg，尿蛋白阴性，无子痫症状；已补叶酸。",
            symptoms=["头痛", "血压高"],
            pmh=["妊娠期高血压"],
            diagnoses=[_dx("642.3", "妊娠期高血压"), _dx("V22.2", "妊娠 32 周")],
            current_medications=[_med("folic acid", dose="5 mg", frequency="qd")],
            pregnancy_status="pregnant",
        ),
        "candidate_drugs": [_cand("lisinopril", dose="10 mg", frequency="qd", indication="高血压")],
    },
    {
        "id": "dept_pediatrics_01",
        "title": "儿童氟喹诺酮禁忌",
        "description": "8 岁儿童急性中耳炎，候选左氧氟沙星需评估年龄禁忌",
        "department": "pediatrics",
        "patient": _patient(
            "pediatrics",
            idx=17,
            age=8,
            gender="M",
            admission_type="URGENT",
            source_text="8岁男童，急性中耳炎，阿莫西林过敏；急诊备选左氧氟沙星。",
            chief_complaint="耳痛发热 2 天",
            history_present_illness="鼓膜充血，体温 38.2℃；体重 28 kg。",
            symptoms=["耳痛", "发热"],
            pmh=["阿莫西林过敏"],
            diagnoses=[_dx("382.9", "急性中耳炎")],
            current_medications=[],
            allergies=["amoxicillin"],
            weight_kg=28.0,
        ),
        "candidate_drugs": [_cand("levofloxacin", dose="10 mg/kg", frequency="bid", indication="急性中耳炎")],
    },
    {
        "id": "dept_orthopedic_01",
        "title": "骨科术后 NSAIDs + 抗凝",
        "description": "全膝置换术后华法林抗凝，拟加用布洛芬止痛",
        "department": "orthopedic",
        "patient": _patient(
            "orthopedic",
            idx=18,
            age=70,
            gender="M",
            admission_type="POSTOP",
            source_text="70岁男性，全膝置换术后第 3 天，房颤长期华法林；术后疼痛明显，拟 NSAIDs 止痛。",
            chief_complaint="术后膝痛",
            history_present_illness="INR 2.4，切口无渗血；VAS 7/10。",
            symptoms=["膝痛", "活动痛"],
            pmh=["房颤", "膝 OA"],
            diagnoses=[_dx("715.96", "膝骨关节炎"), _dx("V43.65", "全膝置换术后")],
            current_medications=[_med("warfarin", dose="3 mg", frequency="qd")],
        ),
        "candidate_drugs": [_cand("ibuprofen", dose="400 mg", frequency="tid", indication="术后止痛")],
    },
    {
        "id": "dept_urology_01",
        "title": "双重 α 阻滞剂",
        "description": "BPH 已用坦索罗辛，再加多沙唑嗪存在低血压叠加风险",
        "department": "urology",
        "patient": _patient(
            "urology",
            idx=19,
            age=65,
            gender="M",
            admission_type="OUTPATIENT",
            source_text="65岁男性，BPH 长期坦索罗辛，夜尿仍 3 次；泌尿科拟加用多沙唑嗪。",
            chief_complaint="排尿困难、夜尿",
            history_present_illness="IPSS 22 分，PSA 2.8 ng/ml；血压 128/76 mmHg。",
            symptoms=["排尿费力", "夜尿"],
            pmh=["良性前列腺增生"],
            diagnoses=[_dx("600.00", "良性前列腺增生")],
            current_medications=[_med("tamsulosin", dose="0.4 mg", frequency="qd")],
        ),
        "candidate_drugs": [_cand("doxazosin", dose="2 mg", frequency="qd", indication="BPH")],
    },
    {
        "id": "dept_icu_01",
        "title": "ICU 镇静镇痛联用",
        "description": "机械通气患者，丙泊酚+芬太尼联用需审查呼吸抑制及 DDI",
        "department": "icu",
        "patient": _patient(
            "icu",
            idx=20,
            age=48,
            gender="M",
            admission_type="ICU",
            source_text="48岁男性，ARDS 机械通气，升压药维持血压；拟丙泊酚镇静联合芬太尼镇痛。",
            chief_complaint="ARDS 机械通气",
            history_present_illness="PaO₂/FiO₂ 120，RASS -2 目标；已用去甲肾及万古霉素。",
            symptoms=["低氧", "镇静需求"],
            pmh=["ARDS", "肺炎"],
            diagnoses=[_dx("518.81", "ARDS"), _dx("486", "肺炎")],
            current_medications=[
                _med("norepinephrine", dose="0.1 mcg/kg/min", route="IV", frequency="continuous"),
                _med("vancomycin", dose="1 g", route="IV", frequency="q12h"),
            ],
            weight_kg=75.0,
        ),
        "candidate_drugs": [
            _cand("propofol", dose="50 mg/h", route="IV", frequency="continuous", indication="镇静"),
            _cand("fentanyl", dose="50 mcg/h", route="IV", frequency="continuous", indication="镇痛"),
        ],
    },
    {
        "id": "dept_anesthesiology_01",
        "title": "全麻诱导：咪达唑仑 + 芬太尼",
        "description": "全麻诱导联合用药，审查呼吸抑制及相互作用",
        "department": "anesthesiology",
        "patient": _patient(
            "anesthesiology",
            idx=21,
            age=50,
            gender="F",
            admission_type="PREOP",
            source_text="50岁女性，腹腔镜胆囊切除术，全麻诱导拟咪达唑仑+芬太尼；术前已给昂丹司琼。",
            chief_complaint="胆囊结石拟手术",
            history_present_illness="ASA II，气道评估 Mallampati II；无哮喘及药物过敏。",
            symptoms=[],
            pmh=["胆囊结石"],
            diagnoses=[_dx("574.20", "胆囊结石"), _dx("V72.84", "术前评估")],
            current_medications=[_med("ondansetron", dose="4 mg", route="IV", frequency="stat")],
            weight_kg=62.0,
        ),
        "candidate_drugs": [
            _cand("midazolam", dose="2 mg", route="IV", frequency="stat", indication="麻醉诱导"),
            _cand("fentanyl", dose="100 mcg", route="IV", frequency="stat", indication="麻醉诱导"),
        ],
    },
    {
        "id": "dept_psychiatry_01",
        "title": "SSRI + 苯二氮卓",
        "description": "抑郁焦虑共病，舍曲林基础上加用劳拉西泮，审查 Sedation/Beers",
        "department": "psychiatry",
        "patient": _patient(
            "psychiatry",
            idx=22,
            age=35,
            gender="F",
            admission_type="OUTPATIENT",
            source_text="35岁女性，抑郁焦虑共病，舍曲林治疗 4 周；急性焦虑发作，拟短期苯二氮卓。",
            chief_complaint="焦虑加重、失眠",
            history_present_illness="HAMD 18 分，无自杀意念；无物质滥用史。",
            symptoms=["焦虑", "失眠", "心悸"],
            pmh=["抑郁症", "焦虑症"],
            diagnoses=[_dx("296.32", "重度抑郁发作"), _dx("300.00", "焦虑障碍")],
            current_medications=[_med("sertraline", dose="50 mg", frequency="qd")],
        ),
        "candidate_drugs": [_cand("lorazepam", dose="0.5 mg", frequency="bid", indication="急性焦虑")],
    },
    {
        "id": "dept_dermatology_01",
        "title": "MTX + NSAIDs（银屑病）",
        "description": "银屑病系统治疗，甲氨蝶呤基础上加用布洛芬",
        "department": "dermatology",
        "patient": _patient(
            "dermatology",
            idx=23,
            age=42,
            gender="M",
            admission_type="OUTPATIENT",
            source_text="42岁男性，中重度斑块型银屑病，每周甲氨蝶呤；关节型皮损疼痛，拟短期布洛芬。",
            chief_complaint="皮损疼痛",
            history_present_illness="PASI 12，LFT 正常；无溃疡性结肠炎。",
            symptoms=["皮损疼痛", "瘙痒"],
            pmh=["银屑病"],
            diagnoses=[_dx("696.1", "银屑病")],
            current_medications=[_med("methotrexate", dose="15 mg", frequency="weekly")],
        ),
        "candidate_drugs": [_cand("ibuprofen", dose="400 mg", frequency="tid", indication="皮损相关疼痛")],
    },
    {
        "id": "dept_ophthalmology_01",
        "title": "噻吗洛尔滴眼液 + 口服 β 阻滞剂",
        "description": "青光眼已用局部 β 阻滞剂，再加口服美托洛尔存在叠加风险",
        "department": "ophthalmology",
        "patient": _patient(
            "ophthalmology",
            idx=24,
            age=60,
            gender="M",
            admission_type="OUTPATIENT",
            source_text="60岁男性，开角型青光眼，噻吗洛尔滴眼液控制眼压；合并高血压，心内科建议加美托洛尔。",
            chief_complaint="眼压控制尚可，血压偏高",
            history_present_illness="眼压 18 mmHg，BP 148/92 mmHg。",
            symptoms=[],
            pmh=["青光眼", "高血压"],
            diagnoses=[_dx("365.11", "原发性开角型青光眼"), _dx("401.9", "高血压")],
            current_medications=[_med("timolol", dose="0.5%", route="TOP", frequency="bid")],
        ),
        "candidate_drugs": [_cand("metoprolol", dose="25 mg", frequency="bid", indication="高血压")],
    },
    {
        "id": "dept_ent_01",
        "title": "急性咽炎：青霉素过敏 + 阿莫西林",
        "description": "链球菌咽炎候选阿莫西林，明确青霉素过敏史，应触发过敏禁忌",
        "department": "ent",
        "patient": _patient(
            "ent",
            idx=25,
            age=26,
            gender="F",
            admission_type="URGENT",
            source_text="26岁女性，急性咽炎，链球菌快速检测阳性；既往青霉素过敏（皮疹），耳鼻喉科拟阿莫西林。",
            chief_complaint="咽痛发热 2 天",
            history_present_illness="咽部充血，扁桃体渗出；体温 37.8℃。",
            symptoms=["咽痛", "发热", "吞咽痛"],
            pmh=["青霉素过敏"],
            diagnoses=[_dx("462", "急性咽炎")],
            current_medications=[_med("loratadine", dose="10 mg", frequency="qd")],
            allergies=["penicillin", "青霉素"],
        ),
        "candidate_drugs": [_cand("amoxicillin", dose="500 mg", frequency="tid", indication="急性咽炎")],
    },
    {
        "id": "dept_rehabilitation_01",
        "title": "卒中二级预防：双抗",
        "description": "缺血性卒中后康复，阿司匹林基础上加用氯吡格雷",
        "department": "rehabilitation",
        "patient": _patient(
            "rehabilitation",
            idx=26,
            age=72,
            gender="M",
            admission_type="REHAB",
            source_text="72岁男性，急性缺血性卒中后 3 周康复期，已阿司匹林及他汀；神经科建议加氯吡格雷双抗。",
            chief_complaint="卒中后肢体康复",
            history_present_illness="mRS 3，NIHSS 遗留轻度偏瘫；无活动性出血。",
            symptoms=["左侧肢体无力", "步态不稳"],
            pmh=["缺血性卒中", "高血压", "高脂血症"],
            diagnoses=[_dx("434.91", "缺血性卒中"), _dx("401.9", "高血压")],
            current_medications=[
                _med("aspirin", dose="100 mg", frequency="qd"),
                _med("atorvastatin", dose="20 mg", frequency="qd"),
                _med("metoprolol", dose="25 mg", frequency="bid"),
            ],
        ),
        "candidate_drugs": [_cand("clopidogrel", dose="75 mg", frequency="qd", indication="卒中二级预防")],
    },
    {
        "id": "dept_general_internal_safe_01",
        "title": "高血压联合用药（阴性对照）",
        "description": "标准 CCB+ACEI 联合降压，信息完整，预期无高风险命中",
        "department": "general_internal",
        "patient": _patient(
            "general_internal",
            idx=27,
            age=55,
            gender="M",
            admission_type="OUTPATIENT",
            source_text="55岁男性，原发性高血压，氨氯地平控制欠佳，拟加用 ACEI 联合降压。",
            chief_complaint="血压控制不佳",
            history_present_illness="家庭血压 150/95 mmHg，无蛋白尿及血钾异常；eGFR 85。",
            symptoms=[],
            pmh=["高血压"],
            diagnoses=[_dx("401.9", "原发性高血压")],
            current_medications=[_med("amlodipine", dose="5 mg", frequency="qd")],
            egfr=85.0,
        ),
        "candidate_drugs": [_cand("lisinopril", dose="10 mg", frequency="qd", indication="高血压")],
    },
    {
        "id": "dept_pharmacy_02",
        "title": "高警示：胰岛素剂量审查",
        "description": "临床药师会诊：2 型糖尿病住院患者胰岛素加量，审查低血糖风险",
        "department": "pharmacy",
        "patient": _patient(
            "pharmacy",
            idx=28,
            age=58,
            gender="F",
            admission_type="INPATIENT",
            source_text="58岁女性，2 型糖尿病入院调糖，已用基础胰岛素；因空腹血糖 12 mmol/L 拟加用格列本脲。",
            chief_complaint="血糖控制不佳",
            history_present_illness="HbA1c 9.1%，eGFR 88；无低血糖史。",
            symptoms=["多饮", "乏力"],
            pmh=["2 型糖尿病"],
            diagnoses=[_dx("250.00", "2 型糖尿病")],
            current_medications=[_med("insulin glargine", dose="20 U", route="SC", frequency="qd")],
            egfr=88.0,
        ),
        "candidate_drugs": [_cand("glibenclamide", dose="5 mg", frequency="qd", indication="2 型糖尿病")],
    },
    {
        "id": "dept_pharmacy_03",
        "title": "高警示：甲氨蝶呤监测",
        "description": "风湿科会诊：甲氨蝶呤每周方案，审查骨髓抑制与 DDI",
        "department": "pharmacy",
        "patient": _patient(
            "pharmacy",
            idx=29,
            age=54,
            gender="M",
            admission_type="OUTPATIENT",
            source_text="54岁男性，类风湿关节炎每周甲氨蝶呤；因上呼吸道感染拟加复方磺胺甲噁唑。",
            chief_complaint="发热咳嗽",
            history_present_illness="DAS28 3.8，肝肾功能正常；无磺胺过敏史。",
            symptoms=["发热", "咳嗽"],
            pmh=["类风湿关节炎"],
            diagnoses=[_dx("714.0", "类风湿关节炎"), _dx("486", "上呼吸道感染")],
            current_medications=[
                _med("methotrexate", dose="15 mg", frequency="weekly"),
                _med("folic acid", dose="5 mg", frequency="weekly"),
            ],
        ),
        "candidate_drugs": [_cand("trimethoprim sulfamethoxazole", dose="960 mg", frequency="bid", indication="上呼吸道感染")],
    },
]


def _normalize_bench_department(raw: str, catalog_ids: frozenset[str]) -> str:
    dept = BENCH_DEPT_ALIAS.get(raw.strip(), raw.strip())
    return dept if dept in catalog_ids else ""


def _enrich_benchmark_patient(pc: dict[str, Any], description: str, dept_id: str) -> dict[str, Any]:
    out = dict(pc)
    out["department"] = dept_id
    if not out.get("admission_type"):
        out["admission_type"] = "INPATIENT"
    if not out.get("allergies"):
        out["allergies"] = ["NKDA"]
    if not out.get("missing_fields"):
        out["missing_fields"] = []
    if not out.get("lactation_status"):
        out["lactation_status"] = "not_lactating"
    if not out.get("pregnancy_status"):
        out["pregnancy_status"] = "not_applicable"
    if not str(out.get("source_text") or "").strip():
        age = out.get("age")
        gender = out.get("gender")
        gender_cn = "男" if gender == "M" else "女" if gender == "F" else ""
        age_part = f"{age}岁" if age else ""
        out["source_text"] = f"{age_part}{gender_cn}性患者，{description.strip()}"
    if not str(out.get("chief_complaint") or "").strip():
        out["chief_complaint"] = description.strip()[:80]
    out.setdefault("symptoms_or_complaints", [])
    out.setdefault("past_medical_history", [])
    out.setdefault("history_present_illness", "")
    for med in out.get("current_medications", []):
        if isinstance(med, dict):
            med.setdefault("ingredient", med.get("name", ""))
            med.setdefault("route", "PO")
            med.setdefault("frequency", "qd")
    return out


def build_benchmark_template_cases() -> list[dict]:
    """Import Stage 9/11 benchmark cases as loadable case templates (per-dept extras)."""
    catalog = load_json(datasets_path("departments/catalog.json"))
    catalog_ids = frozenset(
        item["dept_id"] for item in catalog.get("departments", []) if item.get("dept_id")
    )
    primary_ids = {f"dept_{d}_01" for d in catalog_ids}
    cases: list[dict] = []
    seen: set[str] = set()

    if not BENCHMARK_CASES_DIR.is_dir():
        return cases

    for path in sorted(BENCHMARK_CASES_DIR.glob("*.json")):
        name = path.name
        if name.startswith("negative_safe_"):
            continue
        data = load_json(path)
        if not isinstance(data, dict):
            continue
        req = data.get("request")
        if not isinstance(req, dict):
            continue
        pc_raw = req.get("patient_context")
        if not isinstance(pc_raw, dict):
            continue
        dept_id = _normalize_bench_department(str(data.get("department") or ""), catalog_ids)
        if not dept_id:
            dept_id = _normalize_bench_department(str(pc_raw.get("department") or ""), catalog_ids)
        if not dept_id:
            continue

        template_id = str(data.get("case_id") or data.get("id") or path.stem)
        if template_id in seen or template_id in primary_ids:
            continue
        seen.add(template_id)

        description = str(data.get("description") or template_id)
        title = description.split("。")[0].split("：")[-1].strip() or template_id
        patient = _enrich_benchmark_patient(pc_raw, description, dept_id)
        candidates = list(req.get("candidate_drugs") or [])
        for cand in candidates:
            if isinstance(cand, dict):
                cand.setdefault("ingredient", cand.get("name", ""))
                cand.setdefault("route", "PO")
                cand.setdefault("frequency", "qd")
                cand.setdefault("source", "candidate")

        cases.append(
            {
                "id": template_id,
                "title": title[:120],
                "description": description,
                "department": dept_id,
                "category": dept_id,
                "request": {
                    "patient_context": patient,
                    "candidate_drugs": candidates,
                    "persist": False,
                },
            }
        )

    return cases


def _wrap_case(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "title": item["title"],
        "description": item["description"],
        "department": item["department"],
        "category": item["department"],
        "request": {
            "patient_context": item["patient"],
            "candidate_drugs": item["candidate_drugs"],
            "persist": False,
        },
    }


def build_department_cases() -> list[dict]:
    catalog = load_json(datasets_path("departments/catalog.json"))
    dept_ids = [item["dept_id"] for item in catalog.get("departments", []) if item.get("dept_id")]
    by_dept_primary: dict[str, dict[str, Any]] = {}
    extras: list[dict[str, Any]] = []
    for item in DEPT_RICH_CASES:
        dept = item["department"]
        if dept in dept_ids and dept not in by_dept_primary:
            by_dept_primary[dept] = item
        else:
            extras.append(item)
    missing = [d for d in dept_ids if d not in by_dept_primary]
    if missing:
        raise SystemExit(f"Missing rich scenarios for: {', '.join(missing)}")
    ordered = [_wrap_case(by_dept_primary[d]) for d in dept_ids]
    ordered.extend(_wrap_case(item) for item in extras)
    return ordered


def validate_templates(cases: list[dict], *, min_evidence: int = 0, label: str = "") -> None:
    engine = ReviewEngine()
    weak: list[str] = []
    for case in cases:
        case_id = case.get("id") or case.get("case_id") or ""
        if case_id in NEGATIVE_TEMPLATE_IDS:
            continue
        req = case.get("request") or case
        pc = PatientContext.model_validate(req["patient_context"])
        cds = [CandidateDrug.model_validate(c) for c in req.get("candidate_drugs", [])]
        out = engine.review(pc, cds)
        if len(out.evidence) < min_evidence and not out.need_clarification:
            weak.append(f"{case_id}: 0 证据且无澄清")
        elif len(out.evidence) == 0 and out.need_clarification and "allergies" in out.clarification_targets and not pc.allergies:
            weak.append(f"{case_id}: 仅因过敏缺失而澄清")
    if weak and min_evidence > 0:
        print(f"Warning ({label}):", *weak, sep="\n  - ")


def enrich_rule_review_samples() -> None:
    """Add clinical narrative fields to rule_review_samples.json cases."""
    data = load_json(RULE_SAMPLES)
    enrichments: dict[str, dict[str, Any]] = {
        "R01_ddi_warfarin_ibuprofen": {
            "source_text": "67岁男性，房颤长期华法林及阿司匹林，因胸痛拟加布洛芬。",
            "chief_complaint": "胸痛",
            "history_present_illness": "胸痛 2 天，INR 2.3。",
            "symptoms_or_complaints": ["胸痛"],
            "past_medical_history": ["房颤", "冠心病"],
            "diagnoses": [_dx("427.31", "心房颤动"), _dx("410.71", "急性冠脉综合征")],
            "admission_type": "EMERGENCY",
        },
        "R02_ddi_warfarin_aspirin": {
            "source_text": "72岁男性，房颤华法林抗凝，拟加阿司匹林双抗。",
            "chief_complaint": "房颤",
            "diagnoses": [_dx("427.31", "心房颤动")],
            "admission_type": "INPATIENT",
        },
        "R03_ddi_clarithromycin_simvastatin": {
            "source_text": "58岁男性，高脂血症口服辛伐他汀，因肺炎拟加克拉霉素。",
            "chief_complaint": "发热咳嗽",
            "diagnoses": [_dx("272.4", "高脂血症"), _dx("486", "肺炎")],
            "admission_type": "INPATIENT",
        },
        "R04_allergy_penicillin_amoxicillin": {
            "source_text": "40岁女性，青霉素过敏史明确，拟阿莫西林抗感染。",
            "chief_complaint": "发热",
            "diagnoses": [_dx("486", "肺炎")],
        },
        "R05_allergy_nsaid_ibuprofen": {
            "source_text": "45岁男性，阿司匹林/NSAIDs 过敏，拟布洛芬止痛。",
            "chief_complaint": "关节痛",
            "diagnoses": [_dx("715.90", "骨关节炎")],
        },
        "R06_pregnancy_lisinopril": {
            "source_text": "30岁女性，已确认妊娠，误开赖诺普利。",
            "chief_complaint": "妊娠期高血压",
            "diagnoses": [_dx("642.3", "妊娠期高血压")],
            "admission_type": "INPATIENT",
        },
        "R07_child_aspirin": {
            "source_text": "8岁男童，病毒性感染后拟阿司匹林（儿童禁忌）。",
            "chief_complaint": "发热",
            "diagnoses": [_dx("780.60", "发热")],
            "weight_kg": 28.0,
        },
        "R08_dup_acetaminophen": {
            "source_text": "55岁女性，已服泰诺，再加对乙酰氨基酚。",
            "chief_complaint": "头痛",
            "diagnoses": [_dx("784.0", "头痛")],
        },
        "R09_clarify_allergy_missing": {
            "source_text": "34岁女性，社区肺炎，过敏史未记录，拟阿莫西林。",
            "chief_complaint": "发热咳嗽",
            "diagnoses": [_dx("486", "社区获得性肺炎")],
            "allergies": [],
            "missing_fields": ["allergies"],
        },
        "R10_clarify_pregnancy_unknown": {
            "source_text": "28岁育龄女性，高血压，妊娠状态未明，拟 ACEI。",
            "chief_complaint": "血压升高",
            "diagnoses": [_dx("401.9", "高血压")],
            "pregnancy_status": "unknown",
        },
        "R11_chinese_alias": {
            "source_text": "70岁男性，中文医嘱：华法林基础上加布洛芬。",
            "chief_complaint": "关节痛",
            "diagnoses": [_dx("427.31", "心房颤动")],
        },
        "R12_no_rule_coverage": {
            "source_text": "60岁男性，美托洛尔基础上加氯吡格雷。",
            "chief_complaint": "PCI 术后",
            "diagnoses": [_dx("414.01", "冠心病")],
        },
    }
    for case in data.get("cases", []):
        cid = case.get("id", "")
        req = case.setdefault("request", {})
        pc = req.setdefault("patient_context", {})
        if cid in enrichments:
            extra = dict(enrichments[cid])
            allergies_override = extra.pop("allergies", None)
            missing_override = extra.pop("missing_fields", None)
            pc.update(extra)
            if allergies_override is not None:
                pc["allergies"] = allergies_override
            if missing_override is not None:
                pc["missing_fields"] = missing_override
        if cid not in {"R09_clarify_allergy_missing"} and not pc.get("allergies"):
            pc["allergies"] = ["NKDA"]
        pc.setdefault("missing_fields", [])
        pc.setdefault("lactation_status", "not_lactating")
        pc.setdefault("department", case.get("department", ""))
        pc.setdefault("admission_type", "INPATIENT")
        for med in pc.get("current_medications", []):
            med.setdefault("ingredient", med.get("name", ""))
            med.setdefault("route", "PO")
            med.setdefault("frequency", "qd")
        for cand in req.get("candidate_drugs", []):
            cand.setdefault("ingredient", cand.get("name", ""))
            cand.setdefault("route", "PO")
            cand.setdefault("frequency", "qd")
            cand.setdefault("source", "candidate")
    save_json(data, RULE_SAMPLES)


def write_stage11_clinical_cases() -> None:
    """Replace sparse stage11 demo cases with rule-review-ready payloads."""
    picks = {
        "clinical_cardio_polypharmacy_01": "dept_cardiology_01",
        "clinical_neuro_epilepsy_01": "dept_neurology_01",
        "clinical_oncology_chemo_01": "dept_oncology_02",
        "clinical_respiratory_severe_01": "dept_respiratory_02",
        "clinical_infectious_severe_01": "dept_infectious_disease_02",
        "clinical_safe_htn_01": "dept_general_internal_safe_01",
    }
    dept_cases = {c["id"]: c for c in build_department_cases()}
    stage11_cases = []
    for case_id, dept_id in picks.items():
        src = dept_cases[dept_id]
        stage11_cases.append(
            {
                "case_id": case_id,
                "title": src["title"],
                "description": src["description"],
                "department": src["department"],
                "category": src["category"],
                "request": src["request"],
            }
        )
    save_json({"cases": stage11_cases}, STAGE11_OUTPUT)


def main() -> None:
    cases = build_department_cases()
    payload = {
        "description": "各科室默认病例模板 — 完整临床上下文，可直接运行规则审查",
        "cases": cases,
    }
    save_json(payload, OUTPUT)
    print(f"Wrote {len(cases)} department templates to {OUTPUT}")

    bench_cases = build_benchmark_template_cases()
    bench_payload = {
        "description": "各科室扩展病例模板 — 由 benchmark 病例转换，补充科室规则场景库",
        "cases": bench_cases,
    }
    save_json(bench_payload, BENCHMARK_TEMPLATES_OUTPUT)
    print(f"Wrote {len(bench_cases)} benchmark-derived templates to {BENCHMARK_TEMPLATES_OUTPUT}")

    validate_templates(cases, min_evidence=1, label="department")
    enrich_rule_review_samples()
    print(f"Enriched {RULE_SAMPLES}")
    write_stage11_clinical_cases()
    print(f"Updated {STAGE11_OUTPUT}")

    missing = departments_missing_templates()
    if missing:
        raise SystemExit(f"Departments still missing templates: {', '.join(missing)}")
    missing_primary = departments_missing_primary_templates()
    if missing_primary:
        raise SystemExit(f"Departments missing primary dept_*_01 template: {', '.join(missing_primary)}")
    print(f"Coverage OK: {len(list_case_templates())} templates total")


if __name__ == "__main__":
    main()
