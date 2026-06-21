import type {
  AgentInfo,
  CaseLog,
  ClinicalReport,
  HealthResponse,
  ImagingStudy,
  ModelId,
  MultiConsultResponse,
  PatientContext,
  ReportParagraph,
  ReviewOutput,
  SegModelInfo,
  SegmentResultItem,
  DrugItem,
  VolumeAxis,
  VolumeMeta,
} from '@/types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err))
  }
  return res.json() as Promise<T>
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

export const medsafeApi = {
  health: () => request<HealthResponse>('/health'),

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
    unable_to_answer?: boolean
    persist?: boolean
  }) =>
    request<MultiConsultResponse>('/api/v1/multi-consult', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  ruleReview: (patient_context: PatientContext, candidate_drugs: DrugItem[]) =>
    request<{ review_output: ReviewOutput; retrieved_evidence: unknown[] }>('/api/v1/review', {
      method: 'POST',
      body: JSON.stringify({ patient_context, candidate_drugs, persist: false }),
    }),

  listCases: (limit = 30) => request<{ count: number; cases: string[] }>(`/api/v1/cases?limit=${limit}`),

  getCase: (caseId: string) => request<CaseLog>(`/api/v1/case/${caseId}`),

  listImagingStudies: () =>
    request<{ count: number; studies: ImagingStudy[] }>('/api/v1/imaging/studies'),

  listSegmentModels: () =>
    request<{ models: SegModelInfo[] }>('/api/v1/imaging/models'),

  getVolumeMeta: (volume_path: string) =>
    request<VolumeMeta>(`/api/v1/imaging/volume/meta?volume_path=${encodeURIComponent(volume_path)}`),

  segment: (body: {
    image_path: string
    model_ids: ModelId[]
    organ?: string
    volume_path?: string
    slice_axis?: VolumeAxis
    slice_index?: number
  }) =>
    request<{ results: SegmentResultItem[]; memory_peak_mb: number }>(
      '/api/v1/imaging/segment',
      { method: 'POST', body: JSON.stringify(body) },
    ),

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
    clinical_text: string
    primary_modality: string
    modalities: string[]
    imaging_session_label?: string
    image_paths: string[]
    overlay_paths: string[]
    screenshot_paths: string[]
    models_used: string[]
    segmentation_summary?: string
  }) =>
    request<ClinicalReport>('/api/v1/imaging/report/generate', {
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
}
