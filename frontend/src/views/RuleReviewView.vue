<script setup lang="ts">
import { ref } from 'vue'
import { medsafeApi } from '@/api/medsafe'
import { DEMO_CASES } from '@/data/demoCases'
import type { ReviewOutput } from '@/types'
import RuleEvidencePanel from '@/components/consult/RuleEvidencePanel.vue'
import RiskBadge from '@/components/common/RiskBadge.vue'

const loading = ref(false)
const error = ref('')
const review = ref<ReviewOutput | null>(null)

const selected = ref(DEMO_CASES[0]!.id)

async function runReview() {
  const demo = DEMO_CASES.find((d) => d.id === selected.value)
  if (!demo?.patient_context) return
  loading.value = true
  error.value = ''
  try {
    const res = await medsafeApi.ruleReview(demo.patient_context, demo.candidate_drugs)
    review.value = res.review_output
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div>
    <h1>规则审查 (Stage 3)</h1>
    <p class="sub">纯规则引擎，无 LLM 多智能体 — 确定性安全底线</p>

    <div class="card controls">
      <label class="label">Demo Case</label>
      <select v-model="selected" class="select">
        <option v-for="d in DEMO_CASES.filter(c => c.patient_context)" :key="d.id" :value="d.id">{{ d.title }}</option>
      </select>
      <button class="btn-primary" type="button" :disabled="loading" @click="runReview">运行规则审查</button>
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <div v-if="review" class="results">
      <div class="card">
        <RiskBadge :level="review.risk_level" :block="review.block_decision" />
        <p class="rec">{{ review.final_recommendation }}</p>
        <ul v-if="review.risk_reasons.length">
          <li v-for="(r, i) in review.risk_reasons" :key="i">{{ r }}</li>
        </ul>
        <p v-if="review.need_clarification" class="clarify-hint">
          需澄清：{{ review.clarification_targets.join(', ') }}
        </p>
      </div>
      <RuleEvidencePanel :evidence="review.evidence" />
    </div>
  </div>
</template>

<style scoped>
h1 { margin-bottom: 0.25rem; }
.sub { color: var(--text-muted); margin-bottom: 1.5rem; }
.controls { display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-end; margin-bottom: 1rem; }
.controls .select { max-width: 320px; }
.err { color: var(--danger); }
.results { display: flex; flex-direction: column; gap: 1rem; }
.rec { margin: 1rem 0; font-size: 1.05rem; }
.clarify-hint { color: var(--warning); font-size: 0.9rem; margin-top: 0.75rem; }
</style>
