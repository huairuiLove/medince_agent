<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ClarifyOutput } from '@/types'

const props = defineProps<{
  clarify: ClarifyOutput | null | undefined
  interactive?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  submit: [payload: { answers: Record<string, string>; unable: boolean }]
}>()

const answers = ref<Record<string, string>>({})

const canInteract = computed(
  () =>
    Boolean(props.interactive)
    && props.clarify?.status === 'need_user_input'
    && (props.clarify?.questions?.length ?? 0) > 0,
)

watch(
  () => props.clarify?.questions,
  (questions) => {
    if (!questions?.length) {
      answers.value = {}
      return
    }
    const next: Record<string, string> = {}
    for (const q of questions) {
      next[q.field] = answers.value[q.field] ?? ''
    }
    answers.value = next
  },
  { immediate: true },
)

const statusLabel = computed(() => {
  const status = props.clarify?.status
  if (!status || status === 'conservative_fallback') return ''
  if (status === 'need_user_input') return '待补充信息'
  if (status === 'complete') return '已完成'
  return status
})

function submitAnswers(unable = false) {
  emit('submit', { answers: { ...answers.value }, unable })
}
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
        <input
          v-if="canInteract"
          v-model="answers[q.field]"
          class="input answer-input"
          type="text"
          :placeholder="`填写：${q.field}`"
          :disabled="loading"
        />
      </div>
    </div>

    <div v-if="canInteract" class="clarify-actions">
      <button class="btn-primary" type="button" :disabled="loading" @click="submitAnswers(false)">
        {{ loading ? '提交中…' : '提交补充信息' }}
      </button>
      <button class="btn-secondary" type="button" :disabled="loading" @click="submitAnswers(true)">
        无法回答，保守建议
      </button>
    </div>

    <div v-if="clarify.conservative_advice" class="conservative">
      <h4>保守建议</h4>
      <p>{{ clarify.conservative_advice.summary }}</p>
      <ul v-if="clarify.conservative_advice.actions?.length">
        <li v-for="(a, i) in clarify.conservative_advice.actions" :key="i">{{ a }}</li>
      </ul>
      <p v-if="clarify.conservative_advice.disclaimer" class="disclaimer">
        {{ clarify.conservative_advice.disclaimer }}
      </p>
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
.q-reason { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.5rem; }
.answer-input { width: 100%; margin-top: 0.35rem; }
.clarify-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.75rem 0 1rem; }
.conservative { margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border); font-size: 0.88rem; }
.conservative h4 { font-size: 0.82rem; color: var(--primary); margin-bottom: 0.35rem; }
.conservative ul { margin: 0.35rem 0 0.35rem 1.1rem; }
.disclaimer { font-size: 0.82rem; color: var(--text-muted); margin-top: 0.35rem; }
.final-msg { margin-top: 0.75rem; font-weight: 500; }
</style>
