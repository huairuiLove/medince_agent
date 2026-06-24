<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import VolumeMprViewer from '@/components/imaging/VolumeMprViewer.vue'
import ImagingFileImage from '@/components/imaging/ImagingFileImage.vue'
import RuleReviewSummary from '@/components/consult/RuleReviewSummary.vue'
import AgentOpinionCard from '@/components/consult/AgentOpinionCard.vue'
import DebatePanel from '@/components/consult/DebatePanel.vue'
import RiskBadge from '@/components/common/RiskBadge.vue'
import { medsafeApi } from '@/api/medsafe'
import { useAuthStore } from '@/stores/auth'
import { useMultiConsult } from '@/composables/useMultiConsult'
import type {
  AgentOpinion,
  ArbitrationResult,
  ClinicalReport,
  DebateResult,
  DrugItem,
  ImagingStudy,
  ModelId,
  MultiConsultResponse,
  PatientContext,
  ReviewOutput,
  SafetyPanelResult,
  SegModelInfo,
  SegmentResultItem,
  SegmentRunRecord,
  VolumeAxis,
  VlmAnalysis,
} from '@/types'
import { coerceStringList, drugDetailParts, drugsWithoutIndication, mergeDrugIndicationsIntoDiagnoses } from '@/utils/patientForm'

const auth = useAuthStore()
const route = useRoute()

const SOURCE_LABELS: Record<string, string> = {
  mimic_cxr: '胸片 XR',
  chest_ct: '胸部/肺 CT',
  kits19: '肾脏 CT',
  brats2024: '脑 MRI',
  mimic: 'MIMIC CT',
}

const studies = ref<ImagingStudy[]>([])
const allowedSources = computed(() => auth.department?.imaging_sources ?? [])
const sourceFilterOptions = computed(() => {
  const opts: Array<[string, string]> = []
  if (allowedSources.value.length > 1) opts.push(['all', '全部'])
  for (const src of allowedSources.value) {
    opts.push([src, SOURCE_LABELS[src] ?? src])
  }
  return opts
})
const sourceFilter = ref<string>('all')
const models = ref<SegModelInfo[]>([])
const selectedStudy = ref<ImagingStudy | null>(null)
const selectedModels = ref<ModelId[]>(['sam2d'])
const sliceIndex = ref(0)
const viewMode = ref<'gallery' | 'mpr'>('gallery')
const mprAxis = ref<VolumeAxis>('axial')
const mprIndex = ref(0)
const clinicalText = ref('')
const organ = ref('brain')
const loading = ref(false)
const segmenting = ref(false)
const error = ref('')
const segmentResults = ref<SegmentResultItem[]>([])
const segmentHistory = ref<SegmentRunRecord[]>([])
const selectedOverlayKeys = ref<Set<string>>(new Set())
const screenshots = ref<{ path: string; caption: string }[]>([])
const report = ref<ClinicalReport | null>(null)
const savedReports = ref<ClinicalReport[]>([])
const reportsLoading = ref(false)
const vlmAnalysis = ref<VlmAnalysis | null>(null)
const vlmModel = ref('')
const vlmConfigured = ref(true)
const vlmHint = ref('')
const vlmImagesUsed = ref<string[]>([])
const vlmDurationMs = ref(0)
const vlmCaseId = ref<string | null>(null)
const analysisFromCache = ref(false)
const reportDurationMs = ref(0)
const reportTask = ref<'vlm' | 'report' | null>(null)
const taskElapsedMs = ref(0)
let taskTimer: ReturnType<typeof setInterval> | null = null
const runMedicationReview = ref(true)
const candidateDrugs = ref<DrugItem[]>([])
const newDrugName = ref('')
const newDiagnosis = ref('')
const newAllergy = ref('')
const newCurrentMed = ref('')

function emptyImagingPatient(): PatientContext {
  return {
    gender: 'unknown',
    pregnancy_status: 'unknown',
    allergies: [],
    current_medications: [],
    missing_fields: [],
    diagnoses: [],
  }
}

const imagingPatient = ref<PatientContext>(emptyImagingPatient())

const {
  loading: medConsultLoading,
  error: medConsultError,
  result: medConsultResult,
  run: runMedConsult,
  reset: resetMedConsult,
} = useMultiConsult()

const medConsultArb = computed(() => medConsultResult.value?.arbitration ?? null)
const qaQuestion = ref('')
const qaAnswer = ref('')
const viewerRef = ref<HTMLDivElement | null>(null)
const memoryPeak = ref(0)
const segmentComputeMessage = ref('')
const volumeMaskPath = ref<string | null>(null)

const filteredStudies = computed(() => {
  if (sourceFilter.value === 'all') return studies.value
  return studies.value.filter(s => s.source === sourceFilter.value)
})

