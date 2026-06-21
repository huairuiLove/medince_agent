<script setup lang="ts">
import type { RuleEvidence } from '@/types'
import RiskBadge from '@/components/common/RiskBadge.vue'

defineProps<{ evidence: RuleEvidence[] }>()
</script>

<template>
  <section class="card evidence-panel">
    <h3>规则证据 (Layer 1)</h3>
    <p v-if="!evidence.length" class="empty">未命中硬规则</p>
    <div v-for="ev in evidence" :key="ev.rule_id" class="ev-item">
      <div class="ev-head">
        <code>{{ ev.rule_id }}</code>
        <RiskBadge :level="ev.risk_level" />
        <span class="cat">{{ ev.category }}</span>
      </div>
      <p>{{ ev.summary }}</p>
      <p v-if="ev.mechanism" class="muted">{{ ev.mechanism }}</p>
      <p v-if="ev.recommendation" class="rec">{{ ev.recommendation }}</p>
    </div>
  </section>
</template>

<style scoped>
h3 { margin-bottom: 1rem; font-size: 1.05rem; }
.empty { color: var(--text-muted); font-size: 0.9rem; }
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
