<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { KnowledgeBaseStats, ReviewOutput } from '@/types'
import { medsafeApi } from '@/api/medsafe'
import RiskBadge from '@/components/common/RiskBadge.vue'
import RuleEvidencePanel from '@/components/consult/RuleEvidencePanel.vue'
import { sanitizeReviewText } from '@/utils/reviewText'

const props = defineProps<{ ruleOutput: ReviewOutput }>()
const kbStats = ref<KnowledgeBaseStats | null>(null)

onMounted(async () => {
  try {
    const health = await medsafeApi.health()
    kbStats.value = health.knowledge_base ?? null
  } catch {
    kbStats.value = null
  }
})

const finalText = computed(() => sanitizeReviewText(props.ruleOutput.final_recommendation))
</script>

<template>
  <section class="card rule-review-summary">
    <header class="head">
      <div>
        <h3>规则审查（Layer 0 · 前置审查）</h3>
        <p class="pipeline-hint">VLM 用药推荐 → 规则审查 → 多智能体用药审查</p>
      </div>
      <RiskBadge :level="ruleOutput.risk_level" :block="ruleOutput.block_decision" />
    </header>

    <p class="final">{{ finalText }}</p>

    <ul v-if="ruleOutput.risk_reasons.length" class="reasons">
      <li v-for="(r, i) in ruleOutput.risk_reasons" :key="i">{{ sanitizeReviewText(r) }}</li>
    </ul>

    <p v-if="ruleOutput.alternative_suggestions.length" class="alts">
      替代建议：{{ ruleOutput.alternative_suggestions.join('；') }}
    </p>

    <p v-if="ruleOutput.need_clarification" class="clarify">
      需澄清字段：{{ ruleOutput.clarification_targets.join('、') }}
    </p>

    <RuleEvidencePanel
      :evidence="ruleOutput.evidence"
      :clarification-targets="ruleOutput.need_clarification ? ruleOutput.clarification_targets : []"
      :kb-stats="kbStats"
    />
  </section>
</template>

<style scoped>
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.head h3 { font-size: 1.05rem; margin: 0; }
.pipeline-hint {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin: 0.25rem 0 0;
}
.final { font-size: 1.02rem; line-height: 1.6; margin-bottom: 0.75rem; }
.reasons { margin: 0 0 0.75rem 1.1rem; font-size: 0.92rem; }
.alts { font-size: 0.9rem; color: var(--primary-dark); margin-bottom: 0.5rem; }
.clarify { font-size: 0.9rem; color: var(--warning); margin-bottom: 0.75rem; }
</style>
