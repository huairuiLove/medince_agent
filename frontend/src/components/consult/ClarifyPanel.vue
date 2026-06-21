<script setup lang="ts">
import type { ClarifyOutput } from '@/types'

defineProps<{ clarify: ClarifyOutput | null | undefined }>()
</script>

<template>
  <section v-if="clarify" class="card clarify-panel">
    <h3>信息协调员 · Clarify</h3>
    <span class="status">{{ clarify.status }}</span>

    <div v-if="clarify.questions.length" class="questions">
      <div v-for="q in clarify.questions" :key="q.field" class="q-item">
        <span class="priority" :data-p="q.priority">{{ q.priority }}</span>
        <p class="q-text">{{ q.question }}</p>
        <p class="q-reason">{{ q.reason }}</p>
      </div>
    </div>

    <div v-if="clarify.conservative_advice" class="fallback">
      <h4>保守降级</h4>
      <p>{{ clarify.conservative_advice.summary }}</p>
      <ul>
        <li v-for="(a, i) in clarify.conservative_advice.actions" :key="i">{{ a }}</li>
      </ul>
      <p class="disclaimer">{{ clarify.conservative_advice.disclaimer }}</p>
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
.fallback {
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  padding: 1rem;
  margin-top: 0.75rem;
}
.fallback h4 { color: var(--warning); margin-bottom: 0.5rem; }
.fallback ul { padding-left: 1.2rem; font-size: 0.9rem; }
.disclaimer { font-size: 0.78rem; color: var(--text-muted); margin-top: 0.5rem; }
.final-msg { margin-top: 0.75rem; font-weight: 500; }
</style>
