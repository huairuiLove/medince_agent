import type {
  AgentInfo,
  AlertDecisionAction,
  CaseLog,
  CaseSummary,
  CaseTemplate,
  ClarifyOutput,
  ClinicalReport,
  CpoeMedicationOrder,
  CpoeMedicationReviewResponse,
  DepartmentContextResponse,
  DepartmentStatsResponse,
  CpoePatientSnapshot,
  DepartmentInfo,
  DoctorWorkspace,
  HealthResponse,
  ImagingStudy,
  MimicDataStatsResponse,
  MimicPatientListResponse,
  ModelId,
  MultiConsultResponse,
  OverrideAuditLog,
  PatientContext,
  PharmacistReview,
  PharmacyQueueItem,
  PharmacyStats,
  ReportParagraph,
  ReviewOutput,
  RiskAcceptance,
  SegModelInfo,
  SegmentResponse,
  SegmentResultItem,
  SegmentRunRecord,
  AtcTreeNode,
  DrugCatalogStats,
  DrugInfoResponse,
  DrugItem,
  DrugSearchModelStatus,
  DrugSpecialFilter,
  HospitalDrug,
  TokenResponse,
  VolumeAxis,
  VolumeMeta,
  VlmAnalysis,
} from '@/types'

const BASE = import.meta.env.VITE_API_BASE ?? ''
const TOKEN_KEY = 'medsafe_token'

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
      ...init,
    })
  } catch (e) {
    const hint =
      BASE
        ? `无法连接后端 ${BASE}，请确认 API 已启动且地址正确`
        : '无法连接后端，请运行 bash scripts/start.sh 启动完整项目'
    if (e instanceof Error && e.name === 'AbortError') {
      throw new Error('请求超时，报告生成可能需要数分钟，请稍后重试或关闭「用药审查」以缩短耗时')
    }
    throw new Error(e instanceof Error && e.message === 'Failed to fetch' ? hint : `${hint}（${String(e)}）`)
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    if (Array.isArray(err.detail)) {
      const msg = err.detail.map((d: { msg?: string; loc?: string[] }) => d.msg ?? JSON.stringify(d)).join('；')
      throw new Error(msg || res.statusText)
    }
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err))
  }
  return res.json() as Promise<T>
}

