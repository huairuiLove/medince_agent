<script setup lang="ts">
import type { RuleEvidence } from '@/types'
import RiskBadge from '@/components/common/RiskBadge.vue'
import { sanitizeReviewText } from '@/utils/reviewText'

defineProps<{
  evidence: RuleEvidence[]
  clarificationTargets?: string[]
}>()

const FIELD_LABELS: Record<string, string> = {
  allergies: '过敏史',
  current_medications: '当前用药',
  pregnancy_status: '妊娠状态',
  age: '年龄',
}
</script>

<template>
  <section class="evidence-panel">
    <h4>规则证据</h4>
    <p v-if="!evidence.length && clarificationTargets?.length" class="clarify-only">
      未命中确定性硬规则，但信息不足需先澄清：
      {{ clarificationTargets.map(f => FIELD_LABELS[f] ?? f).join('、') }}
    </p>
    <p v-else-if="!evidence.length" class="empty">规则库未命中（当前仅覆盖 12 条 DDI/过敏/妊娠/重复用药规则）</p>
    <div v-for="ev in evidence" :key="ev.rule_id" class="ev-item">
      <div class="ev-head">
        <code>{{ ev.rule_id }}</code>
        <RiskBadge :level="ev.risk_level" />
        <span class="cat">{{ ev.category }}</span>
      </div>
      <p>{{ ev.summary }}</p>
      <p v-if="ev.mechanism" class="muted">{{ ev.mechanism }}</p>
      <p v-if="ev.recommendation" class="rec">{{ sanitizeReviewText(ev.recommendation) }}</p>
    </div>
  </section>
</template>

<style scoped>
h4 { margin-bottom: 0.75rem; font-size: 0.95rem; color: var(--text-muted); }
.empty, .clarify-only { color: var(--text-muted); font-size: 0.9rem; }
.clarify-only { color: var(--warning); }
.ev-item {
  border-left: 3px solid var(--primary);
  padding: 0.75rem 0 0.75rem 1rem;
  margin-bottom: 0.75rem;
  background: var(--surface-2);
  border-radius: 0 8px 8px 0;
}
.ev-head { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.35rem; }
code { font-family: var(--mono); font-size: 0.78rem; background: #fff; padding: 0.15rem 0.4rem; border-radius: 4px; }
.cat { font-size: 0.75rem; color: var(--text-muted); }
.muted { font-size: 0.85rem; color: var(--text-muted); }
.rec { font-size: 0.88rem; color: var(--primary-dark); margin-top: 0.25rem; }
</style>
