export type RiskLevel = 'none' | 'low' | 'medium' | 'high' | 'unknown'

export interface DrugItem {
  name: string
  ingredient?: string
  dose?: string
  route?: string
  frequency?: string
  indication?: string
  source?: string
}

export interface PatientContext {
  gender: string
  age?: number | null
  pregnancy_status?: string
  allergies?: string[]
  current_medications?: DrugItem[]
  missing_fields?: string[]
  chief_complaint?: string
  symptoms_or_complaints?: string[]
  diagnoses?: { name: string; icd9_code?: string }[]
  source_text?: string
}

export interface RuleEvidence {
  rule_id: string
  category: string
  risk_level: RiskLevel
  summary: string
  mechanism?: string
  recommendation?: string
  alternatives?: string[]
}

export interface ReviewOutput {
  risk_level: RiskLevel
  block_decision: boolean
  risk_reasons: string[]
  alternative_suggestions: string[]
  need_clarification: boolean
  clarification_targets: string[]
  evidence: RuleEvidence[]
  final_recommendation: string
}

export interface AgentOpinion {
  agent_id: string
  agent_name: string
  role: string
  risk_level: RiskLevel
  block_decision: boolean
  reasons: string[]
  alternatives: string[]
  need_clarification: boolean
  clarification_targets: string[]
  confidence: number
  evidence_cited: string[]
  summary: string
}

export interface ArbitrationResult {
  consensus_risk_level: RiskLevel
  consensus_block_decision: boolean
  agent_opinions: AgentOpinion[]
  dissenting_opinions: AgentOpinion[]
  conflict_detected: boolean
  arbitration_notes: string
  final_recommendation: string
  need_clarification: boolean
  clarification_targets: string[]
  rule_evidence: RuleEvidence[]
}

export interface ClarifyQuestion {
  field: string
  question: string
  reason: string
  priority: 'high' | 'medium' | 'low'
}

export interface ClarifyOutput {
  status: 'need_user_input' | 'conservative_fallback' | 'complete'
  questions: ClarifyQuestion[]
  priority_missing_fields: string[]
  conservative_advice?: {
    summary: string
    actions: string[]
    disclaimer: string
  } | null
  final_message: string
}

export interface MultiConsultResponse {
  case_id?: string | null
  extract_output?: Record<string, unknown> | null
  rule_output: ReviewOutput
  agent_opinions: AgentOpinion[]
  debate?: DebateResult | null
  safety_panel?: SafetyPanelResult | null
  arbitration: ArbitrationResult
  clarify_output?: ClarifyOutput | null
  final_recommendation: string
}

export interface CriticOutput {
  round_number: number
  overall_assessment: string
  consensus_reached: boolean
  dissent_log: string[]
  low_confidence_agents: string[]
  min_confidence: number
}

export interface DebateRoundRecord {
  round_number: number
  agent_opinions: AgentOpinion[]
  critic_output?: CriticOutput | null
  min_confidence: number
}

export interface ModeratorSynthesis {
  consistency_notes: string[]
  conflict_notes: string[]
  integration_summary: string
  recommended_risk_level: RiskLevel
  recommended_block: boolean
}

export interface SafetyFlag {
  severity: RiskLevel
  category: string
  description: string
  recommendation: string
  rule_id: string
}

export interface SafetyPanelResult {
  passed: boolean
  risk_level: RiskLevel
  block_recommended: boolean
  flags: SafetyFlag[]
  summary: string
}

export interface DebateResult {
  enabled: boolean
  rounds: DebateRoundRecord[]
  moderator_synthesis?: ModeratorSynthesis | null
  final_consensus: boolean
  flagged_for_human: boolean
  min_confidence: number
  duration_ms: number
  llm_calls_estimate: number
}

export interface CaseLog {
  case_id: string
  status: string
  created_at: string
  updated_at: string
  raw_input_text?: string
  patient_context?: PatientContext
  candidate_drugs?: DrugItem[]
  review_output?: ReviewOutput
  agent_opinions?: AgentOpinion[]
  arbitration?: ArbitrationResult
  clarify_output?: ClarifyOutput
  final_recommendation?: string
  events?: { stage: string; timestamp: string; payload: unknown }[]
}

