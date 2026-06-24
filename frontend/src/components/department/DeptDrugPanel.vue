<script setup lang="ts">
defineProps<{
  drugs: string[]
  title?: string
}>()

const emit = defineEmits<{ select: [drug: string] }>()

function pick(drug: string) {
  emit('select', drug)
}
</script>

<template>
  <aside class="drug-panel card">
    <h3>{{ title ?? '本科室常用药' }}</h3>
    <p v-if="!drugs.length" class="empty">暂无科室药典配置</p>
    <div v-else class="chips">
      <button
        v-for="d in drugs"
        :key="d"
        type="button"
        class="chip"
        @click="pick(d)"
      >
        {{ d }}
      </button>
    </div>
  </aside>
</template>

<style scoped>
.drug-panel h3 { margin: 0 0 0.75rem; font-size: 0.95rem; }
.chips { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.chip {
  border: 1px solid var(--border);
  background: var(--surface-2);
  border-radius: 999px;
  padding: 0.25rem 0.65rem;
  font-size: 0.78rem;
  cursor: pointer;
}
.chip:hover { border-color: var(--primary); color: var(--primary); }
.empty { color: var(--text-muted); font-size: 0.85rem; }
</style>
