from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

RiskLevel = Literal["none", "low", "medium", "high", "unknown"]
ClarifyStatus = Literal["need_user_input", "conservative_fallback", "complete"]
QuestionPriority = Literal["high", "medium", "low"]
CaseStage = Literal[
    "extract",
    "rule_gate",
    "agent_review",
    "debate",
    "critic_review",
    "safety_panel",
    "arbitration",
    "review",
    "clarify",
    "final",
]
ReportSection = Literal[
    "clinical_analysis",
    "imaging_findings",
    "medication_recommendation",
    "pharmacy_assessment",
    "allergy_analysis",
    "anesthesia_surgery",
    "risk_summary",
]
ReportStatus = Literal["active", "superseded"]
ModelId = Literal[
    "totalsegmentator",
    "vista3d",
    "sam_med3d",
    "sam2d",
    "cxr_lesion",
    "brats_tumor",
]


class DrugItem(BaseModel):
    name: str = Field(default="")
    ingredient: str = Field(default="")
    dose: str = Field(default="")
    route: str = Field(default="")
    frequency: str = Field(default="")
    hospital_drug_id: str = Field(default="", description="院内药品码 (PIS/HIS)")


class CandidateDrug(DrugItem):
    indication: str = Field(default="")
    source: str = Field(default="candidate")


class DiagnosisItem(BaseModel):
    icd9_code: str = Field(default="")
    name: str = Field(default="")


class PatientContext(BaseModel):
    subject_id: Optional[int] = None
    hadm_id: Optional[int] = None
    gender: str = Field(default="unknown")
    age: Optional[int] = None
    admission_type: str = Field(default="")
    source_text: str = Field(default="")
    chief_complaint: str = Field(default="")
    history_present_illness: str = Field(default="")
    symptoms_or_complaints: List[str] = Field(default_factory=list)
    past_medical_history: List[str] = Field(default_factory=list)
    diagnoses: List[DiagnosisItem] = Field(default_factory=list)
    current_medications: List[DrugItem] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    pregnancy_status: str = Field(default="unknown")
    lactation_status: str = Field(default="unknown")
    weight_kg: Optional[float] = None
    egfr: Optional[float] = Field(default=None, description="eGFR mL/min/1.73m²")
    department: str = Field(default="", description="用户/患者所属科室 dept_id")
    missing_fields: List[str] = Field(default_factory=list)


class ExtractionOutput(BaseModel):
    age: Optional[int] = None
    gender: str = Field(default="unknown")
    pregnancy_status: str = Field(default="unknown")
    allergies: List[str] = Field(default_factory=list)
    symptoms_or_complaints: List[str] = Field(default_factory=list)
    diagnoses: List[str] = Field(default_factory=list)
    current_medications: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)


class RuleEvidence(BaseModel):
    rule_id: str
    category: str
    risk_level: RiskLevel
    summary: str
    mechanism: str = Field(default="")
    implicated_drugs: List[str] = Field(default_factory=list)
    recommendation: str = Field(default="")
    alternatives: List[str] = Field(default_factory=list)
    clarification_fields: List[str] = Field(default_factory=list)
    source: str = Field(default="minimal_rule_kb")


class ReviewOutput(BaseModel):
    risk_level: RiskLevel = "unknown"
    block_decision: bool = False
    risk_reasons: List[str] = Field(default_factory=list)
    alternative_suggestions: List[str] = Field(default_factory=list)
    need_clarification: bool = False
    clarification_targets: List[str] = Field(default_factory=list)
    evidence: List[RuleEvidence] = Field(default_factory=list)
    final_recommendation: str = Field(default="")


class ClarifyQuestion(BaseModel):
    field: str
    question: str
    reason: str
    priority: QuestionPriority = "medium"


class ConservativeAdvice(BaseModel):
    summary: str = Field(default="")
    actions: List[str] = Field(default_factory=list)
    disclaimer: str = Field(default="")


class ClarifyOutput(BaseModel):
    status: ClarifyStatus = "need_user_input"
    questions: List[ClarifyQuestion] = Field(default_factory=list)
    priority_missing_fields: List[str] = Field(default_factory=list)
    conservative_advice: Optional[ConservativeAdvice] = None
    final_message: str = Field(default="")