export interface HealthResponse {
  status: string
  version: string
  uptime_seconds: number
  llm_configured?: boolean
  llm_provider: string
  vision_llm_configured?: boolean
}

export interface AgentInfo {
  agent_id: string
  agent_name: string
  role: string
}

export interface CaseTemplate {
  id: string
  title: string
  description: string
  category: string
  department: string
  department_name_cn: string
  input_mode: 'text' | 'context'
  text?: string
  patient_context?: PatientContext
  candidate_drugs: DrugItem[]
}

export type ModelId =
  | 'totalsegmentator'
  | 'vista3d'
  | 'sam_med3d'
  | 'sam2d'
  | 'cxr_lesion'
  | 'brats_tumor'

export interface SegModelInfo {
  model_id: ModelId
  name: string
  description: string
  modalities: string[]
  dim: string
  task?: string
  organs: string[]
  datasets?: string[]
  weights_present: boolean
}

export interface ImagingStudy {
  study_id: string
  patient_id: string
  modality: string
  source: string
  title: string
  image_paths: string[]
  volume_path?: string | null
  slice_count: number
  collection?: string
  report_text?: string
  cxr_id?: string
}

export type VolumeAxis = 'axial' | 'coronal' | 'sagittal'

export interface VolumeMeta {
  volume_path: string
  shape: number[]
  spacing: number[]
  slice_counts: Record<VolumeAxis, number>
  modality: string
}

export interface SegmentResultItem {
  model_id: string
  source_image: string
  overlay_path: string
  labels: string[]
  stats: Record<string, unknown>
  memory_mb: number
  duration_ms: number
  notes: string
}

export interface SegmentRunRecord {
  run_id: string
  patient_id: string
  study_id: string
  image_key: string
  source_image: string
  volume_path?: string | null
  slice_axis: string
  slice_index?: number | null
  organ: string
  model_ids: string[]
  results: SegmentResultItem[]
  memory_peak_mb: number
  created_at: string
}

export interface VlmAnalysis {
  clinical_analysis?: string
  imaging_findings?: string
  medication_recommendation?: string
  recommended_drugs?: DrugItem[]
  allergies?: string[]
  diagnoses?: string[]
  symptoms?: string[]
  chief_complaint?: string
  anesthesia_surgery?: string
  reasoning?: string
  risk_level?: string
  [key: string]: unknown
}

export interface ReportParagraph {
  paragraph_id: string
  section: string
  title: string
  content: string
  order: number
}

export interface ReportSupplement {
  supplement_id: string
  timestamp: string
  question: string
  answer: string
  related_paragraph_ids: string[]
}

export interface ClinicalReport {
  report_id: string
  user_id?: string
  patient_id: string
  imaging_session_id: string
  modalities: string[]
  status: string
  created_at: string
  updated_at: string
  paragraphs: ReportParagraph[]
  supplements: ReportSupplement[]
  chain_of_thought: string
  image_paths: string[]
  overlay_paths: string[]
  screenshot_paths: string[]
  metadata: Record<string, unknown>
}

export interface DepartmentInfo {
  dept_id: string
  name_cn: string
  name_en?: string
  nav_routes?: string[]
  description?: string
}

export interface DepartmentContextResponse {
  dept_id: string
  name_cn: string
  name_en?: string
  description?: string
  review_config?: Record<string, unknown>
  core_formulary?: string[]
  nav_routes?: string[]
}

export interface DepartmentStatsResponse {
  dept_id: string
  reviews_today: number
  alerts_today: number
  overrides_today: number
  pending_queue: number
  top_alerts: { summary: string; count: number }[]
}

export interface UserProfile {
  user_id: string
  username: string
  display_name: string
  role: string
  dept_id: string
  department?: DepartmentInfo | null
}

export interface AgentSkillInfo {
  skill_id: string
  title: string
  description?: string
  builtin?: boolean
  enabled?: boolean
}

export interface AgentConfigInfo {
  agent_id: string
  agent_name: string
  role: string
  enabled?: boolean
  is_department_agent?: boolean
  available_skills?: AgentSkillInfo[]
  enabled_skills?: string[]
}

export interface DoctorWorkspace {
  profile: UserProfile
  agents: AgentConfigInfo[]
  custom_skills: Record<string, unknown>[]
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in_hours: number
}