/** Long-running API calls (report generate, multi-agent review). Default 10 min. */
async function requestLong<T>(path: string, init?: RequestInit, timeoutMs = 600_000): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await request<T>(path, { ...init, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

export function imagingFileUrl(path: string): string {
  return `${BASE}/api/v1/imaging/file?path=${encodeURIComponent(path)}`
}

export function volumeSliceUrl(params: {
  volume_path: string
  axis: string
  index: number
  overlay_path?: string
}): string {
  const q = new URLSearchParams({
    volume_path: params.volume_path,
    axis: params.axis,
    index: String(params.index),
  })
  if (params.overlay_path) q.set('overlay_path', params.overlay_path)
  return `${BASE}/api/v1/imaging/volume/slice?${q}`
}

async function fetchAuthedBlob(url: string): Promise<Blob> {
  const res = await fetch(url, { headers: authHeaders() })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = typeof err.detail === 'string' ? err.detail : res.statusText
    throw new Error(detail || `HTTP ${res.status}`)
  }
  return res.blob()
}

export const medsafeApi = {
  health: () => request<HealthResponse>('/health'),

  login: (username: string, password: string) =>
    request<TokenResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  listDepartments: () =>
    request<{ departments: DepartmentInfo[] }>('/api/v1/auth/departments'),

  register: (body: { username: string; password: string; display_name?: string; dept_id: string }) =>
    request<TokenResponse & DoctorWorkspace>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  getMe: () => request<DoctorWorkspace>('/api/v1/auth/me'),

  updateAgentPrefs: (body: { agents: { agent_id: string; enabled: boolean }[] }) =>
    request<DoctorWorkspace>('/api/v1/auth/agent-prefs', { method: 'PUT', body: JSON.stringify(body) }),

  updateSkillPrefs: (body: { skills: { agent_id: string; skill_id: string; enabled: boolean }[] }) =>
    request<DoctorWorkspace>('/api/v1/auth/skill-prefs', { method: 'PUT', body: JSON.stringify(body) }),

  addCustomSkill: (body: { agent_id: string; title: string; content_md: string }) =>
    request<{ skill_id: string }>('/api/v1/auth/custom-skills', { method: 'POST', body: JSON.stringify(body) }),

  pharmacyQueue: (params?: { page?: number; page_size?: number; status?: string }) => {
    const q = new URLSearchParams()
    if (params?.page) q.set('page', String(params.page))
    if (params?.page_size) q.set('page_size', String(params.page_size))
    if (params?.status) q.set('status', params.status)
    const suffix = q.toString() ? `?${q}` : ''
    return request<{ items: PharmacyQueueItem[]; total: number }>(`/api/v1/pharmacy/queue${suffix}`)
  },

  pharmacyReview: (reviewId: string) =>
    request<PharmacistReview>(`/api/v1/pharmacy/review/${reviewId}`),

  pharmacyDecide: (
    reviewId: string,
    body: {
      alert_id: string
      action: AlertDecisionAction
      override_reason?: string
      override_risk_acceptance?: RiskAcceptance
      pharmacist_notes?: string
    },
  ) =>
    request<PharmacistReview>(`/api/v1/pharmacy/review/${reviewId}/decide`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  pharmacySubmit: (reviewId: string, body: { notes?: string }) =>
    request<PharmacistReview>(`/api/v1/pharmacy/review/${reviewId}/submit`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  pharmacyAudit: (filters: {
    start_date?: string
    end_date?: string
    drug_name?: string
    alert_level?: string
  }) => {
    const q = new URLSearchParams()
    Object.entries(filters).forEach(([k, v]) => { if (v) q.set(k, v) })
    const suffix = q.toString() ? `?${q}` : ''
    return request<{ items: OverrideAuditLog[]; total: number }>(`/api/v1/pharmacy/audit${suffix}`)
  },

  pharmacyAuditExport: async (query: string) => {
    const res = await fetch(`${BASE}/api/v1/pharmacy/audit/export${query ? `?${query}` : ''}`, {
      headers: authHeaders(),
    })
    if (!res.ok) throw new Error(await res.text())
    return res.blob()
  },

  pharmacyAuditExportUrl: (query: string) =>
    `${BASE}/api/v1/pharmacy/audit/export${query ? `?${query}` : ''}`,

  pharmacyStats: () => request<PharmacyStats>('/api/v1/pharmacy/stats'),

  listAgents: () => request<{ agents: AgentInfo[] }>('/api/v1/agents'),

  extract: (text: string) =>
    request<{ case_id?: string; raw_output: string; parsed_output?: Record<string, unknown> }>(
      '/api/v1/extract',
      { method: 'POST', body: JSON.stringify({ text, persist: false }) },
    ),

  multiConsult: (body: {
    text?: string
    patient_context?: PatientContext
    candidate_drugs: DrugItem[]
    persist?: boolean
  }) =>
    requestLong<MultiConsultResponse>('/api/v1/multi-consult', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  clarify: (body: {
    patient_context: PatientContext
    candidate_drugs: DrugItem[]
    review_output: ReviewOutput
    user_answers?: Record<string, string>
    unable_to_answer?: boolean
    case_id?: string | null
    persist?: boolean
  }) =>
    request<{ case_id?: string | null; clarify_output: ClarifyOutput }>('/api/v1/clarify', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  cpoeMedicationReview: (body: {
    encounter_id?: string
    patient: CpoePatientSnapshot
    orders: CpoeMedicationOrder[]
    existing_medications?: DrugItem[]
    review_mode?: string
    department?: string
  }) =>
    request<CpoeMedicationReviewResponse>('/api/v1/cpoe/medication-review', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  getDepartmentContext: (deptId?: string) => {
    const q = deptId ? `?dept_id=${encodeURIComponent(deptId)}` : ''
    return request<DepartmentContextResponse>(`/api/v1/department/context${q}`)
  },

  getDepartmentStats: (deptId?: string) => {
    const q = deptId ? `?dept_id=${encodeURIComponent(deptId)}` : ''
    return request<DepartmentStatsResponse>(`/api/v1/department/stats${q}`)
  },

  ruleReview: (patient_context: PatientContext, candidate_drugs: DrugItem[]) =>
    request<{ review_output: ReviewOutput; retrieved_evidence: unknown[] }>('/api/v1/review', {
      method: 'POST',
      body: JSON.stringify({ patient_context, candidate_drugs, persist: false }),
    }),

  listCases: (limit = 30) =>
    request<{ count: number; cases: CaseSummary[] }>(`/api/v1/cases?limit=${limit}`),

  getCase: (caseId: string) => request<CaseLog>(`/api/v1/case/${caseId}`),

  listImagingStudies: (source?: string) => {
    const q = source ? `?source=${encodeURIComponent(source)}` : ''
    return request<{ count: number; studies: ImagingStudy[] }>(`/api/v1/imaging/studies${q}`)
  },

  listSegmentModels: () =>
    request<{ models: SegModelInfo[] }>('/api/v1/imaging/models'),

  getVolumeMeta: (volume_path: string) =>
    request<VolumeMeta>(`/api/v1/imaging/volume/meta?volume_path=${encodeURIComponent(volume_path)}`),

  imagingFileObjectUrl: async (path: string) => {
    const blob = await fetchAuthedBlob(imagingFileUrl(path))
    return URL.createObjectURL(blob)
  },

  volumeSliceObjectUrl: async (params: {
    volume_path: string
    axis: string
    index: number
    overlay_path?: string
  }) => {
    const blob = await fetchAuthedBlob(volumeSliceUrl(params))
    return URL.createObjectURL(blob)
  },

  segment: (body: {
    image_path: string
    model_ids: ModelId[]
    organ?: string
    volume_path?: string
    slice_axis?: VolumeAxis
    slice_index?: number
    patient_id?: string
    study_id?: string
    persist?: boolean
  }) =>
    requestLong<SegmentResponse>(
      '/api/v1/imaging/segment',
      { method: 'POST', body: JSON.stringify(body) },
    ),

  listSegmentRuns: (params: {
    patient_id: string
    study_id: string
    image_path?: string
    volume_path?: string
    slice_axis?: VolumeAxis
    slice_index?: number
  }) => {
    const q = new URLSearchParams({
      patient_id: params.patient_id,
      study_id: params.study_id,
    })
    if (params.image_path) q.set('image_path', params.image_path)
    if (params.volume_path) q.set('volume_path', params.volume_path)
    if (params.slice_axis) q.set('slice_axis', params.slice_axis)
    if (params.slice_index != null) q.set('slice_index', String(params.slice_index))
    return request<{ count: number; image_key: string; runs: SegmentRunRecord[] }>(
      `/api/v1/imaging/segments?${q}`,
    )
  },

  getImagingAnalysisCache: (patientId: string, studyId: string, source?: string) => {
    const q = source ? `?source=${encodeURIComponent(source)}` : ''
    return request<{
      cached: boolean
      from_cache: boolean
      full_report_cached?: boolean
      entry?: {
        patient_id: string
        study_id: string
        source: string
        image_paths: string[]
        vlm_analysis: VlmAnalysis
        vlm_model: string
        deepseek_synthesis?: Record<string, unknown>
        deepseek_model?: string
        updated_at?: string
      } | null
      clinical_report?: ClinicalReport | null
    }>(`/api/v1/imaging/analysis-cache/${encodeURIComponent(patientId)}/${encodeURIComponent(studyId)}${q}`)
  },

  analyzeWithVlm: (body: {
    clinical_text: string
    primary_modality: string
    patient_id?: string
    study_id?: string
    source?: string
    image_paths?: string[]
    overlay_paths?: string[]
    segmentation_summary?: string
    include_source_image?: boolean
    use_cache?: boolean
    force_refresh?: boolean
  }) =>
    request<{
      case_id?: string | null
      analysis: VlmAnalysis
      images_used: string[]
      model: string
      configured: boolean
      overlay_count: number
      source_count: number
      duration_ms: number
      from_cache?: boolean
      deepseek_synthesis?: Record<string, unknown>
      deepseek_model?: string
    }>(
      '/api/v1/imaging/vlm/analyze',
      { method: 'POST', body: JSON.stringify(body) },
    ),

  getVlmConfig: () =>
    request<{ model: string; configured: boolean; hint: string }>('/api/v1/imaging/vlm/config'),

  saveScreenshot: (body: {
    patient_id: string
    study_id: string
    image_data: string
    caption?: string
  }) =>
    request<{ path: string; caption: string }>('/api/v1/imaging/screenshot', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  generateReport: (body: {
    patient_id: string
    case_id?: string | null
    clinical_text: string
    primary_modality: string
    modalities: string[]
    imaging_session_label?: string
    image_paths: string[]
    overlay_paths?: string[]
    screenshot_paths?: string[]
    models_used?: string[]
    segmentation_summary?: string
    include_source_image?: boolean
    run_medication_review?: boolean
    use_analysis_cache?: boolean
    force_refresh?: boolean
    candidate_drugs?: DrugItem[]
    patient_context?: PatientContext
  }) =>
    requestLong<ClinicalReport>('/api/v1/imaging/report/generate', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  listPatientReports: (patientId: string) =>
    request<{ patient_id: string; count: number; reports: ClinicalReport[] }>(
      `/api/v1/imaging/report/${patientId}`,
    ),

  getReport: (patientId: string, reportId: string) =>
    request<ClinicalReport>(`/api/v1/imaging/report/${patientId}/${reportId}`),

  askReport: (body: { patient_id: string; report_id: string; question: string }) =>
    request<{ answer: string; related_paragraphs: ReportParagraph[]; report: ClinicalReport }>(
      '/api/v1/imaging/report/ask',
      { method: 'POST', body: JSON.stringify(body) },
    ),

  listCaseTemplates: (department?: string) => {
    const q = department ? `?department=${encodeURIComponent(department)}` : ''
    return request<{ templates: CaseTemplate[] }>(`/api/v1/case-templates${q}`)
  },

  getCaseTemplate: (id: string) => request<CaseTemplate>(`/api/v1/case-templates/${id}`),

  mimicStats: () => request<MimicDataStatsResponse>('/api/v1/mimic/stats'),

  listMimicPatients: (params?: {
    offset?: number
    limit?: number
    q?: string
    gender?: string
    min_medications?: number
    icu_only?: boolean
    has_imaging?: boolean
    min_age?: number
    max_age?: number
    admission_type?: string
  }) => {
    const q = new URLSearchParams()
    if (params?.offset != null) q.set('offset', String(params.offset))
    if (params?.limit != null) q.set('limit', String(params.limit))
    if (params?.q) q.set('q', params.q)
    if (params?.gender) q.set('gender', params.gender)
    if (params?.min_medications != null) q.set('min_medications', String(params.min_medications))
    if (params?.icu_only) q.set('icu_only', 'true')
    if (params?.has_imaging != null) q.set('has_imaging', String(params.has_imaging))
    if (params?.min_age != null) q.set('min_age', String(params.min_age))
    if (params?.max_age != null) q.set('max_age', String(params.max_age))
    if (params?.admission_type) q.set('admission_type', params.admission_type)
    const suffix = q.toString() ? `?${q}` : ''
    return request<MimicPatientListResponse>(`/api/v1/mimic/patients${suffix}`)
  },

  getMimicPatient: (subjectId: number, hadmId: number) =>
    request<PatientContext>(`/api/v1/mimic/patients/${subjectId}/${hadmId}`),

  getMimicPatientImaging: (subjectId: number, hadmId: number) =>
    request<{ subject_id: number; hadm_id: number; cxr_patient_id: string; has_imaging: boolean; studies: ImagingStudy[] }>(
      `/api/v1/mimic/patients/${subjectId}/${hadmId}/imaging`,
    ),

  getDrugCatalogStats: () => request<DrugCatalogStats>('/api/v1/drug-catalog/stats'),

  getDrugClassification: (maxLevel = 4) =>
    request<{ max_level: number; tree: AtcTreeNode[]; special_filters: DrugSpecialFilter[] }>(
      `/api/v1/drug-catalog/classification?max_level=${maxLevel}`,
    ),

  browseDrugCatalog: (params: {
    atc_prefix?: string
    filter_id?: string
    limit?: number
    offset?: number
  }) => {
    const q = new URLSearchParams()
    if (params.atc_prefix) q.set('atc_prefix', params.atc_prefix)
    if (params.filter_id) q.set('filter_id', params.filter_id)
    if (params.limit != null) q.set('limit', String(params.limit))
    if (params.offset != null) q.set('offset', String(params.offset))
    const suffix = q.toString() ? `?${q}` : ''
    return request<{ results: HospitalDrug[]; total: number; offset: number; limit: number }>(
      `/api/v1/drug-catalog/browse${suffix}`,
    )
  },

  searchDrugCatalog: (q: string, limit = 20, mode: 'keyword' | 'semantic' = 'semantic') => {
    const params = new URLSearchParams({ q, limit: String(limit), mode })
    return request<{ query: string; mode: string; count: number; results: HospitalDrug[] }>(
      `/api/v1/drug-catalog/search?${params}`,
    )
  },

  getDrugSearchModelStatus: () =>
    request<DrugSearchModelStatus>('/api/v1/drug-catalog/search-model/status'),

  rebuildDrugSearchIndex: () =>
    request<DrugSearchModelStatus>('/api/v1/drug-catalog/search-model/rebuild', { method: 'POST' }),

  getDrugById: (hospitalDrugId: string) =>
    request<HospitalDrug>(`/api/v1/drug-catalog/drugs/${encodeURIComponent(hospitalDrugId)}`),

  getDrugAlternatives: (hospitalDrugId: string) =>
    request<{ hospital_drug_id: string; count: number; alternatives: HospitalDrug[] }>(
      `/api/v1/drug-catalog/drugs/${encodeURIComponent(hospitalDrugId)}/alternatives`,
    ),

  getDrugInfo: (drugName: string) =>
    request<DrugInfoResponse>('/api/v1/drug/info', {
      method: 'POST',
      body: JSON.stringify({ drug_name: drugName }),
    }),
}
