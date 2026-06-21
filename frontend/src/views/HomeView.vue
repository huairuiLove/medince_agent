<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { medsafeApi } from '@/api/medsafe'
import type { HealthResponse, AgentInfo } from '@/types'

const health = ref<HealthResponse | null>(null)
const agents = ref<AgentInfo[]>([])
const error = ref('')

onMounted(async () => {
  try {
    health.value = await medsafeApi.health()
    agents.value = (await medsafeApi.listAgents()).agents
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})

const stages = [
  { n: 1, title: '方案设计', desc: 'MIMIC-III + 本地 LoRA 路线规划' },
  { n: 2, title: 'Extract 原型', desc: '本地 Qwen LoRA → 后迁移 LLM API' },
  { n: 3, title: '规则审查', desc: 'Review / Clarify 确定性引擎' },
  { n: 4, title: '工程落地', desc: '多智能体 + Vue 前端 + Docker' },
]
</script>

<template>
  <div class="home">
    <header class="hero card">
      <div>
        <p class="eyebrow">MedSafe · 临床用药安全</p>
        <h1>多智能体用药规则审查系统</h1>
        <p class="sub">
          规则引擎硬底线 + 影像 2D 分割 + Qwen3-VL + DeepSeek 多智能体报告。
        </p>
        <div class="actions">
          <RouterLink to="/imaging"><button class="btn-primary">影像会诊</button></RouterLink>
          <RouterLink to="/consult"><button class="btn-secondary">文本会诊</button></RouterLink>
        </div>
      </div>
      <div v-if="health" class="status-box">
        <div class="stat"><span>API</span><strong class="ok">{{ health.status }}</strong></div>
        <div class="stat"><span>版本</span><strong>{{ health.version }}</strong></div>
        <div class="stat"><span>LLM</span><strong>{{ health.llm_provider }}</strong></div>
        <div class="stat"><span>运行</span><strong>{{ Math.round(health.uptime_seconds) }}s</strong></div>
      </div>
      <p v-else-if="error" class="err">后端未连接：{{ error }} — 请先 <code>medsafe serve</code></p>
    </header>

    <section class="stages">
      <h2>四阶段演进</h2>
      <div class="stage-grid">
        <div v-for="s in stages" :key="s.n" class="stage card">
          <span class="num">Stage {{ s.n }}</span>
          <h3>{{ s.title }}</h3>
          <p>{{ s.desc }}</p>
        </div>
      </div>
    </section>

    <section v-if="agents.length" class="agents-preview">
      <h2>智能体阵容 ({{ agents.length }})</h2>
      <div class="agent-chips">
        <span v-for="a in agents" :key="a.agent_id" class="chip">{{ a.agent_name }}</span>
      </div>
    </section>
  </div>
</template>

<style scoped>
.hero {
  display: flex;
  justify-content: space-between;
  gap: 2rem;
  align-items: flex-start;
  margin-bottom: 2rem;
  background: linear-gradient(135deg, #fff 0%, #e3f2fd 100%);
}
.eyebrow { font-size: 0.82rem; color: var(--primary); font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
h1 { font-size: 2rem; margin: 0.35rem 0 0.75rem; line-height: 1.2; }
.sub { color: var(--text-muted); max-width: 520px; margin-bottom: 1.25rem; }
.actions { display: flex; gap: 0.75rem; }
.status-box {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
  min-width: 220px;
}
.stat {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.65rem 0.85rem;
}
.stat span { display: block; font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; }
.stat strong { font-size: 1.1rem; }
.ok { color: var(--success); }
.err { color: var(--danger); font-size: 0.9rem; margin-top: 1rem; }
h2 { font-size: 1.15rem; margin-bottom: 1rem; }
.stage-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem; }
@media (max-width: 900px) { .stage-grid { grid-template-columns: 1fr 1fr; } .hero { flex-direction: column; } }
.num { font-size: 0.78rem; color: var(--primary); font-weight: 700; }
.stage h3 { margin: 0.35rem 0; font-size: 1rem; }
.stage p { font-size: 0.85rem; color: var(--text-muted); }
.agent-chips { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.chip {
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 0.4rem 0.85rem;
  border-radius: 999px;
  font-size: 0.88rem;
}
</style>
