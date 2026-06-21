<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { medsafeApi, volumeSliceUrl } from '@/api/medsafe'
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
const loading = ref(false)
const error = ref('')
const localAxis = ref<VolumeAxis>(props.axis ?? 'axial')
const localIndex = ref(props.sliceIndex ?? 0)

const maxIndex = computed(() => {
  if (!meta.value) return 0
  return Math.max(0, meta.value.slice_counts[localAxis.value] - 1)
})

const sliceUrl = computed(() => {
  if (!props.volumePath) return ''
  return volumeSliceUrl({
    volume_path: props.volumePath,
    axis: localAxis.value,
    index: localIndex.value,
    overlay_path: props.overlayPath ?? undefined,
  })
})

const axes: { id: VolumeAxis; label: string }[] = [
  { id: 'axial', label: '轴位 Axial' },
  { id: 'coronal', label: '冠状 Coronal' },
  { id: 'sagittal', label: '矢状 Sagittal' },
]

watch(() => props.axis, v => { if (v) localAxis.value = v })
watch(() => props.sliceIndex, v => { if (v !== undefined) localIndex.value = v })

watch(localAxis, v => {
  if (localIndex.value > maxIndex.value) localIndex.value = maxIndex.value
  emit('update:axis', v)
  emit('update:sliceIndex', localIndex.value)
})

watch(localIndex, v => emit('update:sliceIndex', v))

async function loadMeta() {
  if (!props.volumePath) return
  loading.value = true
  error.value = ''
  try {
    meta.value = await medsafeApi.getVolumeMeta(props.volumePath)
    if (localIndex.value > maxIndex.value) {
      localIndex.value = Math.floor(maxIndex.value / 2)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(loadMeta)
watch(() => props.volumePath, loadMeta)
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
    <p v-else-if="loading" class="mpr-loading">加载 3D 体数据…</p>

    <div v-else class="mpr-canvas">
      <img
        v-if="sliceUrl"
        :key="sliceUrl"
        :src="sliceUrl"
        alt="MPR slice"
        class="mpr-img"
      />
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
  background: #000;
  border-radius: var(--radius);
  min-height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.mpr-img { max-width: 100%; max-height: 480px; object-fit: contain; }
.mpr-err { color: var(--danger); font-size: 0.85rem; }
.mpr-loading { color: var(--text-muted); font-size: 0.85rem; }
</style>
