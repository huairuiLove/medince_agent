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
  llm_provider: string
}

export interface AgentInfo {
  agent_id: string
  agent_name: string
  role: string
}

export interface DemoCase {
  id: string
  title: string
  description: string
  mode: 'text' | 'context'
  text?: string
  patient_context?: PatientContext
  candidate_drugs: DrugItem[]
}

export type ModelId = 'totalsegmentator' | 'vista3d' | 'sam_med3d' | 'sam2d'

export interface SegModelInfo {
  model_id: ModelId
  name: string
  description: string
  modalities: string[]
  dim: string
  organs: string[]
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
