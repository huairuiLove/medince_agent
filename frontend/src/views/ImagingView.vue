<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { medsafeApi, imagingFileUrl } from '@/api/medsafe'
import type { ClinicalReport, ImagingStudy, ModelId, SegModelInfo, SegmentResultItem } from '@/types'

const studies = ref<ImagingStudy[]>([])
const models = ref<SegModelInfo[]>([])
const selectedStudy = ref<ImagingStudy | null>(null)
const selectedModels = ref<ModelId[]>(['sam2d'])
const sliceIndex = ref(0)
const clinicalText = ref('')
const organ = ref('brain')
const loading = ref(false)
const error = ref('')
const segmentResults = ref<SegmentResultItem[]>([])
const screenshots = ref<{ path: string; caption: string }[]>([])
const report = ref<ClinicalReport | null>(null)
const qaQuestion = ref('')
const qaAnswer = ref('')
const viewerRef = ref<HTMLDivElement | null>(null)
const memoryPeak = ref(0)

const currentImage = computed(() => {
  if (!selectedStudy.value?.image_paths.length) return ''
  const idx = Math.min(sliceIndex.value, selectedStudy.value.image_paths.length - 1)
  return selectedStudy.value.image_paths[idx]
})

const overlayPaths = computed(() => segmentResults.value.map(r => r.overlay_path))

