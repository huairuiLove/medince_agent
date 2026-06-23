<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { medsafeApi } from '@/api/medsafe'
import type { VolumeAxis, VolumeMeta } from '@/types'

const props = defineProps<{
  volumePath: string
  overlayPath?: string | null
  axis?: VolumeAxis
  sliceIndex?: number
}>()

const emit = defineEmits<{
  'update:axis': [VolumeAxis]
  'update:sliceIndex': [number]
}>()

const meta = ref<VolumeMeta | null>(null)
const metaLoading = ref(false)
const sliceLoading = ref(false)
const error = ref('')
const sliceSrc = ref('')
const localAxis = ref<VolumeAxis>(props.axis ?? 'axial')
const localIndex = ref(props.sliceIndex ?? 0)

const sliceCache = new Map<string, string>()
let loadTimer: ReturnType<typeof setTimeout> | null = null
let loadGeneration = 0

const maxIndex = computed(() => {
  if (!meta.value) return 0
  return Math.max(0, meta.value.slice_counts[localAxis.value] - 1)
})

const sliceParams = computed(() => ({
  volume_path: props.volumePath,
  axis: localAxis.value,
  index: localIndex.value,
  overlay_path: props.overlayPath ?? undefined,
}))

const axes: { id: VolumeAxis; label: string }[] = [
  { id: 'axial', label: '轴位 Axial' },
  { id: 'coronal', label: '冠状 Coronal' },
  { id: 'sagittal', label: '矢状 Sagittal' },
]

function sliceCacheKey(params: {
  volume_path: string
  axis: string
  index: number
  overlay_path?: string
}) {
  return `${params.volume_path}|${params.axis}|${params.index}|${params.overlay_path ?? ''}`
}

function revokeAllCachedUrls() {
  for (const url of sliceCache.values()) {
    URL.revokeObjectURL(url)
  }
  sliceCache.clear()
}

watch(() => props.axis, v => {
  if (v && v !== localAxis.value) localAxis.value = v
})
watch(() => props.sliceIndex, v => {
  if (v !== undefined && v !== localIndex.value) localIndex.value = v
})

watch(localAxis, v => {
  const clamped = Math.min(localIndex.value, maxIndex.value)
  if (clamped !== localIndex.value) localIndex.value = clamped
  emit('update:axis', v)
  if (clamped !== props.sliceIndex) emit('update:sliceIndex', clamped)
})

watch(localIndex, v => {
  if (v !== props.sliceIndex) emit('update:sliceIndex', v)
})

async function loadSliceImage() {
  if (!props.volumePath || !meta.value) return

  const params = sliceParams.value
  const key = sliceCacheKey(params)
  const cached = sliceCache.get(key)
  if (cached) {
    sliceSrc.value = cached
    return
  }

  const generation = ++loadGeneration
  sliceLoading.value = true
  try {
    const objectUrl = await medsafeApi.volumeSliceObjectUrl(params)
    if (generation !== loadGeneration) {
      URL.revokeObjectURL(objectUrl)
      return
    }
    sliceCache.set(key, objectUrl)
    sliceSrc.value = objectUrl
    error.value = ''
  } catch (e) {
    if (generation === loadGeneration) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  } finally {
    if (generation === loadGeneration) sliceLoading.value = false
  }
}

function scheduleSliceLoad() {
  if (loadTimer) clearTimeout(loadTimer)
  loadTimer = setTimeout(() => {
    loadTimer = null
    void loadSliceImage()
  }, 100)
}

async function loadMeta() {
  if (!props.volumePath) return
  metaLoading.value = true
  error.value = ''
  revokeAllCachedUrls()
  sliceSrc.value = ''
  try {
    meta.value = await medsafeApi.getVolumeMeta(props.volumePath)
    if (localIndex.value > maxIndex.value) {
      localIndex.value = Math.floor(maxIndex.value / 2)
      emit('update:sliceIndex', localIndex.value)
    }
    await loadSliceImage()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    metaLoading.value = false
  }
}

watch(sliceParams, scheduleSliceLoad, { deep: true })
watch(() => props.volumePath, loadMeta)

onMounted(loadMeta)
onBeforeUnmount(() => {
  if (loadTimer) clearTimeout(loadTimer)
  revokeAllCachedUrls()
})
</script>

<template>
  <div class="mpr-viewer">
    <div class="mpr-toolbar">
      <div class="axis-tabs">
        <button
          v-for="a in axes"
          :key="a.id"
          type="button"
          class="axis-btn"
          :class="{ active: localAxis === a.id }"
          @click="localAxis = a.id"
        >
          {{ a.label }}
        </button>
      </div>
      <div v-if="meta" class="slice-control">
        <input
          v-model.number="localIndex"
          type="range"
          min="0"
          :max="maxIndex"
          class="slice-slider"
        />
        <span class="slice-label">{{ localIndex + 1 }} / {{ maxIndex + 1 }}</span>
        <span class="dim-label">{{ meta.shape.join(' × ') }}</span>
      </div>
    </div>

    <p v-if="error" class="mpr-err">{{ error }}</p>
    <p v-else-if="metaLoading" class="mpr-loading">加载 3D 体数据…</p>

    <div v-else class="mpr-canvas">
      <img
        v-if="sliceSrc"
        :src="sliceSrc"
        alt="MPR slice"
        class="mpr-img"
      />
      <div v-if="sliceLoading" class="mpr-slice-loading">切片加载中…</div>
    </div>
  </div>
</template>

<style scoped>
.mpr-viewer { display: flex; flex-direction: column; gap: 0.65rem; }
.mpr-toolbar { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center; justify-content: space-between; }
.axis-tabs { display: flex; gap: 0.35rem; }
.axis-btn {
  padding: 0.35rem 0.65rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  font-size: 0.78rem;
  cursor: pointer;
  color: var(--text);
}
.axis-btn.active { background: var(--primary); color: #fff; border-color: var(--primary); }
.slice-control { display: flex; align-items: center; gap: 0.5rem; flex: 1; min-width: 200px; }
.slice-slider { flex: 1; accent-color: var(--primary); }
.slice-label, .dim-label { font-size: 0.78rem; color: var(--text-muted); white-space: nowrap; }
.mpr-canvas {
  position: relative;
  background: #000;
  border-radius: var(--radius);
  min-height: 480px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.mpr-img { max-width: 100%; max-height: 480px; object-fit: contain; }
.mpr-slice-loading {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
  border-radius: var(--radius);
  pointer-events: none;
}
.mpr-err { color: var(--danger); font-size: 0.85rem; }
.mpr-loading { color: var(--text-muted); font-size: 0.85rem; }
</style>
