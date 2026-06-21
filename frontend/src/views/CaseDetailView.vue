<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { medsafeApi } from '@/api/medsafe'
import type { CaseLog } from '@/types'
import AgentOpinionCard from '@/components/consult/AgentOpinionCard.vue'
import RuleEvidencePanel from '@/components/consult/RuleEvidencePanel.vue'
import ClarifyPanel from '@/components/consult/ClarifyPanel.vue'
import RiskBadge from '@/components/common/RiskBadge.vue'

const route = useRoute()
const caseLog = ref<CaseLog | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    caseLog.value = await medsafeApi.getCase(route.params.id as string)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})

const events = computed(() => caseLog.value?.events ?? [])
</script>

<template>
  <div v-if="caseLog" class="detail">
    <header>
      <h1>Case {{ caseLog.case_id }}</h1>
      <span class="status">{{ caseLog.status }}</span>
    </header>
    <p class="meta">创建 {{ caseLog.created_at }} · 更新 {{ caseLog.updated_at }}</p>

    <div class="card timeline">
      <h3>事件链</h3>
      <div class="events">
        <div v-for="(e, i) in events" :key="i" class="ev">
          <span class="stage">{{ e.stage }}</span>
          <span class="time">{{ e.timestamp }}</span>
        </div>
      </div>
    </div>

    <div v-if="caseLog.final_recommendation" class="card">
      <h3>最终建议</h3>
      <p>{{ caseLog.final_recommendation }}</p>
    </div>

    <RuleEvidencePanel v-if="caseLog.review_output" :evidence="caseLog.review_output.evidence" />

    <div v-if="caseLog.arbitration" class="card">
      <h3>仲裁结果</h3>
      <RiskBadge :level="caseLog.arbitration.consensus_risk_level" :block="caseLog.arbitration.consensus_block_decision" />
      <p>{{ caseLog.arbitration.final_recommendation }}</p>
    </div>

    <div v-if="caseLog.agent_opinions?.length" class="agents">
      <h3>专家意见</h3>
      <AgentOpinionCard v-for="o in caseLog.agent_opinions" :key="o.agent_id" :opinion="o" />
    </div>

    <ClarifyPanel :clarify="caseLog.clarify_output" />
  </div>
  <p v-else-if="error" class="err">{{ error }}</p>
  <p v-else class="loading">加载中…</p>
</template>

<style scoped>
header { display: flex; align-items: center; gap: 1rem; margin-bottom: 0.25rem; }
.status { background: var(--surface-2); padding: 0.25rem 0.65rem; border-radius: 6px; font-size: 0.82rem; }
.meta { color: var(--text-muted); font-size: 0.88rem; margin-bottom: 1.5rem; }
.timeline { margin-bottom: 1rem; }
.events { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.ev {
  background: var(--surface-2);
  padding: 0.4rem 0.75rem;
  border-radius: 8px;
  font-size: 0.85rem;
}
.stage { font-weight: 700; margin-right: 0.5rem; text-transform: uppercase; font-size: 0.75rem; }
.time { color: var(--text-muted); font-size: 0.78rem; }
.agents { display: flex; flex-direction: column; gap: 0.75rem; margin-top: 1rem; }
.err { color: var(--danger); }
</style>
