<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { medsafeApi } from '@/api/medsafe'
import type { AgentInfo } from '@/types'

const agents = ref<AgentInfo[]>([])

const details: Record<string, string> = {
  clinical_pharmacist: '审查 DDI、剂量、重复成分、给药途径',
  internal_medicine: '审查适应证与诊断匹配、off-label 风险',
  allergy_specialist: '审查过敏史、交叉过敏、既往 ADR',
  pharmacy_inventory: '审查库存、formulary、缺货替代',
  specialist: '专科禁忌：妊娠/抗凝/老年（动态激活）',
  chief_reviewer: '汇总各专家意见，规则 high 不可覆盖',
  coordinator: '生成追问或保守降级方案',
}

onMounted(async () => {
  agents.value = (await medsafeApi.listAgents()).agents
})
</script>

<template>
  <div>
    <h1>智能体阵容</h1>
    <p class="sub">多智能体会诊 — 规则 evidence 注入各 Agent prompt</p>
    <div class="grid">
      <article v-for="a in agents" :key="a.agent_id" class="card agent">
        <h3>{{ a.agent_name }}</h3>
        <code>{{ a.agent_id }}</code>
        <p class="role">{{ a.role }}</p>
        <p v-if="details[a.agent_id]" class="detail">{{ details[a.agent_id] }}</p>
      </article>
    </div>
  </div>
</template>

<style scoped>
.sub { color: var(--text-muted); margin-bottom: 1.5rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1rem; }
.agent h3 { margin-bottom: 0.35rem; }
code { font-size: 0.78rem; color: var(--text-muted); font-family: var(--mono); }
.role { font-size: 0.88rem; margin: 0.5rem 0; }
.detail { font-size: 0.85rem; color: var(--text-muted); }
</style>