export type AlertDecisionAction = 'acknowledge' | 'override' | 'escalate' | 'hold'
export type RiskAcceptance = 'low' | 'medium' | 'high'

export interface CpoeReviewAlert {
  alert_id: string
  order_id?: string
  rule_id: string
  alert_level: 'info' | 'warning' | 'hard_stop'
  category?: string
  summary: string
  recommendation?: string
  display_name?: string
  implicated_drugs?: string[]
  overridable?: boolean
}

export interface CpoePatientSnapshot {
  patient_id?: string
  age?: number | null
  gender?: string
  weight_kg?: number | null
  egfr?: number | null
  allergies?: string[]
  conditions?: string[]
  pregnancy_status?: string
  lactation_status?: string
}

export interface CpoeMedicationOrder {
  order_id: string
  hospital_drug_id?: string
  display_name?: string
  ingredient?: string
  dose?: string
  route?: string
  frequency?: string
  status?: string
}

export interface CpoeMedicationReviewResponse {
  encounter_id?: string
  overall_status: 'passed' | 'warning' | 'blocked'
  requires_pharmacist_review: boolean
  alerts: CpoeReviewAlert[]
  unresolved_drugs?: string[]
  review_output?: ReviewOutput
  formulary_drug_count?: number
  department?: string
  department_focus_categories?: string[]
}

export interface AlertDecision {
  alert_id: string
  action: AlertDecisionAction
  override_reason?: string | null
  override_risk_acceptance?: RiskAcceptance | null
  pharmacist_notes?: string | null
  decided_at: string
  pharmacist_id?: string
}

export interface PharmacistReview {
  review_id: string
  encounter_id?: string
  patient_id?: string
  department?: string
  status: 'pending' | 'reviewed' | 'expired'
  created_at: string
  reviewed_at?: string | null
  cpoe_response: CpoeMedicationReviewResponse
  alert_decisions: AlertDecision[]
  max_alert_level?: string
}

export interface PharmacyQueueItem {
  review_id: string
  encounter_id?: string
  patient_id?: string
  department?: string
  created_at: string
  status: string
  max_alert_level: string
  alert_count: number
  wait_minutes: number
}

export interface OverrideAuditLog {
  log_id: string
  review_id: string
  alert_id: string
  drug_name: string
  alert_level: string
  action: string
  override_reason: string
  risk_acceptance: string
  timestamp: string
  pharmacist_name: string
}

export interface PharmacyStats {
  pending_count: number
  override_rate: number
  high_risk_override_rate: number
  top_override_drugs: { drug_name: string; count: number }[]
}

export interface HospitalDrug {
  hospital_drug_id: string
  generic_name_cn: string
  generic_name_en: string
  trade_name_cn: string
  strength: string
  dosage_form: string
  route: string
  atc_code: string
  rxnorm_rxcui: string
  insurance_code?: string
  manufacturer: string
  in_formulary: boolean
  in_stock: boolean
  high_alert: boolean
  antibiotic_level: string
  narcotic_class: string
  restricted_dept: string
  alternatives?: string[]
  canonical_key?: string
  sync_version?: string
  display_name?: string
}

export interface DrugCatalogStats {
  db_path?: string
  total_drugs: number
  in_formulary: number
  in_stock: number
  last_sync?: Record<string, unknown> | null
}

export interface AtcTreeNode {
  code: string
  level: number
  name_cn: string
  name_en: string
  drug_count: number
  children: AtcTreeNode[]
}

export interface DrugSpecialFilter {
  id: string
  name_cn: string
  name_en: string
}

export interface DrugSearchModelStatus {
  backend?: string
  provider?: string
  model?: string
  model_dir?: string
  base_url?: string
  model_present: boolean
  index_built: boolean
  indexed_drugs: number
  load_error?: string | null
  download_command?: string
}

export interface DrugInteractionInfo {
  drug: string
  severity: string
  effect?: string
  recommendation?: string
}

export interface DrugInfoResponse {
  name: string
  category?: string
  rx_type?: string
  brand_names?: string[]
  description?: string
  interactions?: DrugInteractionInfo[]
  contraindications?: unknown[]
  food_interactions?: unknown[]
  error?: string
}
