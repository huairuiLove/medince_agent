<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { medsafeApi } from '@/api/medsafe'

const props = withDefaults(
  defineProps<{
    path: string
    alt?: string
    imgClass?: string
  }>(),
  { alt: '', imgClass: '' },
)

const src = ref('')
const failed = ref(false)
let objectUrl: string | null = null

function revoke() {
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl)
    objectUrl = null
  }
}

async function load() {
  revoke()
  failed.value = false
  src.value = ''
  if (!props.path) return
  try {
    objectUrl = await medsafeApi.imagingFileObjectUrl(props.path)
    src.value = objectUrl
  } catch {
    failed.value = true
  }
}

watch(() => props.path, load, { immediate: true })
onBeforeUnmount(revoke)
</script>

<template>
  <img v-if="src && !failed" :src="src" :alt="alt" :class="imgClass" />
  <span v-else-if="failed" class="img-fail">影像加载失败</span>
</template>

<style scoped>
.img-fail {
  font-size: 0.72rem;
  color: var(--danger, #c0392b);
}
</style>
