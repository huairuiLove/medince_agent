<script setup lang="ts">
import type { AgentOpinion } from '@/types'
import RiskBadge from '@/components/common/RiskBadge.vue'

defineProps<{ opinion: AgentOpinion }>()

const iconMap: Record<string, string> = {
  clinical_pharmacist: '💊',
  internal_medicine: '🩺',
  allergy_specialist: '⚠️',
  pharmacy_inventory: '📦',
  specialist: '🔬',
}
</script>

<template>
  <article class="agent-card">
    <header>
      <span class="icon">{{ iconMap[opinion.agent_id] ?? '🤖' }}</span>
      <div>
        <h4>{{ opinion.agent_name }}</h4>
        <p class="role">{{ opinion.role }}</p>
      </div>
      <RiskBadge :level="opinion.risk_level" :block="opinion.block_decision" />
    </header>
    <p class="summary">{{ opinion.summary }}</p>
    <ul v-if="opinion.reasons.length" class="reasons">
      <li v-for="(r, i) in opinion.reasons" :key="i">{{ r }}</li>
    </ul>
    <div v-if="opinion.alternatives.length" class="alts">
      <strong>替代：</strong>{{ opinion.alternatives.join('；') }}
    </div>
    <footer>
      <span>置信度 {{ Math.round(opinion.confidence * 100) }}%</span>
      <span v-if="opinion.evidence_cited.length">证据 {{ opinion.evidence_cited.join(', ') }}</span>
    </footer>
  </article>
</template>

<style scoped>
.agent-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem;
  background: var(--surface);
}
header {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.icon { font-size: 1.5rem; }
h4 { font-size: 1rem; margin: 0; }
.role { font-size: 0.82rem; color: var(--text-muted); margin: 0; }
header .badge { margin-left: auto; flex-shrink: 0; }
.summary { font-size: 0.92rem; margin-bottom: 0.5rem; }
.reasons { padding-left: 1.1rem; font-size: 0.88rem; color: var(--text-muted); }
.alts { font-size: 0.85rem; margin-top: 0.5rem; color: var(--primary-dark); }
footer {
  display: flex;
  gap: 1rem;
  margin-top: 0.75rem;
  font-size: 0.78rem;
  color: var(--text-muted);
}
</style>
