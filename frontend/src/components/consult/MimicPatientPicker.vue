<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { medsafeApi } from '@/api/medsafe'
import type { MimicPatientSummary, PatientContext } from '@/types'

const emit = defineEmits<{
  loaded: [ctx: PatientContext]
}>()

const router = useRouter()

const loading = ref(false)
const error = ref('')
const statsReady = ref(false)
const contextCount = ref(0)
const datasetTier = ref('unknown')

const query = ref('')
const icuOnly = ref(false)
const imagingOnly = ref(false)
const items = ref<MimicPatientSummary[]>([])
const total = ref(0)
const offset = ref(0)
const limit = 20
const selectedKey = ref('')

const page = computed(() => Math.floor(offset.value / limit) + 1)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / limit)))

async function loadStats() {
  try {
    const stats = await medsafeApi.mimicStats()
    statsReady.value = stats.processed_available
    contextCount.value = stats.context_count
    datasetTier.value = stats.dataset_tier
  } catch {
    statsReady.value = false
  }
}

async function search(resetOffset = true) {
  if (!statsReady.value) return
  if (resetOffset) offset.value = 0
  loading.value = true
  error.value = ''
  try {
    const res = await medsafeApi.listMimicPatients({
      offset: offset.value,
      limit,
      q: query.value.trim() || undefined,
      icu_only: icuOnly.value || undefined,
      has_imaging: imagingOnly.value ? true : undefined,
      min_medications: 1,
    })
    items.value = res.items
    total.value = res.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadAdmission(subjectId: number, hadmId: number) {
  loading.value = true
  error.value = ''
  selectedKey.value = `${subjectId}/${hadmId}`
  try {
    const ctx = await medsafeApi.getMimicPatient(subjectId, hadmId)
    emit('loaded', ctx)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function goImaging(subjectId: number) {
  router.push({ path: '/imaging', query: { patient: `p${String(subjectId).padStart(8, '0')}` } })
}

function prevPage() {
  if (offset.value <= 0) return
  offset.value = Math.max(0, offset.value - limit)
  search(false)
}

function nextPage() {
  if (offset.value + limit >= total.value) return
  offset.value += limit
  search(false)
}

let debounceTimer: ReturnType<typeof setTimeout> | undefined
watch([query, icuOnly, imagingOnly], () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => search(true), 350)
})

onMounted(async () => {
  await loadStats()
  if (statsReady.value) await search(true)
})
</script>

<template>
  <div class="mimic-picker card">
    <div class="head">
      <div>
        <strong>MIMIC-III 真实病例</strong>
        <span v-if="statsReady" class="badge">{{ contextCount.toLocaleString() }} 条 · {{ datasetTier }}</span>
      </div>
      <button type="button" class="btn-secondary" :disabled="loading" @click="search(true)">刷新</button>
    </div>

    <p v-if="!statsReady" class="hint">
      尚未构建 MIMIC 索引。请在项目根目录运行：
      <code>python -m src.cli build-mimic --max-samples 0</code>
    </p>

    <template v-else>
      <div class="filters">
        <input v-model="query" class="input" type="search" placeholder="搜索诊断、用药、主诉…" />
        <label class="chk"><input v-model="icuOnly" type="checkbox" /> ICU</label>
        <label class="chk"><input v-model="imagingOnly" type="checkbox" /> 有胸片</label>
      </div>

      <p v-if="error" class="err">{{ error }}</p>
      <p v-if="loading && !items.length" class="muted">加载中…</p>

      <ul v-if="items.length" class="list">
        <li
          v-for="item in items"
          :key="`${item.subject_id}-${item.hadm_id}`"
          :class="{ active: selectedKey === `${item.subject_id}/${item.hadm_id}` }"
        >
          <button type="button" class="row-btn" @click="loadAdmission(item.subject_id, item.hadm_id)">
            <span class="id">{{ item.subject_id }} / {{ item.hadm_id }}</span>
            <span class="meta">
              {{ item.gender }} · {{ item.age ?? '?' }} 岁 · {{ item.medication_count }} 药
              <span v-if="item.icu_stay" class="tag icu">ICU</span>
              <span v-if="item.has_imaging" class="tag img">CXR</span>
            </span>
            <span v-if="item.primary_diagnosis" class="dx">{{ item.primary_diagnosis }}</span>
            <span v-if="item.egfr != null" class="lab">eGFR {{ item.egfr }}</span>
          </button>
          <button
            v-if="item.has_imaging"
            type="button"
            class="btn-ghost img-btn"
            title="打开影像"
            @click.stop="goImaging(item.subject_id)"
          >
            影像
          </button>
        </li>
      </ul>
      <p v-else-if="!loading" class="muted">无匹配住院记录</p>

      <div v-if="total > limit" class="pager">
        <button type="button" class="btn-secondary" :disabled="offset <= 0 || loading" @click="prevPage">上一页</button>
        <span>{{ page }} / {{ totalPages }}（共 {{ total }}）</span>
        <button type="button" class="btn-secondary" :disabled="offset + limit >= total || loading" @click="nextPage">下一页</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.mimic-picker { margin-bottom: 1rem; padding: 1rem; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }
.badge { font-size: 0.72rem; background: var(--surface-2); padding: 0.15rem 0.45rem; border-radius: 999px; margin-left: 0.35rem; }
.hint, .muted { font-size: 0.85rem; color: var(--text-muted); }
.hint code { font-size: 0.78rem; }
.filters { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin-bottom: 0.75rem; }
.filters .input { flex: 1; min-width: 180px; }
.chk { font-size: 0.82rem; display: flex; align-items: center; gap: 0.25rem; }
.list { list-style: none; padding: 0; margin: 0; max-height: 280px; overflow-y: auto; }
.list li { display: flex; align-items: stretch; border-bottom: 1px solid var(--border); }
.list li.active { background: var(--primary-light); }
.row-btn { flex: 1; text-align: left; padding: 0.5rem 0.35rem; background: none; border: none; cursor: pointer; }
.id { font-family: var(--mono); font-size: 0.78rem; color: var(--text-muted); display: block; }
.meta { font-size: 0.82rem; display: block; }
.dx { font-size: 0.8rem; color: var(--text-muted); display: block; margin-top: 0.15rem; }
.lab { font-size: 0.75rem; color: var(--primary-dark); }
.tag { font-size: 0.68rem; padding: 0 0.3rem; border-radius: 3px; margin-left: 0.25rem; }
.tag.icu { background: #fce4ec; color: #880e4f; }
.tag.img { background: #e3f2fd; color: #0d47a1; }
.img-btn { align-self: center; margin-right: 0.25rem; }
.pager { display: flex; justify-content: space-between; align-items: center; margin-top: 0.75rem; font-size: 0.82rem; }
.err { color: var(--danger); font-size: 0.85rem; }
</style>