function formatElapsed(ms: number): string {
  const sec = ms / 1000
  if (sec < 60) return `${sec.toFixed(1)} 秒`
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

function startReportTask(task: 'vlm' | 'report') {
  stopReportTask(false)
  reportTask.value = task
  taskElapsedMs.value = 0
  const started = Date.now()
  taskTimer = setInterval(() => {
    taskElapsedMs.value = Date.now() - started
  }, 200)
}

function stopReportTask(clearTask = true) {
  if (taskTimer) {
    clearInterval(taskTimer)
    taskTimer = null
  }
  if (clearTask) reportTask.value = null
}

onUnmounted(() => stopReportTask())

async function loadStudies() {
  const res = await medsafeApi.listImagingStudies(
    sourceFilter.value === 'all' ? undefined : sourceFilter.value,
  )
  studies.value = res.studies
  const patientQuery = typeof route.query.patient === 'string' ? route.query.patient : ''
  if (patientQuery) {
    const match = studies.value.find(s => s.patient_id === patientQuery)
    if (match) {
      selectStudy(match)
      return
    }
  }
  if (!studies.value.some(s => s.study_id === selectedStudy.value?.study_id)) {
    if (studies.value.length) selectStudy(studies.value[0])
    else selectedStudy.value = null
  }
}

const hasVolume = computed(() => Boolean(selectedStudy.value?.volume_path))

const compatibleModels = computed(() => {
  if (!selectedStudy.value) return models.value
  const study = selectedStudy.value
  return models.value.filter(m => {
    if (m.datasets?.includes(study.source)) return true
    if (m.modalities.includes(study.modality)) return true
    if (m.modalities.includes('ALL')) return true
    return false
  })
})

const showLesionTarget = computed(() =>
  selectedModels.value.some(id => compatibleModels.value.find(m => m.model_id === id)?.task === 'lesion'),
)

const targetOptions = computed(() => {
  const opts = new Set<string>()
  for (const id of selectedModels.value) {
    compatibleModels.value.find(m => m.model_id === id)?.organs.forEach(o => opts.add(o))
  }
  return opts.size ? [...opts] : ['brain', 'liver', 'lung']
})

function defaultModelsForStudy(s: ImagingStudy): ModelId[] {
  if (s.source === 'mimic_cxr') return ['cxr_lesion']
  if (s.source === 'brats2024') return ['brats_tumor']
  if (s.source === 'kits19') return ['vista3d']
  if (s.source === 'chest_ct') return ['totalsegmentator', 'vista3d']
  return ['sam2d']
}

function defaultTargetForStudy(s: ImagingStudy): string {
  if (s.source === 'mimic_cxr') return 'opacity'
  if (s.source === 'brats2024') return 'whole_tumor'
  if (s.source === 'kits19') return 'kidney'
  if (s.source === 'chest_ct') return 'lung'
  return 'brain'
}

const currentImage = computed(() => {
  if (!selectedStudy.value?.image_paths.length) return ''
  const idx = Math.min(sliceIndex.value, selectedStudy.value.image_paths.length - 1)
  return selectedStudy.value.image_paths[idx]
})

function isVisualImagePath(path: string): boolean {
  return /\.(png|jpe?g|webp|bmp)$/i.test(path)
}

/** 提交 Qwen/DS 的原片路径（catalog 预览 PNG，不含分割 overlay） */
const vlmSourceImagePaths = computed(() => {
  const s = selectedStudy.value
  if (!s?.image_paths?.length) return [] as string[]
  return s.image_paths.filter(isVisualImagePath).slice(0, 4)
})

const hasVlmSourceImages = computed(() => vlmSourceImagePaths.value.length > 0)

const currentSegmentImagePath = computed(() => {
  if (viewMode.value === 'mpr' && selectedStudy.value?.volume_path) {
    return selectedStudy.value.volume_path
  }
  return currentImage.value
})

function overlayKey(runId: string, modelId: string) {
  return `${runId}:${modelId}`
}

const selectedOverlayPaths = computed(() => {
  const paths: string[] = []
  for (const run of segmentHistory.value) {
    for (const r of run.results) {
      if (selectedOverlayKeys.value.has(overlayKey(run.run_id, r.model_id))) {
        paths.push(r.overlay_path)
      }
    }
  }
  return paths
})

const vista3dOverlayMask = computed(() => {
  for (const run of segmentHistory.value) {
    for (const modelId of ['vista3d', 'brats_tumor'] as const) {
      const v = run.results.find(r => r.model_id === modelId)
      const p = v?.stats?.volume_mask_path
      if (typeof p === 'string') return p
    }
  }
  for (const modelId of ['vista3d', 'brats_tumor'] as const) {
    const v = segmentResults.value.find(r => r.model_id === modelId)
    const p = v?.stats?.volume_mask_path
    if (typeof p === 'string') return p
  }
  return volumeMaskPath.value
})

async function loadSegmentHistory() {
  if (!selectedStudy.value) {
    segmentHistory.value = []
    return
  }
  try {
    const res = await medsafeApi.listSegmentRuns({
      patient_id: selectedStudy.value.patient_id,
      study_id: selectedStudy.value.study_id,
      image_path: currentSegmentImagePath.value,
      volume_path: selectedStudy.value.volume_path ?? undefined,
      slice_axis: viewMode.value === 'mpr' ? mprAxis.value : 'axial',
      slice_index: viewMode.value === 'mpr' ? mprIndex.value : sliceIndex.value,
    })
    segmentHistory.value = res.runs
    if (!selectedOverlayKeys.value.size && res.runs.length) {
      const latest = res.runs[0]
      const next = new Set<string>()
      for (const r of latest.results) next.add(overlayKey(latest.run_id, r.model_id))
      selectedOverlayKeys.value = next
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(async () => {
  try {
    await loadStudies()
    models.value = (await medsafeApi.listSegmentModels()).models
    const vlmCfg = await medsafeApi.getVlmConfig()
    vlmConfigured.value = vlmCfg.configured
    vlmHint.value = vlmCfg.hint
    vlmModel.value = vlmCfg.model
    if (studies.value.length) selectStudy(studies.value[0])
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})

watch(allowedSources, (sources) => {
  if (sources.length === 1) sourceFilter.value = sources[0]
  else if (!sources.includes(sourceFilter.value) && sourceFilter.value !== 'all') {
    sourceFilter.value = sources.length > 1 ? 'all' : (sources[0] ?? 'all')
  }
}, { immediate: true })

watch(
  () => auth.department?.dept_id,
  () => {
    studies.value = []
    selectedStudy.value = null
    void loadStudies()
    void medsafeApi.listSegmentModels().then(res => {
      models.value = res.models
    })
  },
)

watch(sourceFilter, () => {
  void loadStudies()
})

watch([currentSegmentImagePath, viewMode], () => {
  if (selectedStudy.value) void loadSegmentHistory()
})

function selectStudy(s: ImagingStudy) {
  selectedStudy.value = s
  sliceIndex.value = 0
  mprIndex.value = 0
  mprAxis.value = 'axial'
  viewMode.value = s.volume_path ? 'mpr' : 'gallery'
  segmentResults.value = []
  segmentHistory.value = []
  selectedOverlayKeys.value = new Set()
  screenshots.value = []
  report.value = null
  savedReports.value = []
  reportDurationMs.value = 0
  vlmAnalysis.value = null
  analysisFromCache.value = false
  volumeMaskPath.value = null
  qaAnswer.value = ''
  qaQuestion.value = ''
  candidateDrugs.value = []
  imagingPatient.value = emptyImagingPatient()
  resetMedConsult()
  newDrugName.value = ''
  newDiagnosis.value = ''
  newAllergy.value = ''
  newCurrentMed.value = ''
  selectedModels.value = defaultModelsForStudy(s)
  organ.value = defaultTargetForStudy(s)
  clinicalText.value = s.report_text?.trim()
    ? s.report_text
    : `${s.title} — ${s.modality} 影像会诊`
  void loadSegmentHistory()
  void loadPatientReports()
  void loadAnalysisCache()
}

function applyReportToForm(r: ClinicalReport) {
  applyMedConsultFromReport(r)
  const vlm = r.metadata?.vlm_analysis as VlmAnalysis | undefined
  if (vlm && typeof vlm === 'object') {
    vlmAnalysis.value = vlm
    syncImagingFormFromVlm(vlm)
  }
  const drugs = r.metadata?.candidate_drugs as DrugItem[] | undefined
  if (Array.isArray(drugs) && drugs.length) {
    candidateDrugs.value = drugs.map(d => ({
      name: d.name?.trim() ?? '',
      dose: d.dose,
      route: d.route,
      frequency: d.frequency,
      indication: d.indication,
    })).filter(d => d.name)
  }
}

async function loadAnalysisCache() {
  if (!selectedStudy.value) return
  const s = selectedStudy.value
  try {
    const res = await medsafeApi.getImagingAnalysisCache(s.patient_id, s.study_id, s.source)
    if (res.cached && res.entry?.vlm_analysis) {
      vlmAnalysis.value = res.entry.vlm_analysis
      vlmModel.value = res.entry.vlm_model
      vlmImagesUsed.value = res.entry.image_paths ?? []
      analysisFromCache.value = true
      syncImagingFormFromVlm(res.entry.vlm_analysis)
    }
    if (res.full_report_cached && res.clinical_report) {
      report.value = res.clinical_report
      applyReportToForm(res.clinical_report)
      analysisFromCache.value = true
    }
  } catch {
    /* optional preload */
  }
}

function applyMedConsultFromReport(r: ClinicalReport) {
  const meta = r.metadata ?? {}
  if (!meta.medication_review_ran) {
    resetMedConsult()
    return
  }
  const ruleOutput = meta.rule_output as ReviewOutput | undefined
  const arbitration = meta.arbitration as ArbitrationResult | undefined
  if (!ruleOutput || !arbitration) {
    resetMedConsult()
    return
  }
  medConsultResult.value = {
    rule_output: ruleOutput,
    agent_opinions: (meta.agent_opinions as AgentOpinion[]) ?? [],
    debate: (meta.debate as DebateResult | null) ?? null,
    safety_panel: (meta.safety_panel as SafetyPanelResult | null) ?? null,
    arbitration,
    final_recommendation: String(meta.final_recommendation ?? arbitration.final_recommendation ?? ''),
  } satisfies MultiConsultResponse
}

async function loadPatientReports() {
  if (!selectedStudy.value) {
    savedReports.value = []
    return
  }
  reportsLoading.value = true
  try {
    const res = await medsafeApi.listPatientReports(selectedStudy.value.patient_id)
    savedReports.value = res.reports.sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    reportsLoading.value = false
  }
}

async function loadSavedReport(reportId: string) {
  if (!selectedStudy.value) return
  loading.value = true
  error.value = ''
  qaAnswer.value = ''
  try {
    report.value = await medsafeApi.getReport(selectedStudy.value.patient_id, reportId)
    applyReportToForm(report.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function toggleModel(id: ModelId) {
  const i = selectedModels.value.indexOf(id)
  if (i >= 0) selectedModels.value.splice(i, 1)
  else selectedModels.value.push(id)
}

function toggleOverlaySelection(runId: string, modelId: string) {
  const key = overlayKey(runId, modelId)
  const next = new Set(selectedOverlayKeys.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selectedOverlayKeys.value = next
}

function isOverlaySelected(runId: string, modelId: string) {
  return selectedOverlayKeys.value.has(overlayKey(runId, modelId))
}

async function runSegmentation() {
  if (!selectedModels.value.length || !selectedStudy.value) return
  if (viewMode.value === 'gallery' && !currentImage.value) return
  if (viewMode.value === 'mpr' && !selectedStudy.value?.volume_path) return

  segmenting.value = true
  error.value = ''
  segmentComputeMessage.value = ''
  try {
    const imagePath = viewMode.value === 'mpr'
      ? (selectedStudy.value!.volume_path as string)
      : currentImage.value

    const res = await medsafeApi.segment({
      image_path: imagePath,
      model_ids: selectedModels.value,
      organ: organ.value,
      volume_path: selectedStudy.value?.volume_path ?? undefined,
      slice_axis: viewMode.value === 'mpr' ? mprAxis.value : 'axial',
      slice_index: viewMode.value === 'mpr' ? mprIndex.value : sliceIndex.value,
      patient_id: selectedStudy.value.patient_id,
      study_id: selectedStudy.value.study_id,
      persist: true,
    })
    segmentResults.value = res.results
    memoryPeak.value = res.memory_peak_mb
    segmentComputeMessage.value = res.compute_message ?? ''
    const vista = res.results.find(r => r.model_id === 'vista3d' || r.model_id === 'brats_tumor')
    const mask = vista?.stats?.volume_mask_path
    if (typeof mask === 'string') volumeMaskPath.value = mask
    await loadSegmentHistory()
    if (res.run_id) {
      const next = new Set(selectedOverlayKeys.value)
      for (const r of res.results) next.add(overlayKey(res.run_id!, r.model_id))
      selectedOverlayKeys.value = next
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    segmenting.value = false
  }
}

async function captureScreenshot() {
  if (!selectedStudy.value || !viewerRef.value) return
  const canvas = document.createElement('canvas')
  const img = viewerRef.value.querySelector('img') as HTMLImageElement | null
  if (!img) return
  canvas.width = img.naturalWidth || img.width
  canvas.height = img.naturalHeight || img.height
  const ctx = canvas.getContext('2d')!
  ctx.drawImage(img, 0, 0)
  const dataUrl = canvas.toDataURL('image/png')
  const caption = viewMode.value === 'mpr'
    ? `${mprAxis.value}_${mprIndex.value}`
    : `slice_${sliceIndex.value}`
  const res = await medsafeApi.saveScreenshot({
    patient_id: selectedStudy.value.patient_id,
    study_id: selectedStudy.value.study_id,
    image_data: dataUrl,
    caption,
  })
  screenshots.value.push({ path: res.path, caption: res.caption })
}

function vlmToDrugItems(drugs: VlmAnalysis['recommended_drugs']): DrugItem[] {
  if (!drugs?.length) return []
  return drugs
    .map(d => {
      if (typeof d === 'string') return { name: d.trim() }
      return {
        name: d.name?.trim() ?? '',
        dose: d.dose,
        route: d.route,
        frequency: d.frequency,
        indication: d.indication,
      }
    })
    .filter(d => d.name)
}

function syncImagingFormFromVlm(analysis: VlmAnalysis | null) {
  if (!analysis) return
  const drugs = vlmToDrugItems(analysis.recommended_drugs)
  if (drugs.length) candidateDrugs.value = drugs

  const dxFromVlm = (analysis.diagnoses ?? [])
    .map(d => (typeof d === 'string' ? { name: d } : d))
    .filter(d => d.name?.trim())

  const vlmAllergies = coerceStringList(analysis.allergies)
  const vlmSymptoms = coerceStringList(analysis.symptoms)

  imagingPatient.value = {
    ...imagingPatient.value,
    gender: imagingPatient.value.gender ?? 'unknown',
    chief_complaint: analysis.chief_complaint ?? imagingPatient.value.chief_complaint,
    symptoms_or_complaints: vlmSymptoms.length
      ? vlmSymptoms
      : coerceStringList(imagingPatient.value.symptoms_or_complaints),
    allergies: vlmAllergies.length
      ? vlmAllergies
      : coerceStringList(imagingPatient.value.allergies),
    diagnoses: dxFromVlm.length ? dxFromVlm : imagingPatient.value.diagnoses ?? [],
    department: auth.profile?.dept_id ?? imagingPatient.value.department ?? '',
    source_text: clinicalText.value,
    history_present_illness: [
      analysis.clinical_analysis,
      analysis.imaging_findings,
      analysis.medication_recommendation,
    ]
      .filter(Boolean)
      .join('\n'),
  }
  if (drugs.length) mergeDrugIndicationsIntoDiagnoses(imagingPatient.value, drugs)
}

function addCandidateDrug() {
  const name = newDrugName.value.trim()
  if (!name) return
  candidateDrugs.value.push({ name })
  newDrugName.value = ''
}

function removeCandidateDrug(i: number) {
  candidateDrugs.value.splice(i, 1)
}

function addImagingDiagnosis() {
  const name = newDiagnosis.value.trim()
  if (!name) return
  if (!imagingPatient.value.diagnoses) imagingPatient.value.diagnoses = []
  if (!imagingPatient.value.diagnoses.some(d => d.name === name)) {
    imagingPatient.value.diagnoses.push({ name })
  }
  newDiagnosis.value = ''
}

function removeImagingDiagnosis(i: number) {
  imagingPatient.value.diagnoses?.splice(i, 1)
}

function addImagingAllergy() {
  const val = newAllergy.value.trim()
  if (!val) return
  if (!imagingPatient.value.allergies) imagingPatient.value.allergies = []
  if (!imagingPatient.value.allergies.includes(val)) {
    imagingPatient.value.allergies.push(val)
  }
  newAllergy.value = ''
}

function removeImagingAllergy(i: number) {
  imagingPatient.value.allergies?.splice(i, 1)
}

function addCurrentMedication() {
  const name = newCurrentMed.value.trim()
  if (!name) return
  if (!imagingPatient.value.current_medications) imagingPatient.value.current_medications = []
  imagingPatient.value.current_medications.push({ name })
  newCurrentMed.value = ''
}

function removeCurrentMedication(i: number) {
  imagingPatient.value.current_medications?.splice(i, 1)
}

function buildImagingPatientContext(): PatientContext {
  const vlm = vlmAnalysis.value
  const narrative = [
    clinicalText.value,
    vlm?.clinical_analysis,
    vlm?.imaging_findings,
    vlm?.medication_recommendation,
    vlm?.reasoning ? `推理：${vlm.reasoning}` : '',
  ]
    .filter(Boolean)
    .join('\n\n')
  return {
    ...imagingPatient.value,
    department: auth.profile?.dept_id ?? imagingPatient.value.department ?? '',
    source_text: narrative || imagingPatient.value.source_text || clinicalText.value,
  }
}

async function runMedicationAnalysis() {
  if (!candidateDrugs.value.length) {
    medConsultError.value = '请至少添加一种候选用药（VLM 查阅后会自动带入，也可手动编辑）'
    return
  }
  const pc = buildImagingPatientContext()
  mergeDrugIndicationsIntoDiagnoses(pc, candidateDrugs.value)
  await runMedConsult({
    patient_context: pc,
    candidate_drugs: drugsWithoutIndication(candidateDrugs.value),
    persist: true,
  })
}

watch(vlmAnalysis, analysis => syncImagingFormFromVlm(analysis))

const reportRuleOutput = computed((): ReviewOutput | null => {
  const raw = report.value?.metadata?.rule_output
  if (!raw || typeof raw !== 'object') return null
  return raw as ReviewOutput
})

async function generateReport() {
  if (!selectedStudy.value) return
  const candidateDrugsForReport = candidateDrugs.value.length
    ? drugsWithoutIndication(candidateDrugs.value)
    : vlmToDrugItems(vlmAnalysis.value?.recommended_drugs)
  if (runMedicationReview.value && !candidateDrugsForReport.length) {
    error.value = '已启用用药审查，请填写候选药物，或先运行 VLM 查阅以自动带入推荐用药'
    return
  }
  if (!hasVlmSourceImages.value) {
    error.value = '该检查暂无可用的影像原片（PNG 预览），请先运行 warm_imaging_analysis_cache 或确认 catalog 数据'
    return
  }
  loading.value = true
  error.value = ''
  startReportTask('report')
  const started = Date.now()
  try {
    report.value = await medsafeApi.generateReport({
      patient_id: selectedStudy.value.patient_id,
      case_id: vlmCaseId.value ?? undefined,
      clinical_text: clinicalText.value,
      primary_modality: selectedStudy.value.modality,
      modalities: [selectedStudy.value.modality],
      imaging_session_label: selectedStudy.value.study_id,
      image_paths: vlmSourceImagePaths.value,
      overlay_paths: [],
      screenshot_paths: screenshots.value.map(s => s.path),
      models_used: selectedModels.value,
      segmentation_summary: '',
      include_source_image: true,
      run_medication_review: runMedicationReview.value,
      use_analysis_cache: true,
      candidate_drugs: candidateDrugsForReport,
      patient_context: buildImagingPatientContext(),
    })
    reportDurationMs.value = Date.now() - started
    const reviewErr = report.value.metadata?.medication_review_error
    if (typeof reviewErr === 'string' && reviewErr) {
      error.value = `报告已生成（VLM 部分完成），但用药审查未完成：${reviewErr}`
    }
    await loadPatientReports()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
    stopReportTask()
  }
}

async function runVlmConsult(forceRefresh = false) {
  if (!selectedStudy.value) return
  if (!hasVlmSourceImages.value) {
    error.value = '该检查暂无影像原片预览，无法提交 VLM'
    return
  }
  loading.value = true
  error.value = ''
  vlmAnalysis.value = null
  vlmCaseId.value = null
  analysisFromCache.value = false
  startReportTask('vlm')
  const started = Date.now()
  try {
    const s = selectedStudy.value
    const res = await medsafeApi.analyzeWithVlm({
      patient_id: s.patient_id,
      study_id: s.study_id,
      source: s.source,
      clinical_text: clinicalText.value,
      primary_modality: s.modality,
      image_paths: vlmSourceImagePaths.value,
      overlay_paths: [],
      include_source_image: true,
      use_cache: !forceRefresh,
      force_refresh: forceRefresh,
    })
    vlmAnalysis.value = res.analysis
    vlmCaseId.value = res.case_id ?? null
    vlmModel.value = res.model
    vlmImagesUsed.value = res.images_used
    vlmDurationMs.value = res.duration_ms || Date.now() - started
    analysisFromCache.value = Boolean(res.from_cache)
    syncImagingFormFromVlm(res.analysis)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
    stopReportTask()
  }
}

async function askReport() {
  if (!report.value || !qaQuestion.value.trim()) return
  loading.value = true
  try {
    const res = await medsafeApi.askReport({
      patient_id: report.value.patient_id,
      report_id: report.value.report_id,
      question: qaQuestion.value,
    })
    qaAnswer.value = res.answer
    report.value = res.report
    qaQuestion.value = ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

const sortedParagraphs = computed(() =>
  report.value ? [...report.value.paragraphs].sort((a, b) => a.order - b.order) : [],
)
</script>

<template>
  <div class="imaging-page">
    <header class="page-head">
      <div>
        <h1>影像分割与用药安全报告</h1>
        <p class="sub">病灶分割 · 器官分割 · Qwen VLM 报告 · 科室：{{ auth.department?.name_cn ?? '—' }}</p>
      </div>
      <div v-if="memoryPeak" class="mem-badge">峰值内存 ~{{ memoryPeak.toFixed(0) }} MB</div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>
    <p v-if="segmentComputeMessage" class="info-banner">{{ segmentComputeMessage }}</p>
    <p v-if="!vlmConfigured" class="config-banner">{{ vlmHint }}</p>

    <div class="grid-main">
      <aside class="card panel">
        <h3>影像检查</h3>
        <div v-if="sourceFilterOptions.length" class="source-filter">
          <button
            v-for="opt in sourceFilterOptions"
            :key="opt[0]"
            type="button"
            class="mode-btn"
            :class="{ active: sourceFilter === opt[0] }"
            @click="sourceFilter = opt[0]"
          >{{ opt[1] }}</button>
        </div>
        <p v-else class="empty-hint">本科室未配置影像数据源，请联系管理员。</p>
        <ul class="study-list">
          <li v-if="!filteredStudies.length" class="empty-hint">
            暂无该类型影像。腹部 CT 演示：
            <code>python scripts/fetch_demo_datasets.py --mimic-ct</code>
          </li>
          <li
            v-for="s in filteredStudies"
            :key="s.study_id"
            :class="{ active: selectedStudy?.study_id === s.study_id }"
            @click="selectStudy(s)"
          >
            <span class="mod">{{ s.modality }}</span>
            {{ s.title }}
            <small v-if="s.collection">{{ s.collection }}</small>
            <small>{{ s.volume_path ? '3D NIfTI' : `${s.slice_count} 张` }}</small>
          </li>
        </ul>

        <div v-if="hasVolume" class="view-mode">
          <button
            type="button"
            class="mode-btn"
            :class="{ active: viewMode === 'mpr' }"
            @click="viewMode = 'mpr'"
          >3D MPR</button>
          <button
            type="button"
            class="mode-btn"
            :class="{ active: viewMode === 'gallery' }"
            @click="viewMode = 'gallery'"
          >2D 切片库</button>
        </div>

        <h3>分割模型（病灶 / 器官，串行）</h3>
        <label v-for="m in compatibleModels" :key="m.model_id" class="model-check">
          <input type="checkbox" :checked="selectedModels.includes(m.model_id)" @change="toggleModel(m.model_id)" />
          <span>
            <strong>{{ m.name }}</strong>
            <small>{{ m.description }}</small>
            <em v-if="m.task === 'lesion'" class="lesion-tag">病灶</em>
            <em v-if="!m.weights_present" class="warn">权重未下载</em>
          </span>
        </label>

        <label class="label">{{ showLesionTarget ? '病灶 / 肿瘤区域' : 'VISTA3D 器官' }}</label>
        <select v-model="organ" class="select">
          <option v-for="opt in targetOptions" :key="opt" :value="opt">{{ opt }}</option>
        </select>

        <button class="btn-primary full" :disabled="segmenting || loading || !selectedModels.length" @click="runSegmentation">
          {{ segmenting ? '分割中（3D 较慢，请稍候）…' : (viewMode === 'mpr' && hasVolume ? '运行 3D 分割' : '运行 2D 分割') }}
        </button>
      </aside>

      <section class="viewer card">
        <template v-if="viewMode === 'mpr' && selectedStudy?.volume_path">
          <div class="viewer-toolbar">
            <button class="btn-primary" @click="captureScreenshot">截取当前视图</button>
            <span v-if="volumeMaskPath" class="mask-tag">3D Mask 已生成</span>
          </div>
          <div ref="viewerRef">
            <VolumeMprViewer
              :volume-path="selectedStudy.volume_path"
              :overlay-path="vista3dOverlayMask"
              :axis="mprAxis"
              :slice-index="mprIndex"
              @update:axis="mprAxis = $event"
              @update:slice-index="mprIndex = $event"
            />
          </div>
        </template>

        <template v-else>
          <div class="viewer-toolbar">
            <button class="btn-secondary" :disabled="sliceIndex <= 0" @click="sliceIndex--">上一张</button>
            <span>{{ sliceIndex + 1 }} / {{ selectedStudy?.image_paths.length ?? 0 }}</span>
            <button
              class="btn-secondary"
              :disabled="!selectedStudy || sliceIndex >= selectedStudy.image_paths.length - 1"
              @click="sliceIndex++"
            >下一张</button>
            <button class="btn-primary" @click="captureScreenshot">截取当前视图</button>
          </div>

          <div ref="viewerRef" class="viewer-canvas">
            <ImagingFileImage v-if="currentImage" :path="currentImage" alt="study slice" />
          </div>
        </template>

        <div v-if="segmentResults.length" class="overlays">
          <h4>本次分割结果</h4>
          <div class="overlay-row">
            <figure v-for="r in segmentResults" :key="r.model_id">
              <ImagingFileImage :path="r.overlay_path" :alt="r.model_id" />
              <figcaption>
                {{ r.model_id }} · {{ r.duration_ms.toFixed(0) }}ms · +{{ r.memory_mb.toFixed(1) }}MB
                <br /><small>{{ r.notes }}</small>
              </figcaption>
            </figure>
          </div>
        </div>

        <div v-if="segmentHistory.length" class="overlays history">
          <h4>
            历史分割（当前切片）
            <small>已选 {{ selectedOverlayPaths.length }} 张 → 供 VLM 查阅</small>
          </h4>
          <div v-for="run in segmentHistory" :key="run.run_id" class="history-run">
            <p class="run-meta">{{ run.created_at.slice(0, 19).replace('T', ' ') }} · {{ run.model_ids.join(', ') }}</p>
            <div class="overlay-row">
              <figure
                v-for="r in run.results"
                :key="overlayKey(run.run_id, r.model_id)"
                :class="{ selected: isOverlaySelected(run.run_id, r.model_id) }"
                @click="toggleOverlaySelection(run.run_id, r.model_id)"
              >
                <label class="overlay-check">
                  <input
                    type="checkbox"
                    :checked="isOverlaySelected(run.run_id, r.model_id)"
                    @click.stop
                    @change="toggleOverlaySelection(run.run_id, r.model_id)"
                  />
                  <ImagingFileImage :path="r.overlay_path" :alt="r.model_id" />
                </label>
                <figcaption>
                  {{ r.model_id }}
                  <br /><small>{{ r.notes }}</small>
                </figcaption>
              </figure>
            </div>
          </div>
        </div>

        <div v-if="screenshots.length" class="shots">
          <h4>已截截图 ({{ screenshots.length }})</h4>
          <div class="overlay-row">
            <figure v-for="s in screenshots" :key="s.path">
              <ImagingFileImage :path="s.path" :alt="s.caption" />
            </figure>
          </div>
        </div>
      </section>
    </div>

    <section class="card report-panel">
      <div v-if="selectedStudy" class="report-history">
        <div class="history-head">
          <h3>历史报告</h3>
          <button
            type="button"
            class="btn-secondary btn-sm"
            :disabled="reportsLoading"
            @click="loadPatientReports"
          >
            {{ reportsLoading ? '加载中…' : '刷新' }}
          </button>
        </div>
        <p v-if="reportsLoading" class="muted">正在加载 {{ selectedStudy.patient_id }} 的历史报告…</p>
        <ul v-else-if="savedReports.length" class="history-list">
          <li v-for="r in savedReports" :key="r.report_id">
            <button
              type="button"
              class="history-item"
              :class="{ active: report?.report_id === r.report_id }"
              @click="loadSavedReport(r.report_id)"
            >
              <strong>{{ r.report_id.slice(0, 8) }}…</strong>
              <span>{{ r.imaging_session_id || r.modalities.join(', ') }}</span>
              <small>{{ new Date(r.created_at).toLocaleString() }}</small>
            </button>
          </li>
        </ul>
        <p v-else class="muted">该患者暂无已保存报告</p>
      </div>

      <p v-if="hasVlmSourceImages" class="hint-muted">
        VLM/报告使用影像原片（{{ vlmSourceImagePaths.length }} 张），不依赖分割 overlay。
        <span v-if="analysisFromCache">· 已加载缓存</span>
      </p>

      <label class="label">病历 / 临床描述</label>
      <textarea v-model="clinicalText" class="textarea" rows="3" />

      <label class="model-check include-src">
        <input v-model="runMedicationReview" type="checkbox" />
        <span>完整报告时启用用药审查流水线（规则审查 → 多智能体）</span>
      </label>

      <div v-if="vlmAnalysis || candidateDrugs.length" class="med-form card-inline">
        <h4>用药推荐与临床上下文（可编辑）</h4>
        <p class="hint-muted">VLM 查阅后自动填入，格式与多智能体会诊一致；确认后可一键发起用药安全分析。</p>

        <div class="field">
          <label class="label">病症 / 诊断</label>
          <ul v-if="imagingPatient.diagnoses?.length" class="tag-list">
            <li v-for="(dx, i) in imagingPatient.diagnoses" :key="i">
              <span>{{ dx.name }}<small v-if="dx.icd9_code"> · {{ dx.icd9_code }}</small></span>
              <button type="button" class="btn-ghost" @click="removeImagingDiagnosis(i)">×</button>
            </li>
          </ul>
          <p v-else class="empty-hint">尚未添加诊断（VLM 会自动推断）</p>
          <div class="add-drug">
            <input v-model="newDiagnosis" class="input" placeholder="如：重症社区获得性肺炎" @keyup.enter="addImagingDiagnosis" />
            <button type="button" class="btn-secondary" @click="addImagingDiagnosis">添加</button>
          </div>
        </div>

        <div class="field">
          <label class="label">过敏史</label>
          <ul v-if="imagingPatient.allergies?.length" class="tag-list">
            <li v-for="(a, i) in imagingPatient.allergies" :key="i">
              <span>{{ a }}</span>
              <button type="button" class="btn-ghost" @click="removeImagingAllergy(i)">×</button>
            </li>
          </ul>
          <p v-else class="empty-hint">无已知过敏 / 待补充</p>
          <div class="add-drug">
            <input v-model="newAllergy" class="input" placeholder="如：青霉素" @keyup.enter="addImagingAllergy" />
            <button type="button" class="btn-secondary" @click="addImagingAllergy">添加</button>
          </div>
        </div>

        <div class="field">
          <label class="label">当前用药</label>
          <ul v-if="imagingPatient.current_medications?.length" class="drug-list">
            <li v-for="(m, i) in imagingPatient.current_medications" :key="i">
              <strong>{{ m.name }}</strong>
              <span v-for="(part, j) in drugDetailParts(m)" :key="j" class="drug-meta">{{ part }}</span>
              <button type="button" class="btn-ghost" @click="removeCurrentMedication(i)">×</button>
            </li>
          </ul>
          <p v-else class="empty-hint">尚未添加当前用药</p>
          <div class="add-drug">
            <input v-model="newCurrentMed" class="input" placeholder="药名" @keyup.enter="addCurrentMedication" />
            <button type="button" class="btn-secondary" @click="addCurrentMedication">添加</button>
          </div>
        </div>

        <div class="field">
          <label class="label">候选用药</label>
          <ul v-if="candidateDrugs.length" class="drug-list">
            <li v-for="(d, i) in candidateDrugs" :key="i">
              <strong>{{ d.name }}</strong>
              <span v-for="(part, j) in drugDetailParts(d)" :key="j" class="drug-meta">{{ part }}</span>
              <span v-if="d.indication" class="drug-meta">{{ d.indication }}</span>
              <button type="button" class="btn-ghost" @click="removeCandidateDrug(i)">×</button>
            </li>
          </ul>
          <p v-else class="empty-hint">尚未添加候选用药 — 请先运行 VLM 查阅或手动添加</p>
          <div class="add-drug">
            <input v-model="newDrugName" class="input" placeholder="药名" @keyup.enter="addCandidateDrug" />
            <button type="button" class="btn-secondary" @click="addCandidateDrug">添加</button>
          </div>
        </div>

        <button
          class="btn-primary med-analyze-btn"
          type="button"
          :disabled="medConsultLoading || !candidateDrugs.length"
          @click="runMedicationAnalysis"
        >
          <span v-if="medConsultLoading" class="spinner" />
          {{ medConsultLoading ? '用药安全分析中…' : '发起用药安全分析（规则 + 多智能体）' }}
        </button>
        <p v-if="medConsultError" class="error">{{ medConsultError }}</p>
      </div>

      <div class="action-row">
        <button
          class="btn-primary"
          :disabled="loading || !hasVlmSourceImages"
          @click="runVlmConsult(false)"
        >
          <span v-if="reportTask === 'vlm'" class="spinner" />
          {{
            reportTask === 'vlm'
              ? `VLM 查阅中… ${formatElapsed(taskElapsedMs)}`
              : `Qwen VLM 查阅（原片 ${vlmSourceImagePaths.length} 张）`
          }}
        </button>
        <button
          class="btn-ghost"
          type="button"
          :disabled="loading || !hasVlmSourceImages"
          title="忽略缓存，重新调用 Qwen + DeepSeek"
          @click="runVlmConsult(true)"
        >
          强制刷新
        </button>
        <button
          class="btn-secondary"
          :disabled="loading || !hasVlmSourceImages"
          @click="generateReport"
        >
          <span v-if="reportTask === 'report'" class="spinner" />
          {{
            reportTask === 'report'
              ? `报告生成中… ${formatElapsed(taskElapsedMs)}`
              : '生成完整报告（VLM → 规则审查 → 多智能体）'
          }}
        </button>
      </div>

      <div v-if="reportTask" class="task-status" role="status" aria-live="polite">
        <template v-if="reportTask === 'vlm'">
          <strong>正在调用 Qwen VLM 分析原片…</strong>
          <span>已用时 {{ formatElapsed(taskElapsedMs) }}</span>
          <p class="task-hint">通常需 10–60 秒，请稍候</p>
        </template>
        <template v-else>
          <strong>正在生成完整报告（VLM → 规则审查 → 多智能体）…</strong>
          <span>已用时 {{ formatElapsed(taskElapsedMs) }}</span>
          <p class="task-hint">完整流水线通常需 1–4 分钟，请保持页面打开</p>
        </template>
      </div>

      <template v-if="vlmAnalysis">
        <hr class="divider" />
        <p class="meta">
          模型 {{ vlmModel }}
          <span v-if="analysisFromCache">· 缓存</span>
          · 原片 {{ vlmImagesUsed.length }} 张
          · 耗时 {{ formatElapsed(vlmDurationMs) }}
          <span v-if="vlmCaseId">
            · Case:
            <RouterLink :to="`/cases/${vlmCaseId}`"><code>{{ vlmCaseId }}</code></RouterLink>
          </span>
        </p>
        <ul v-if="vlmImagesUsed.length" class="used-images">
          <li v-for="p in vlmImagesUsed" :key="p">{{ p.split('/').slice(-2).join('/') }}</li>
        </ul>
        <div v-if="vlmAnalysis.imaging_findings" class="report-section">
          <h4>影像学发现</h4>
          <p>{{ vlmAnalysis.imaging_findings }}</p>
        </div>
        <div v-if="vlmAnalysis.clinical_analysis" class="report-section">
          <h4>临床分析</h4>
          <p>{{ vlmAnalysis.clinical_analysis }}</p>
        </div>
        <div v-if="vlmAnalysis.medication_recommendation" class="report-section">
          <h4>用药建议（文本）</h4>
          <p>{{ vlmAnalysis.medication_recommendation }}</p>
        </div>
        <div v-if="vlmAnalysis.reasoning" class="cot-block">
          <strong>推理</strong>
          {{ vlmAnalysis.reasoning }}
        </div>
      </template>

      <template v-if="medConsultResult">
        <hr class="divider" />
        <div class="med-result">
          <h3>用药安全分析结果</h3>
          <div class="card final-card">
            <h4>最终建议</h4>
            <RiskBadge
              v-if="medConsultArb"
              :level="medConsultArb.consensus_risk_level"
              :block="medConsultArb.consensus_block_decision"
            />
            <p class="final-text">{{ medConsultResult.final_recommendation }}</p>
            <p v-if="medConsultResult.case_id" class="case-id">
              Case:
              <RouterLink :to="`/cases/${medConsultResult.case_id}`">
                <code>{{ medConsultResult.case_id }}</code>
              </RouterLink>
            </p>
          </div>
          <RuleReviewSummary :rule-output="medConsultResult.rule_output" />
          <DebatePanel
            :debate="medConsultResult.debate"
            :safety-panel="medConsultResult.safety_panel"
          />
          <div v-if="medConsultArb" class="card">
            <h4>会诊主席仲裁</h4>
            <p>{{ medConsultArb.arbitration_notes }}</p>
            <p v-if="medConsultArb.conflict_detected" class="conflict">检测到专家意见冲突</p>
          </div>
          <div class="agents-grid">
            <h4>专家意见 ({{ medConsultResult.agent_opinions.length }})</h4>
            <AgentOpinionCard
              v-for="o in medConsultResult.agent_opinions"
              :key="o.agent_id"
              :opinion="o"
            />
          </div>
        </div>
      </template>

      <template v-if="report">
        <hr class="divider" />
        <p class="meta">
          报告 ID: {{ report.report_id }} · 会话: {{ report.imaging_session_id }} ·
          {{ report.created_at }}
          <span v-if="reportDurationMs"> · 生成耗时 {{ formatElapsed(reportDurationMs) }}</span>
          <span v-if="report.metadata?.medication_review_ran === false" class="info-tag">未跑用药审查</span>
          <span v-if="report.metadata?.medication_review_error" class="warn-tag">用药审查未完成</span>
        </p>
        <p v-if="report.metadata?.medication_review_error" class="err inline-err">
          {{ report.metadata.medication_review_error }}
        </p>

        <RuleReviewSummary v-if="reportRuleOutput" :rule-output="reportRuleOutput" />

        <div v-for="p in sortedParagraphs" :key="p.paragraph_id" class="report-section">
          <h4>{{ p.title }}</h4>
          <p>{{ p.content }}</p>
        </div>

        <div v-if="report.chain_of_thought" class="cot-block">
          <strong>思维链</strong>
          {{ report.chain_of_thought }}
        </div>

        <div v-if="report.supplements.length" class="supplements">
          <h4>医生追问补充</h4>
          <div v-for="s in report.supplements" :key="s.supplement_id" class="sup-item">
            <p><strong>Q:</strong> {{ s.question }}</p>
            <p><strong>A:</strong> {{ s.answer }}</p>
          </div>
        </div>

        <div class="qa-row">
          <input v-model="qaQuestion" class="input" placeholder="基于报告段落 RAG 追问…" />
          <button class="btn-secondary" :disabled="loading" @click="askReport">追问</button>
        </div>
        <p v-if="qaAnswer" class="qa-ans">{{ qaAnswer }}</p>
      </template>
    </section>
  </div>
</template>

<style scoped>
.page-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem; }
h1 { font-size: 1.35rem; color: var(--primary-dark); }
.sub { color: var(--text-muted); font-size: 0.88rem; margin-top: 0.25rem; }
.mem-badge { background: var(--primary-light); color: var(--primary-dark); padding: 0.35rem 0.65rem; border-radius: var(--radius); font-size: 0.82rem; }
.err { color: var(--danger); margin-bottom: 0.75rem; }
.config-banner {
  background: #fff3e0;
  color: #e65100;
  border: 1px solid #ffcc80;
  padding: 0.65rem 0.85rem;
  border-radius: var(--radius);
  margin-bottom: 0.75rem;
  font-size: 0.88rem;
}
.info-banner {
  background: #e8f5e9;
  color: #2e7d32;
  border: 1px solid #a5d6a7;
  padding: 0.65rem 0.85rem;
  border-radius: var(--radius);
  margin-bottom: 0.75rem;
  font-size: 0.88rem;
}
.info-tag { color: #1565c0; font-weight: 600; margin-left: 0.35rem; }
.warn-tag { color: #e65100; font-weight: 600; margin-left: 0.35rem; }
.inline-err { font-size: 0.85rem; margin: 0.35rem 0 0.75rem; }
.used-images { font-size: 0.75rem; color: var(--text-muted); margin: 0 0 0.75rem 1.1rem; }
.include-src { margin: 0.5rem 0 0.25rem; }
.hint-inline { display: block; color: var(--text-muted); font-size: 0.75rem; margin-top: 0.15rem; }
.grid-main { display: grid; grid-template-columns: 280px 1fr; gap: 1rem; margin-bottom: 1rem; }
@media (max-width: 960px) { .grid-main { grid-template-columns: 1fr; } }
.panel h3 { font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; margin: 0.75rem 0 0.5rem; }
.study-list { list-style: none; max-height: 200px; overflow-y: auto; margin-bottom: 0.5rem; }
.study-list li { padding: 0.45rem 0.5rem; border-radius: var(--radius); cursor: pointer; font-size: 0.85rem; border: 1px solid transparent; }
.study-list li:hover { background: var(--surface-2); }
.study-list li.active { background: var(--primary-light); border-color: var(--primary); }
.mod { display: inline-block; background: var(--primary); color: #fff; font-size: 0.65rem; padding: 0.1rem 0.35rem; border-radius: 3px; margin-right: 0.35rem; }
.study-list small { display: block; color: var(--text-muted); font-size: 0.72rem; }
.empty-hint { cursor: default !important; color: var(--text-muted); font-size: 0.8rem; line-height: 1.4; padding: 0.75rem !important; }
.empty-hint code { font-size: 0.7rem; word-break: break-all; }
.view-mode { display: flex; gap: 0.35rem; margin-bottom: 0.5rem; }
.mode-btn {
  flex: 1;
  padding: 0.35rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  font-size: 0.78rem;
  cursor: pointer;
}
.mode-btn.active { background: var(--primary); color: #fff; border-color: var(--primary); }
.model-check { display: flex; gap: 0.5rem; align-items: flex-start; margin-bottom: 0.5rem; font-size: 0.85rem; cursor: pointer; }
.model-check small { display: block; color: var(--text-muted); font-size: 0.75rem; }
.model-check .warn { color: var(--warning); font-style: normal; font-size: 0.72rem; }
.model-check .lesion-tag { color: var(--primary-dark); font-style: normal; font-size: 0.72rem; margin-left: 0.25rem; }
.full { width: 100%; margin-top: 0.75rem; }
.viewer-toolbar { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.75rem; flex-wrap: wrap; }
.mask-tag { font-size: 0.78rem; color: var(--primary-dark); background: var(--primary-light); padding: 0.2rem 0.5rem; border-radius: var(--radius); }
.viewer-canvas { background: #000; border-radius: var(--radius); overflow: hidden; min-height: 280px; display: flex; align-items: center; justify-content: center; }
.viewer-canvas img { max-width: 100%; max-height: 420px; object-fit: contain; }
.overlays, .shots { margin-top: 1rem; }
.overlays h4, .shots h4 { font-size: 0.85rem; margin-bottom: 0.5rem; }
.overlay-row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
.overlay-row figure { max-width: 200px; }
.overlay-row :deep(img) { width: 100%; border: 1px solid var(--border); border-radius: var(--radius); }
.overlay-row figcaption { font-size: 0.72rem; color: var(--text-muted); }
.history h4 small { font-weight: normal; color: var(--text-muted); margin-left: 0.5rem; }
.history-run { margin-bottom: 0.75rem; padding-bottom: 0.5rem; border-bottom: 1px dashed var(--border); }
.run-meta { font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.35rem; }
.overlay-row figure { cursor: pointer; border-radius: var(--radius); padding: 0.25rem; border: 2px solid transparent; }
.overlay-row figure.selected { border-color: var(--primary); background: var(--primary-light); }
.overlay-check { display: block; position: relative; }
.overlay-check input { position: absolute; top: 0.35rem; left: 0.35rem; z-index: 1; }
.action-row { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.75rem; }
.action-row .btn-primary,
.action-row .btn-secondary { display: inline-flex; align-items: center; gap: 0.45rem; }
.task-status {
  margin-top: 0.75rem;
  padding: 0.65rem 0.85rem;
  border-radius: var(--radius);
  background: var(--primary-light);
  border: 1px solid color-mix(in srgb, var(--primary) 35%, transparent);
  font-size: 0.88rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.task-status strong { color: var(--primary-dark); }
.task-status span { color: var(--text-muted); font-size: 0.82rem; }
.task-hint { margin: 0; font-size: 0.78rem; color: var(--text-muted); }
.report-panel { margin-top: 0.5rem; }
.divider { border: none; border-top: 1px solid var(--border); margin: 1rem 0; }
.meta { font-size: 0.78rem; color: var(--text-muted); margin-bottom: 0.75rem; }
.sup-item { background: var(--surface-2); padding: 0.65rem; border-radius: var(--radius); margin-bottom: 0.5rem; font-size: 0.88rem; }
.qa-row { display: flex; gap: 0.5rem; margin-top: 1rem; }
.qa-ans { margin-top: 0.5rem; padding: 0.65rem; background: var(--primary-light); border-radius: var(--radius); font-size: 0.9rem; }
.report-history { margin-bottom: 1rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border); }
.history-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
.history-head h3 { font-size: 0.95rem; margin: 0; }
.btn-sm { padding: 0.25rem 0.55rem; font-size: 0.78rem; }
.history-list { list-style: none; display: flex; flex-direction: column; gap: 0.35rem; max-height: 160px; overflow-y: auto; }
.history-item {
  width: 100%;
  text-align: left;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.45rem 0.6rem;
  cursor: pointer;
  font-size: 0.82rem;
}
.history-item:hover { border-color: var(--primary); }
.history-item.active { background: var(--primary-light); border-color: var(--primary); }
.history-item span { display: block; color: var(--text-muted); font-size: 0.78rem; }
.history-item small { color: var(--text-muted); font-size: 0.72rem; }
.muted, .hint-muted { color: var(--text-muted); font-size: 0.85rem; }
.hint-muted { margin-bottom: 0.75rem; }
.card-inline {
  margin: 0.75rem 0;
  padding: 0.85rem;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.card-inline h4 { margin: 0 0 0.35rem; font-size: 0.95rem; }
.field { margin-bottom: 0.75rem; }
.label { display: block; font-size: 0.82rem; font-weight: 600; margin-bottom: 0.35rem; }
.drug-list { list-style: none; margin-bottom: 0.5rem; }
.drug-list li {
  display: flex; flex-wrap: wrap; align-items: center; gap: 0.35rem;
  padding: 0.35rem 0.5rem; background: var(--surface); border-radius: var(--radius); margin-bottom: 0.35rem;
}
.drug-meta { font-size: 0.78rem; color: var(--text-muted); }
.tag-list { list-style: none; margin-bottom: 0.5rem; }
.tag-list li {
  display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;
  padding: 0.35rem 0.5rem; background: var(--surface); border-radius: var(--radius); margin-bottom: 0.35rem;
}
.tag-list small { color: var(--text-muted); font-weight: normal; }
.empty-hint { font-size: 0.82rem; color: var(--text-muted); margin: 0 0 0.35rem; }
.add-drug { display: flex; gap: 0.5rem; }
.add-drug .input { flex: 1; }
.med-analyze-btn { width: 100%; margin-top: 0.35rem; display: inline-flex; align-items: center; justify-content: center; gap: 0.45rem; }
.med-result { margin-top: 0.5rem; }
.med-result h3 { font-size: 1rem; margin-bottom: 0.75rem; }
.final-card { background: var(--surface-2); padding: 0.75rem; border-radius: var(--radius); margin-bottom: 0.75rem; }
.final-text { margin: 0.5rem 0 0; line-height: 1.55; }
.case-id { font-size: 0.82rem; color: var(--text-muted); margin-top: 0.5rem; }
.conflict { color: var(--danger); font-size: 0.88rem; }
.agents-grid { display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.75rem; }
.error { color: var(--danger); font-size: 0.88rem; margin-top: 0.35rem; }
</style>