class ExtractRequest(BaseModel):
    text: str
    case_id: Optional[str] = None
    persist: bool = True


class ExtractResponse(BaseModel):
    case_id: Optional[str] = None
    raw_output: str
    parsed_output: Optional[dict] = None


class ReviewRequest(BaseModel):
    patient_context: PatientContext
    candidate_drugs: List[CandidateDrug] = Field(default_factory=list)
    retrieved_evidence: List[RuleEvidence] = Field(default_factory=list)
    case_id: Optional[str] = None
    persist: bool = True


class ReviewResponse(BaseModel):
    case_id: Optional[str] = None
    retrieved_evidence: List[RuleEvidence] = Field(default_factory=list)
    review_output: ReviewOutput


class ClarifyRequest(BaseModel):
    patient_context: PatientContext
    candidate_drugs: List[CandidateDrug] = Field(default_factory=list)
    review_output: ReviewOutput
    user_answers: Dict[str, str] = Field(default_factory=dict)
    unable_to_answer: bool = False
    case_id: Optional[str] = None
    persist: bool = True


class ClarifyResponse(BaseModel):
    case_id: Optional[str] = None
    clarify_output: ClarifyOutput


class ConsultRequest(BaseModel):
    text: str = Field(default="")
    patient_context: Optional[PatientContext] = None
    candidate_drugs: List[CandidateDrug] = Field(default_factory=list)
    unable_to_answer: bool = False
    case_id: Optional[str] = None
    persist: bool = True


class ConsultResponse(BaseModel):
    case_id: Optional[str] = None
    extract_output: Optional[ExtractionOutput] = None
    review_output: ReviewOutput
    clarify_output: ClarifyOutput
    final_recommendation: str


class AgentOpinion(BaseModel):
    agent_id: str
    agent_name: str
    role: str
    risk_level: RiskLevel = "unknown"
    block_decision: bool = False
    reasons: List[str] = Field(default_factory=list)
    alternatives: List[str] = Field(default_factory=list)
    need_clarification: bool = False
    clarification_targets: List[str] = Field(default_factory=list)
    confidence: float = 0.5
    evidence_cited: List[str] = Field(default_factory=list)
    summary: str = Field(default="")
    debate_round: int = Field(default=1, description="Opinion produced at debate round N")


class CriticOutput(BaseModel):
    round_number: int = 0
    ehr_contradictions: List[str] = Field(default_factory=list)
    evidence_gaps: List[str] = Field(default_factory=list)
    safety_misses: List[str] = Field(default_factory=list)
    overall_assessment: str = Field(default="")
    consensus_reached: bool = False
    dissent_log: List[str] = Field(default_factory=list)
    low_confidence_agents: List[str] = Field(default_factory=list)
    min_confidence: float = Field(default=1.0)


class DebateRoundRecord(BaseModel):
    round_number: int
    agent_opinions: List[AgentOpinion] = Field(default_factory=list)
    critic_output: Optional[CriticOutput] = None
    min_confidence: float = Field(default=1.0)


class ModeratorSynthesis(BaseModel):
    consistency_notes: List[str] = Field(default_factory=list)
    conflict_notes: List[str] = Field(default_factory=list)
    integration_summary: str = Field(default="")
    recommended_risk_level: RiskLevel = "unknown"
    recommended_block: bool = False
    majority_block_votes: int = 0
    total_agents: int = 0


class SafetyFlag(BaseModel):
    severity: RiskLevel = "medium"
    category: str = Field(default="")
    description: str = Field(default="")
    recommendation: str = Field(default="")
    rule_id: str = Field(default="")
    implicated_drugs: List[str] = Field(default_factory=list)


class SafetyPanelResult(BaseModel):
    passed: bool = True
    risk_level: RiskLevel = "none"
    block_recommended: bool = False
    flags: List[SafetyFlag] = Field(default_factory=list)
    ddi_hits: List[SafetyFlag] = Field(default_factory=list)
    summary: str = Field(default="")


