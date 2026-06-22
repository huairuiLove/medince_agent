<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const agents = computed(() => auth.workspace?.agents ?? [])

onMounted(async () => {
  if (!auth.workspace) await auth.fetchMe()
})
</script>

<template>
  <div>
    <h1>智能体阵容</h1>
    <p class="sub">
      您的个人配置 — 启用的 Agent 与 Skill 会在多智能体会诊时注入 prompt。
      在 <RouterLink to="/settings">个人配置</RouterLink> 中修改。
    </p>
    <div class="grid">
      <article v-for="a in agents" :key="a.agent_id" class="card agent">
        <div class="head">
          <h3>{{ a.agent_name }}</h3>
          <span class="badge" :class="{ off: !a.enabled }">{{ a.enabled ? '已启用' : '已关闭' }}</span>
        </div>
        <code>{{ a.agent_id }}</code>
        <p class="role">{{ a.role }}</p>
        <p class="skills">
          Skills:
          <span v-for="sid in a.enabled_skills" :key="sid" class="chip">{{ sid }}</span>
          <span v-if="!a.enabled_skills.length" class="muted">无</span>
        </p>
      </article>
    </div>
  </div>
</template>

<style scoped>
.sub { color: var(--text-muted); margin-bottom: 1.5rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1rem; }
.head { display: flex; justify-content: space-between; align-items: center; }
.badge { font-size: 0.72rem; background: var(--primary-light); color: var(--primary-dark); padding: 0.15rem 0.45rem; border-radius: 999px; }
.badge.off { background: var(--surface-2); color: var(--text-muted); }
.agent h3 { margin-bottom: 0.35rem; }
code { font-size: 0.78rem; color: var(--text-muted); font-family: var(--mono); }
.role { font-size: 0.88rem; margin: 0.5rem 0; }
.skills { font-size: 0.82rem; }
.chip { display: inline-block; background: var(--surface-2); padding: 0.1rem 0.4rem; border-radius: 4px; margin: 0.15rem 0.15rem 0 0; font-size: 0.75rem; }
.muted { color: var(--text-muted); }
</style>
