from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

RiskLevel = Literal["none", "low", "medium", "high", "unknown"]
ClarifyStatus = Literal["need_user_input", "conservative_fallback", "complete"]
QuestionPriority = Literal["high", "medium", "low"]
CaseStage = Literal[
    "extract", "rule_gate", "agent_review", "arbitration", "review", "clarify", "final"
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
ModelId = Literal["totalsegmentator", "vista3d", "sam_med3d", "sam2d"]


class DrugItem(BaseModel):
    name: str = Field(default="")
    ingredient: str = Field(default="")
    dose: str = Field(default="")
    route: str = Field(default="")
    frequency: str = Field(default="")


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


class SegmentRequest(BaseModel):
    image_path: str
    model_ids: List[ModelId] = Field(default_factory=list)
    organ: str = Field(default="brain")
    point: Optional[List[int]] = None
    bbox: Optional[List[int]] = None


class SegmentResponse(BaseModel):
    results: List[Dict[str, Any]] = Field(default_factory=list)
    memory_peak_mb: float = 0.0


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


class ReportAskRequest(BaseModel):
    patient_id: str
    report_id: str
    question: str


class ReportAskResponse(BaseModel):
    answer: str
    related_paragraphs: List[ReportParagraph] = Field(default_factory=list)
    report: ClinicalReport