class DebateResult(BaseModel):
    enabled: bool = True
    rounds: List[DebateRoundRecord] = Field(default_factory=list)
    moderator_synthesis: Optional[ModeratorSynthesis] = None
    final_opinions: List[AgentOpinion] = Field(default_factory=list)
    final_consensus: bool = False
    flagged_for_human: bool = False
    min_confidence: float = Field(default=1.0)
    duration_ms: float = Field(default=0.0)
    llm_calls_estimate: int = Field(default=0)


class ArbitrationResult(BaseModel):
    consensus_risk_level: RiskLevel = "unknown"
    consensus_block_decision: bool = False
    agent_opinions: List[AgentOpinion] = Field(default_factory=list)
    dissenting_opinions: List[AgentOpinion] = Field(default_factory=list)
    conflict_detected: bool = False
    arbitration_notes: str = Field(default="")
    final_recommendation: str = Field(default="")
    need_clarification: bool = False
    clarification_targets: List[str] = Field(default_factory=list)
    rule_evidence: List[RuleEvidence] = Field(default_factory=list)


class MultiReviewRequest(BaseModel):
    patient_context: PatientContext
    candidate_drugs: List[CandidateDrug] = Field(default_factory=list)
    unable_to_answer: bool = False
    case_id: Optional[str] = None
    persist: bool = True


class MultiReviewResponse(BaseModel):
    case_id: Optional[str] = None
    rule_output: ReviewOutput
    agent_opinions: List[AgentOpinion] = Field(default_factory=list)
    debate: Optional[DebateResult] = None
    safety_panel: Optional[SafetyPanelResult] = None
    arbitration: ArbitrationResult
    clarify_output: Optional[ClarifyOutput] = None
    final_recommendation: str = Field(default="")


class MultiConsultRequest(BaseModel):
    text: str = Field(default="")
    patient_context: Optional[PatientContext] = None
    candidate_drugs: List[CandidateDrug] = Field(default_factory=list)
    unable_to_answer: bool = False
    case_id: Optional[str] = None
    persist: bool = True


class MultiConsultResponse(BaseModel):
    case_id: Optional[str] = None
    extract_output: Optional[ExtractionOutput] = None
    rule_output: ReviewOutput
    agent_opinions: List[AgentOpinion] = Field(default_factory=list)
    debate: Optional[DebateResult] = None
    safety_panel: Optional[SafetyPanelResult] = None
    arbitration: ArbitrationResult
    clarify_output: Optional[ClarifyOutput] = None
    final_recommendation: str = Field(default="")


class CaseEvent(BaseModel):
    stage: CaseStage
    timestamp: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class CaseLog(BaseModel):
    case_id: str
    created_at: str
    updated_at: str
    status: str = Field(default="in_progress")
    raw_input_text: str = Field(default="")
    patient_context: Optional[PatientContext] = None
    candidate_drugs: List[CandidateDrug] = Field(default_factory=list)
    extract_output: Optional[ExtractionOutput] = None
    review_output: Optional[ReviewOutput] = None
    agent_opinions: List[AgentOpinion] = Field(default_factory=list)
    arbitration: Optional[ArbitrationResult] = None
    clarify_output: Optional[ClarifyOutput] = None
    final_recommendation: str = Field(default="")
    events: List[CaseEvent] = Field(default_factory=list)


class ReportParagraph(BaseModel):
    paragraph_id: str
    section: ReportSection
    title: str
    content: str
    order: int = 0


class ReportSupplement(BaseModel):
    supplement_id: str
    timestamp: str
    question: str
    answer: str
    related_paragraph_ids: List[str] = Field(default_factory=list)


class ClinicalReport(BaseModel):
    report_id: str
    patient_id: str
    imaging_session_id: str
    modalities: List[str] = Field(default_factory=list)
    status: ReportStatus = "active"
    created_at: str
    updated_at: str
    paragraphs: List[ReportParagraph] = Field(default_factory=list)
    supplements: List[ReportSupplement] = Field(default_factory=list)
    chain_of_thought: str = Field(default="")
    image_paths: List[str] = Field(default_factory=list)
    overlay_paths: List[str] = Field(default_factory=list)
    screenshot_paths: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ImagingStudyItem(BaseModel):
    study_id: str
    patient_id: str
    modality: str
    source: str
    title: str
    image_paths: List[str] = Field(default_factory=list)
    volume_path: Optional[str] = None
    slice_count: int = 0
    collection: str = Field(default="", description="NLMCXR | MIMIC-CXR | local")
    report_text: str = Field(default="", description="Radiology report text when available")
    cxr_id: str = Field(default="")


