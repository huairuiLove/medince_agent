<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import VolumeMprViewer from '@/components/imaging/VolumeMprViewer.vue'
import { medsafeApi, imagingFileUrl } from '@/api/medsafe'
import type {
  ClinicalReport,
  ImagingStudy,
  ModelId,
  SegModelInfo,
  SegmentResultItem,
  SegmentRunRecord,
  VolumeAxis,
  VlmAnalysis,
} from '@/types'

const studies = ref<ImagingStudy[]>([])
const sourceFilter = ref<'all' | 'mimic_cxr' | 'chest_ct' | 'kits19' | 'brats2024'>('all')
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
const includeSourceImage = ref(false)
const runMedicationReview = ref(false)
const candidateDrugText = ref('')
const qaQuestion = ref('')
const qaAnswer = ref('')
const viewerRef = ref<HTMLDivElement | null>(null)
const memoryPeak = ref(0)
const volumeMaskPath = ref<string | null>(null)

const filteredStudies = computed(() => {
  if (sourceFilter.value === 'all') return studies.value
  return studies.value.filter(s => s.source === sourceFilter.value)
})

async function loadStudies() {
  const res = await medsafeApi.listImagingStudies(
    sourceFilter.value === 'all' ? undefined : sourceFilter.value,
  )
  studies.value = res.studies
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
  if (s.source === 'kits19' || s.source === 'chest_ct') return ['totalsegmentator', 'vista3d']
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

const selectedSegmentSummary = computed(() => {
  const parts: string[] = []
  for (const run of segmentHistory.value) {
    for (const r of run.results) {
      if (selectedOverlayKeys.value.has(overlayKey(run.run_id, r.model_id))) {
        parts.push(`${r.model_id} (${run.created_at.slice(0, 16)}): ${r.notes}`)
      }
    }
  }
  return parts.join('; ')
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

watch(sourceFilter, () => {
  void loadStudies()
})

watch([currentSegmentImagePath, mprAxis, mprIndex, sliceIndex, viewMode], () => {
  if (selectedStudy.value) {
    selectedOverlayKeys.value = new Set()
    void loadSegmentHistory()
  }
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
  vlmAnalysis.value = null
  volumeMaskPath.value = null
  qaAnswer.value = ''
  qaQuestion.value = ''
  selectedModels.value = defaultModelsForStudy(s)
  organ.value = defaultTargetForStudy(s)
  clinicalText.value = s.report_text?.trim()
    ? s.report_text
    : `${s.title} — ${s.modality} 影像会诊`
  void loadSegmentHistory()
  void loadPatientReports()
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

  loading.value = true
  error.value = ''
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
    loading.value = false
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

function parseCandidateDrugs(raw: string): { name: string; dose?: string; route?: string }[] {
  const text = raw.trim()
  if (!text) return []
  if (text.startsWith('[')) {
    try {
      const parsed = JSON.parse(text) as unknown
      if (Array.isArray(parsed)) {
        return parsed.map(item =>
          typeof item === 'string' ? { name: item } : (item as { name: string; dose?: string; route?: string }),
        )
      }
    } catch {
      /* fall through */
    }
  }
  return text.split(/[,，、\n]/).map(s => s.trim()).filter(Boolean).map(name => ({ name }))
}

async function generateReport() {
  if (!selectedStudy.value) return
  if (runMedicationReview.value && !candidateDrugText.value.trim()) {
    error.value = '已启用用药多智能体审查，请填写候选药物（如：阿莫西林 500mg PO）'
    return
  }
  loading.value = true
  error.value = ''
  try {
    report.value = await medsafeApi.generateReport({
      patient_id: selectedStudy.value.patient_id,
      clinical_text: clinicalText.value,
      primary_modality: selectedStudy.value.modality,
      modalities: [selectedStudy.value.modality],
      imaging_session_label: selectedStudy.value.study_id,
      image_paths: includeSourceImage.value ? [currentSegmentImagePath.value].filter(Boolean) : [],
      overlay_paths: selectedOverlayPaths.value,
      screenshot_paths: screenshots.value.map(s => s.path),
      models_used: selectedModels.value,
      segmentation_summary: selectedSegmentSummary.value,
      include_source_image: includeSourceImage.value,
      run_medication_review: runMedicationReview.value,
      candidate_drugs: parseCandidateDrugs(candidateDrugText.value),
    })
    await loadPatientReports()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function runVlmConsult() {
  if (!selectedStudy.value) return
  if (!selectedOverlayPaths.value.length) {
    error.value = '请至少选中一张分割 overlay 再提交 VLM 查阅'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const res = await medsafeApi.analyzeWithVlm({
      clinical_text: clinicalText.value,
      primary_modality: selectedStudy.value.modality,
      overlay_paths: selectedOverlayPaths.value,
      include_source_image: includeSourceImage.value,
      segmentation_summary: selectedSegmentSummary.value,
    })
    vlmAnalysis.value = res.analysis
    vlmModel.value = res.model
    vlmImagesUsed.value = res.images_used
    vlmDurationMs.value = res.duration_ms
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
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
        <p class="sub">病灶分割（MIMIC CXR / BraTS）· 器官分割 · Qwen VLM 报告</p>
      </div>
      <div v-if="memoryPeak" class="mem-badge">峰值内存 ~{{ memoryPeak.toFixed(0) }} MB</div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>
    <p v-if="!vlmConfigured" class="config-banner">{{ vlmHint }}</p>

    <div class="grid-main">
      <aside class="card panel">
        <h3>影像检查</h3>
        <div class="source-filter">
          <button
            v-for="opt in ([['all', '全部'], ['mimic_cxr', '胸片 XR'], ['chest_ct', '胸部/肺 CT'], ['kits19', '肾脏 CT'], ['brats2024', '脑 MRI']] as const)"
            :key="opt[0]"
            type="button"
            class="mode-btn"
            :class="{ active: sourceFilter === opt[0] }"
            @click="sourceFilter = opt[0]"
          >{{ opt[1] }}</button>
        </div>
        <ul class="study-list">
          <li v-if="!filteredStudies.length" class="empty-hint">
            暂无该类型影像。运行：
            <code>python data/scripts/fetch_demo_datasets.py --chest-ct --kits-cases 8 --monai-samples --nlmcxr-map 50</code>
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

        <button class="btn-primary full" :disabled="loading || !selectedModels.length" @click="runSegmentation">
          {{ viewMode === 'mpr' && hasVolume ? '运行 3D 分割' : '运行 2D 分割' }}
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
            <img v-if="currentImage" :src="imagingFileUrl(currentImage)" alt="study slice" />
          </div>
        </template>

        <div v-if="segmentResults.length" class="overlays">
          <h4>本次分割结果</h4>
          <div class="overlay-row">
            <figure v-for="r in segmentResults" :key="r.model_id">
              <img :src="imagingFileUrl(r.overlay_path)" :alt="r.model_id" />
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
                  <img :src="imagingFileUrl(r.overlay_path)" :alt="r.model_id" />
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
              <img :src="imagingFileUrl(s.path)" :alt="s.caption" />
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

      <label class="label">病历 / 临床描述</label>
      <textarea v-model="clinicalText" class="textarea" rows="3" />

      <label class="model-check include-src">
        <input v-model="includeSourceImage" type="checkbox" />
        <span>同时提交原图（overlay 已含底图，默认不勾选）</span>
      </label>

      <label class="model-check include-src">
        <input v-model="runMedicationReview" type="checkbox" />
        <span>启用用药多智能体审查（需填写候选药物，否则仅生成影像会诊报告）</span>
      </label>
      <textarea
        v-if="runMedicationReview"
        v-model="candidateDrugText"
        class="textarea"
        rows="2"
        placeholder="候选药物，如：阿莫西林 500mg PO；华法林 3mg PO（逗号或换行分隔）"
      />

      <div class="action-row">
        <button
          class="btn-primary"
          :disabled="loading || !selectedOverlayPaths.length"
          @click="runVlmConsult"
        >
          Qwen VLM 查阅（已选 {{ selectedOverlayPaths.length }} 张 overlay）
        </button>
        <button class="btn-secondary" :disabled="loading" @click="generateReport">
          生成完整用药安全报告（VLM + DeepSeek + 多智能体）
        </button>
      </div>

      <template v-if="vlmAnalysis">
        <hr class="divider" />
        <p class="meta">
          模型 {{ vlmModel }}
          · 提交 {{ vlmImagesUsed.length }} 张（overlay {{ selectedOverlayPaths.length
          }}{{ includeSourceImage ? ' + 原图' : '' }}）
          · 耗时 {{ vlmDurationMs.toFixed(0) }}ms
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
          <h4>用药建议</h4>
          <p>{{ vlmAnalysis.medication_recommendation }}</p>
        </div>
        <div v-if="vlmAnalysis.reasoning" class="cot-block">
          <strong>推理</strong>
          {{ vlmAnalysis.reasoning }}
        </div>
      </template>

      <template v-if="report">
        <hr class="divider" />
        <p class="meta">
          报告 ID: {{ report.report_id }} · 会话: {{ report.imaging_session_id }} ·
          {{ report.created_at }}
          <span v-if="report.metadata?.medication_review_ran === false" class="info-tag">未跑用药审查</span>
        </p>

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
.info-tag { color: #1565c0; font-weight: 600; margin-left: 0.35rem; }
.used-images { font-size: 0.75rem; color: var(--text-muted); margin: 0 0 0.75rem 1.1rem; }
.include-src { margin: 0.5rem 0 0.25rem; }
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
.overlay-row img { width: 100%; border: 1px solid var(--border); border-radius: var(--radius); }
.overlay-row figcaption { font-size: 0.72rem; color: var(--text-muted); }
.history h4 small { font-weight: normal; color: var(--text-muted); margin-left: 0.5rem; }
.history-run { margin-bottom: 0.75rem; padding-bottom: 0.5rem; border-bottom: 1px dashed var(--border); }
.run-meta { font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.35rem; }
.overlay-row figure { cursor: pointer; border-radius: var(--radius); padding: 0.25rem; border: 2px solid transparent; }
.overlay-row figure.selected { border-color: var(--primary); background: var(--primary-light); }
.overlay-check { display: block; position: relative; }
.overlay-check input { position: absolute; top: 0.35rem; left: 0.35rem; z-index: 1; }
.action-row { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.75rem; }
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
.muted { color: var(--text-muted); font-size: 0.85rem; }
</style>
