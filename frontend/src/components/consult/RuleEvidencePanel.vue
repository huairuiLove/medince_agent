<script setup lang="ts">
import { computed } from 'vue'
import type { KnowledgeBaseStats, RuleEvidence } from '@/types'
import RiskBadge from '@/components/common/RiskBadge.vue'
import { sanitizeReviewText } from '@/utils/reviewText'

const props = defineProps<{
  evidence: RuleEvidence[]
  clarificationTargets?: string[]
  kbStats?: KnowledgeBaseStats | null
}>()

const FIELD_LABELS: Record<string, string> = {
  allergies: '过敏史',
  current_medications: '当前用药',
  pregnancy_status: '妊娠状态',
  age: '年龄',
}

const kbHint = computed(() => {
  const s = props.kbStats
  if (!s?.total_rules) return ''
  return `知识库 ${s.version || s.path || ''}：共 ${s.total_rules} 条确定性规则（DDI ${s.interaction_rules} · 重复成分 ${s.duplicate_ingredient_rules} · 人群 ${s.population_rules} · 过敏 ${s.allergy_rules}）`
})
</script>

<template>
  <section class="evidence-panel">
    <h4>规则证据</h4>
    <p v-if="kbHint" class="kb-hint">{{ kbHint }}</p>
    <p v-if="!evidence.length && clarificationTargets?.length" class="clarify-only">
      未命中确定性硬规则，但信息不足需先澄清：
      {{ clarificationTargets.map(f => FIELD_LABELS[f] ?? f).join('、') }}
    </p>
    <div v-else-if="!evidence.length" class="pass-box">
      <p class="pass-title">审查通过（未发现已知高危规则）</p>
      <p class="pass-detail">
        这<strong>不是</strong>系统失败。规则库只覆盖常见高危组合；任意两种药联用大多无预置条目。
        建议使用科室病例模板（如华法林+阿司匹林）验证，或启用 DDI 模型补充未覆盖组合。
      </p>
    </div>
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
.kb-hint { font-size: 0.82rem; color: var(--text-muted); margin: -0.35rem 0 0.75rem; }
.empty, .clarify-only { color: var(--text-muted); font-size: 0.9rem; }
.clarify-only { color: var(--warning); }
.pass-box {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.75rem 0.9rem;
  font-size: 0.88rem;
}
.pass-title { color: var(--success, #15803d); font-weight: 600; margin-bottom: 0.35rem; }
.pass-detail { color: var(--text-muted); line-height: 1.55; }
.pass-detail strong { color: var(--text); font-weight: 600; }
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