class SegmentRequest(BaseModel):
    image_path: str
    model_ids: List[ModelId] = Field(default_factory=list)
    organ: str = Field(default="brain")
    volume_path: Optional[str] = None
    slice_axis: str = Field(default="axial")
    slice_index: Optional[int] = None
    point: Optional[List[int]] = None
    bbox: Optional[List[int]] = None
    patient_id: str = Field(default="")
    study_id: str = Field(default="")
    persist: bool = Field(default=True)


class SegmentResultStored(BaseModel):
    model_id: str
    source_image: str
    overlay_path: str
    labels: List[str] = Field(default_factory=list)
    stats: Dict[str, Any] = Field(default_factory=dict)
    memory_mb: float = 0.0
    duration_ms: float = 0.0
    notes: str = ""


class SegmentRunRecord(BaseModel):
    run_id: str
    patient_id: str
    study_id: str
    image_key: str
    source_image: str
    volume_path: Optional[str] = None
    slice_axis: str = "axial"
    slice_index: Optional[int] = None
    organ: str = "brain"
    model_ids: List[str] = Field(default_factory=list)
    results: List[SegmentResultStored] = Field(default_factory=list)
    memory_peak_mb: float = 0.0
    created_at: str = ""


class ListSegmentRunsResponse(BaseModel):
    patient_id: str
    study_id: str
    image_key: str
    count: int
    runs: List[SegmentRunRecord] = Field(default_factory=list)


class VlmAnalyzeRequest(BaseModel):
    clinical_text: str = Field(default="")
    primary_modality: str = Field(default="CT")
    image_paths: List[str] = Field(default_factory=list)
    overlay_paths: List[str] = Field(default_factory=list)
    segmentation_summary: str = Field(default="")
    include_source_image: bool = Field(default=False)


class VlmAnalyzeResponse(BaseModel):
    analysis: Dict[str, Any] = Field(default_factory=dict)
    images_used: List[str] = Field(default_factory=list)
    model: str = ""
    configured: bool = True
    overlay_count: int = 0
    source_count: int = 0
    duration_ms: float = 0.0


class VolumeMetaResponse(BaseModel):
    volume_path: str
    shape: List[int]
    spacing: List[float]
    slice_counts: Dict[str, int]
    modality: str


class SegmentResponse(BaseModel):
    results: List[Dict[str, Any]] = Field(default_factory=list)
    memory_peak_mb: float = 0.0
    run_id: Optional[str] = None
    image_key: Optional[str] = None


class SaveScreenshotRequest(BaseModel):
    patient_id: str
    study_id: str
    image_data: str
    caption: str = Field(default="")


class GenerateReportRequest(BaseModel):
    patient_id: str
    clinical_text: str = Field(default="")
    primary_modality: str = Field(default="CT")
    modalities: List[str] = Field(default_factory=lambda: ["CT"])
    imaging_session_label: str = Field(default="")
    image_paths: List[str] = Field(default_factory=list)
    overlay_paths: List[str] = Field(default_factory=list)
    screenshot_paths: List[str] = Field(default_factory=list)
    models_used: List[str] = Field(default_factory=list)
    segmentation_summary: str = Field(default="")
    patient_context: Optional[PatientContext] = None
    candidate_drugs: List[CandidateDrug] = Field(default_factory=list)
    include_source_image: bool = Field(default=False)
    run_medication_review: bool = Field(default=False)


class ReportAskRequest(BaseModel):
    patient_id: str
    report_id: str
    question: str


class ReportAskResponse(BaseModel):
    answer: str
    related_paragraphs: List[ReportParagraph] = Field(default_factory=list)
    report: ClinicalReport


# ── CPOE / Hospital Formulary ───────────────────────────────────────────

AlertLevel = Literal["info", "warning", "hard_stop"]
CpoeOverallStatus = Literal["passed", "warning", "blocked"]


