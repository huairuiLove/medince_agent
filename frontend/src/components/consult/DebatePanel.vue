<script setup lang="ts">
import type { DebateResult, SafetyPanelResult } from '@/types'

defineProps<{
  debate?: DebateResult | null
  safetyPanel?: SafetyPanelResult | null
}>()
</script>

<template>
  <section v-if="debate?.enabled" class="debate-panel card">
    <header class="debate-head">
      <h3>多轮辩论</h3>
      <div class="badges">
        <span class="badge">{{ debate.rounds.length }} 轮</span>
        <span class="badge">{{ debate.duration_ms.toFixed(0) }} ms</span>
        <span class="badge">min conf {{ debate.min_confidence.toFixed(2) }}</span>
        <span v-if="debate.final_consensus" class="badge ok">已共识</span>
        <span v-else-if="debate.flagged_for_human" class="badge warn">需人工复核</span>
      </div>
    </header>

    <div v-for="round in debate.rounds" :key="round.round_number" class="round-block">
      <h4>第 {{ round.round_number }} 轮</h4>
      <p class="meta">最低置信度 {{ round.min_confidence.toFixed(2) }}</p>
      <div v-if="round.critic_output" class="critic">
        <strong>Critic</strong>
        <p>{{ round.critic_output.overall_assessment }}</p>
        <ul v-if="round.critic_output.dissent_log.length">
          <li v-for="(d, i) in round.critic_output.dissent_log" :key="i">{{ d }}</li>
        </ul>
        <p class="consensus">
          共识：{{ round.critic_output.consensus_reached ? '是' : '否' }}
        </p>
      </div>
    </div>

    <div v-if="debate.moderator_synthesis" class="moderator">
      <h4>主持人汇总（MDAgents Moderator）</h4>
      <p>{{ debate.moderator_synthesis.integration_summary }}</p>
      <p v-if="debate.moderator_synthesis.conflict_notes.length" class="conflicts">
        分歧：{{ debate.moderator_synthesis.conflict_notes.join('；') }}
      </p>
    </div>
  </section>

  <section v-if="safetyPanel" class="safety-panel card">
    <header class="debate-head">
      <h3>Safety Panel</h3>
      <span :class="['badge', safetyPanel.passed ? 'ok' : 'warn']">
        {{ safetyPanel.passed ? '通过' : '需关注' }}
      </span>
    </header>
    <p>{{ safetyPanel.summary }}</p>
    <ul v-if="safetyPanel.flags.length">
      <li v-for="(f, i) in safetyPanel.flags" :key="i">
        [{{ f.severity }}] {{ f.description }}
      </li>
    </ul>
  </section>
</template>

<style scoped>
.debate-panel, .safety-panel { margin-top: 1rem; padding: 1rem; }
.debate-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
.badges { display: flex; gap: 0.4rem; flex-wrap: wrap; }
.badge { font-size: 0.78rem; padding: 0.15rem 0.45rem; border-radius: 4px; background: var(--surface-2); }
.badge.ok { background: #e8f5e9; color: #2e7d32; }
.badge.warn { background: #fff3e0; color: #ef6c00; }
.round-block { border-left: 3px solid var(--primary); padding-left: 0.75rem; margin-bottom: 0.75rem; }
.round-block h4 { font-size: 0.95rem; margin-bottom: 0.25rem; }
.meta { font-size: 0.82rem; color: var(--text-muted); }
.critic { font-size: 0.88rem; margin-top: 0.35rem; }
.consensus { font-size: 0.82rem; color: var(--text-muted); }
.moderator { margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border); }
.conflicts { color: var(--warning); font-size: 0.88rem; }
</style>
