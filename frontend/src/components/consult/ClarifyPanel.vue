<script setup lang="ts">
import { computed } from 'vue'
import type { ClarifyOutput } from '@/types'

const props = defineProps<{ clarify: ClarifyOutput | null | undefined }>()

const statusLabel = computed(() => {
  const status = props.clarify?.status
  if (!status || status === 'conservative_fallback') return ''
  if (status === 'need_user_input') return '待补充信息'
  if (status === 'complete') return '已完成'
  return status
})
</script>

<template>
  <section v-if="clarify" class="card clarify-panel">
    <h3>信息协调员 · Clarify</h3>
    <span v-if="statusLabel" class="status">{{ statusLabel }}</span>

    <div v-if="clarify.questions.length" class="questions">
      <div v-for="q in clarify.questions" :key="q.field" class="q-item">
        <span class="priority" :data-p="q.priority">{{ q.priority }}</span>
        <p class="q-text">{{ q.question }}</p>
        <p class="q-reason">{{ q.reason }}</p>
      </div>
    </div>

    <p v-if="clarify.final_message" class="final-msg">{{ clarify.final_message }}</p>
  </section>
</template>

<style scoped>
h3 { margin-bottom: 0.5rem; }
.status {
  display: inline-block;
  font-size: 0.78rem;
  font-weight: 700;
  background: var(--surface-2);
  padding: 0.2rem 0.6rem;
  border-radius: 6px;
  margin-bottom: 1rem;
}
.q-item {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.85rem;
  margin-bottom: 0.65rem;
}
.priority {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--warning);
}
.q-text { font-weight: 600; margin: 0.35rem 0; }
.q-reason { font-size: 0.85rem; color: var(--text-muted); }
.final-msg { margin-top: 0.75rem; font-weight: 500; }
</style>