onMounted(async () => {
  try {
    studies.value = (await medsafeApi.listImagingStudies()).studies
    models.value = (await medsafeApi.listSegmentModels()).models
    if (studies.value.length) selectStudy(studies.value[0])
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})

function selectStudy(s: ImagingStudy) {
  selectedStudy.value = s
  sliceIndex.value = 0
  segmentResults.value = []
  screenshots.value = []
  report.value = null
  clinicalText.value = `${s.title} — ${s.modality} 影像会诊`
}

function toggleModel(id: ModelId) {
  const i = selectedModels.value.indexOf(id)
  if (i >= 0) selectedModels.value.splice(i, 1)
  else selectedModels.value.push(id)
}

async function runSegmentation() {
  if (!currentImage.value || !selectedModels.value.length) return
  loading.value = true
  error.value = ''
  try {
    const res = await medsafeApi.segment({
      image_path: currentImage.value,
      model_ids: selectedModels.value,
      organ: organ.value,
    })
    segmentResults.value = res.results
    memoryPeak.value = res.memory_peak_mb
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
  const res = await medsafeApi.saveScreenshot({
    patient_id: selectedStudy.value.patient_id,
    study_id: selectedStudy.value.study_id,
    image_data: dataUrl,
    caption: `slice_${sliceIndex.value}`,
  })
  screenshots.value.push({ path: res.path, caption: res.caption })
}

async function generateReport() {
  if (!selectedStudy.value) return
  loading.value = true
  error.value = ''
  try {
    report.value = await medsafeApi.generateReport({
      patient_id: selectedStudy.value.patient_id,
      clinical_text: clinicalText.value,
      primary_modality: selectedStudy.value.modality,
      modalities: [selectedStudy.value.modality],
      imaging_session_label: selectedStudy.value.study_id,
      image_paths: [currentImage.value],
      overlay_paths: overlayPaths.value,
      screenshot_paths: screenshots.value.map(s => s.path),
      models_used: selectedModels.value,
      segmentation_summary: segmentResults.value.map(r => `${r.model_id}: ${r.notes}`).join('; '),
    })
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
        <p class="sub">2D 串行分割 → 截图 → Qwen3-VL → DeepSeek 多智能体 → 结构化报告</p>
      </div>
      <div v-if="memoryPeak" class="mem-badge">峰值内存 ~{{ memoryPeak.toFixed(0) }} MB</div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <div class="grid-main">
      <aside class="card panel">
        <h3>影像检查</h3>
        <ul class="study-list">
          <li
            v-for="s in studies"
            :key="s.study_id"
            :class="{ active: selectedStudy?.study_id === s.study_id }"
            @click="selectStudy(s)"
          >
            <span class="mod">{{ s.modality }}</span>
            {{ s.title }}
            <small>{{ s.slice_count }} 张</small>
          </li>
        </ul>

        <h3>分割模型（医生选择，串行）</h3>
        <label v-for="m in models" :key="m.model_id" class="model-check">
          <input type="checkbox" :checked="selectedModels.includes(m.model_id)" @change="toggleModel(m.model_id)" />
          <span>
            <strong>{{ m.name }}</strong>
            <small>{{ m.description }}</small>
            <em v-if="!m.weights_present" class="warn">权重未下载</em>
          </span>
        </label>

        <label class="label">VISTA3D 器官</label>
        <select v-model="organ" class="select">
          <option value="brain">脑</option>
          <option value="liver">肝</option>
          <option value="lung">肺</option>
        </select>

        <button class="btn-primary full" :disabled="loading || !selectedModels.length" @click="runSegmentation">
          运行 2D 分割
        </button>
      </aside>

      <section class="viewer card">
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

        <div v-if="segmentResults.length" class="overlays">
          <h4>分割 Overlay</h4>
          <div class="overlay-row">
            <figure v-for="r in segmentResults" :key="r.model_id">
              <img :src="imagingFileUrl(r.overlay_path)" :alt="r.model_id" />
              <figcaption>{{ r.model_id }} · {{ r.duration_ms.toFixed(0) }}ms · +{{ r.memory_mb.toFixed(1) }}MB</figcaption>
            </figure>
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
      <label class="label">病历 / 临床描述</label>
      <textarea v-model="clinicalText" class="textarea" rows="3" />

      <button class="btn-primary" :disabled="loading" @click="generateReport">
        生成用药安全报告（Qwen VLM + DeepSeek）
      </button>

      <template v-if="report">
        <hr class="divider" />
        <p class="meta">
          报告 ID: {{ report.report_id }} · 会话: {{ report.imaging_session_id }} ·
          {{ report.created_at }}
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
.grid-main { display: grid; grid-template-columns: 280px 1fr; gap: 1rem; margin-bottom: 1rem; }
@media (max-width: 960px) { .grid-main { grid-template-columns: 1fr; } }
.panel h3 { font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; margin: 0.75rem 0 0.5rem; }
.study-list { list-style: none; max-height: 200px; overflow-y: auto; margin-bottom: 0.5rem; }
.study-list li { padding: 0.45rem 0.5rem; border-radius: var(--radius); cursor: pointer; font-size: 0.85rem; border: 1px solid transparent; }
.study-list li:hover { background: var(--surface-2); }
.study-list li.active { background: var(--primary-light); border-color: var(--primary); }
.mod { display: inline-block; background: var(--primary); color: #fff; font-size: 0.65rem; padding: 0.1rem 0.35rem; border-radius: 3px; margin-right: 0.35rem; }
.study-list small { display: block; color: var(--text-muted); font-size: 0.72rem; }
.model-check { display: flex; gap: 0.5rem; align-items: flex-start; margin-bottom: 0.5rem; font-size: 0.85rem; cursor: pointer; }
.model-check small { display: block; color: var(--text-muted); font-size: 0.75rem; }
.model-check .warn { color: var(--warning); font-style: normal; font-size: 0.72rem; }
.full { width: 100%; margin-top: 0.75rem; }
.viewer-toolbar { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.75rem; flex-wrap: wrap; }
.viewer-canvas { background: #000; border-radius: var(--radius); overflow: hidden; min-height: 280px; display: flex; align-items: center; justify-content: center; }
.viewer-canvas img { max-width: 100%; max-height: 420px; object-fit: contain; }
.overlays, .shots { margin-top: 1rem; }
.overlays h4, .shots h4 { font-size: 0.85rem; margin-bottom: 0.5rem; }
.overlay-row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
.overlay-row figure { max-width: 200px; }
.overlay-row img { width: 100%; border: 1px solid var(--border); border-radius: var(--radius); }
.overlay-row figcaption { font-size: 0.72rem; color: var(--text-muted); }
.report-panel { margin-top: 0.5rem; }
.divider { border: none; border-top: 1px solid var(--border); margin: 1rem 0; }
.meta { font-size: 0.78rem; color: var(--text-muted); margin-bottom: 0.75rem; }
.sup-item { background: var(--surface-2); padding: 0.65rem; border-radius: var(--radius); margin-bottom: 0.5rem; font-size: 0.88rem; }
.qa-row { display: flex; gap: 0.5rem; margin-top: 1rem; }
.qa-ans { margin-top: 0.5rem; padding: 0.65rem; background: var(--primary-light); border-radius: var(--radius); font-size: 0.9rem; }
</style>