class CpoePatientSnapshot(BaseModel):
    patient_id: str = Field(default="")
    age: Optional[int] = None
    gender: str = Field(default="unknown")
    weight_kg: Optional[float] = None
    egfr: Optional[float] = None
    allergies: List[str] = Field(default_factory=list)
    conditions: List[str] = Field(default_factory=list)
    pregnancy_status: str = Field(default="unknown")
    lactation_status: str = Field(default="unknown")


class CpoeMedicationOrder(BaseModel):
    order_id: str
    hospital_drug_id: str = Field(default="")
    display_name: str = Field(default="", description="HIS 展示名，无院内码时使用")
    ingredient: str = Field(default="", description="处方成分名，优先于院目录 generic 解析")
    dose: str = Field(default="")
    route: str = Field(default="")
    frequency: str = Field(default="")
    status: str = Field(default="new")


class CpoeMedicationReviewRequest(BaseModel):
    encounter_id: str = Field(default="")
    patient: CpoePatientSnapshot
    orders: List[CpoeMedicationOrder] = Field(default_factory=list)
    existing_medications: List[DrugItem] = Field(default_factory=list)
    review_mode: str = Field(default="pre_save")
    department: str = Field(default="", description="审查科室上下文，缺省时由服务端从登录用户推断")


class CpoeReviewAlert(BaseModel):
    alert_id: str
    order_id: str = Field(default="")
    rule_id: str
    alert_level: AlertLevel = "warning"
    category: str = Field(default="")
    evidence_grade: str = Field(default="")
    summary: str
    recommendation: str = Field(default="")
    alternatives: List[str] = Field(default_factory=list)
    alternative_drug_ids: List[str] = Field(default_factory=list)
    implicated_drugs: List[str] = Field(default_factory=list)
    hospital_drug_id: str = Field(default="")
    display_name: str = Field(default="")
    overridable: bool = True


class CpoeMedicationReviewResponse(BaseModel):
    encounter_id: str = Field(default="")
    overall_status: CpoeOverallStatus = "passed"
    alerts: List[CpoeReviewAlert] = Field(default_factory=list)
    unresolved_drugs: List[str] = Field(default_factory=list)
    requires_pharmacist_review: bool = False
    review_output: Optional[ReviewOutput] = None
    knowledge_version: str = Field(default="")
    formulary_drug_count: int = 0
    department: str = Field(default="")
    department_focus_categories: List[str] = Field(default_factory=list)


class DepartmentContextResponse(BaseModel):
    dept_id: str
    name_cn: str = ""
    name_en: str = ""
    description: str = ""
    review_config: Dict[str, Any] = Field(default_factory=dict)
    core_formulary: List[str] = Field(default_factory=list)
    nav_routes: List[str] = Field(default_factory=list)


class DepartmentStatsResponse(BaseModel):
    dept_id: str
    reviews_today: int = 0
    alerts_today: int = 0
    overrides_today: int = 0
    pending_queue: int = 0
    top_alerts: List[Dict[str, Any]] = Field(default_factory=list)


class FormularySyncRequest(BaseModel):
    csv_path: str = Field(default="", description="相对项目根目录的 CSV 路径")
    sync_version: str = Field(default="")


class FormularySyncResponse(BaseModel):
    status: str
    sync_version: str = Field(default="")
    rows_total: int = 0
    rows_upserted: int = 0
    source_path: str = Field(default="")
    catalog_stats: Dict[str, Any] = Field(default_factory=dict)


class MimicPatientSummary(BaseModel):
    subject_id: int
    hadm_id: int
    gender: str = Field(default="unknown")
    age: Optional[int] = None
    admission_type: str = Field(default="")
    diagnosis_count: int = 0
    medication_count: int = 0
    has_chief_complaint: bool = False
    has_allergies: bool = False


class MimicPatientListResponse(BaseModel):
    total: int
    offset: int
    limit: int
    items: List[MimicPatientSummary] = Field(default_factory=list)


class MimicDataStatsResponse(BaseModel):
    raw_dir: str
    raw_available: bool
    raw_tables_present: int
    raw_tables_required: int
    processed_path: str
    processed_available: bool
    context_count: int = 0
    with_clinical_notes: int = 0
    with_medications: int = 0
    with_diagnoses: int = 0
    age_min: Optional[int] = None
    age_max: Optional[int] = None
