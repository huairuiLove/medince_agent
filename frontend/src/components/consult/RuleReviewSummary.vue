<script setup lang="ts">
import type { ReviewOutput } from '@/types'
import RiskBadge from '@/components/common/RiskBadge.vue'
import RuleEvidencePanel from '@/components/consult/RuleEvidencePanel.vue'

defineProps<{ ruleOutput: ReviewOutput }>()
</script>

<template>
  <section class="card rule-review-summary">
    <header class="head">
      <h3>规则审查结论（Layer 0）</h3>
      <RiskBadge :level="ruleOutput.risk_level" :block="ruleOutput.block_decision" />
    </header>

    <p class="final">{{ ruleOutput.final_recommendation }}</p>

    <ul v-if="ruleOutput.risk_reasons.length" class="reasons">
      <li v-for="(r, i) in ruleOutput.risk_reasons" :key="i">{{ r }}</li>
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
    />
  </section>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.head h3 { font-size: 1.05rem; margin: 0; }
.final { font-size: 1.02rem; line-height: 1.6; margin-bottom: 0.75rem; }
.reasons { margin: 0 0 0.75rem 1.1rem; font-size: 0.92rem; }
.alts { font-size: 0.9rem; color: var(--primary-dark); margin-bottom: 0.5rem; }
.clarify { font-size: 0.9rem; color: var(--warning); margin-bottom: 0.75rem; }
</style>
