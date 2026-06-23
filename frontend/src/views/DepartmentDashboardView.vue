<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { medsafeApi } from '@/api/medsafe'
import type { DepartmentContextResponse, DepartmentStatsResponse } from '@/types'
import DeptStatsBar from '@/components/department/DeptStatsBar.vue'
import DeptDrugPanel from '@/components/department/DeptDrugPanel.vue'

const auth = useAuthStore()
const loading = ref(true)
const error = ref('')
const ctx = ref<DepartmentContextResponse | null>(null)
const stats = ref<DepartmentStatsResponse | null>(null)

const deptLabel = computed(() => auth.department?.name_cn ?? auth.profile?.dept_id ?? '科室')

onMounted(async () => {
  try {
    if (!auth.workspace) await auth.fetchMe()
    const deptId = auth.profile?.dept_id ?? ''
    const [contextRes, statsRes] = await Promise.all([
      medsafeApi.getDepartmentContext(deptId),
      medsafeApi.getDepartmentStats(deptId),
    ])
    ctx.value = contextRes
    stats.value = statsRes
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="dept-dash">
    <header class="page-head">
      <div>
        <p class="eyebrow">{{ deptLabel }} · 科室工作台</p>
        <h1>科室仪表盘</h1>
        <p class="sub">{{ ctx?.description ?? '科室级审查统计与快捷入口' }}</p>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>
    <p v-else-if="loading" class="muted">加载科室上下文…</p>

    <template v-else>
      <DeptStatsBar
        v-if="stats"
        :reviews-today="stats.reviews_today"
        :alerts-today="stats.alerts_today"
        :overrides-today="stats.overrides_today"
        :pending-queue="stats.pending_queue"
      />

      <div class="grid-2">
        <section class="card shortcuts">
          <h2>快捷入口</h2>
          <div class="actions">
            <RouterLink to="/cpoe"><button class="btn-primary">本科室 CPOE 审查</button></RouterLink>
            <RouterLink to="/cases"><button class="btn-secondary">本科室病例库</button></RouterLink>
            <RouterLink to="/agents"><button class="btn-secondary">科室 Agent 配置</button></RouterLink>
            <RouterLink to="/rule-review"><button class="btn-secondary">规则审查</button></RouterLink>
          </div>
        </section>

        <DeptDrugPanel :drugs="ctx?.core_formulary ?? []" />
      </div>

      <section v-if="stats?.top_alerts?.length" class="card top-alerts">
        <h2>常见 DDI 警示 Top 5</h2>
        <ul>
          <li v-for="(item, i) in stats.top_alerts" :key="i">
            <span class="count">{{ item.count }}</span>
            {{ item.summary }}
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.eyebrow { font-size: 0.78rem; color: var(--text-muted); margin: 0 0 0.25rem; }
.sub { color: var(--text-muted); margin-top: 0.35rem; }
.grid-2 { display: grid; grid-template-columns: 1fr 280px; gap: 1rem; margin-bottom: 1rem; }
.shortcuts h2, .top-alerts h2 { font-size: 1rem; margin: 0 0 0.75rem; }
.actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.top-alerts ul { margin: 0; padding: 0; list-style: none; }
.top-alerts li { padding: 0.45rem 0; border-bottom: 1px solid var(--border); font-size: 0.88rem; }
.count {
  display: inline-block; min-width: 1.5rem; text-align: center;
  background: var(--surface-2); border-radius: 4px; margin-right: 0.5rem; font-size: 0.75rem;
}
.err { color: var(--danger); }
.muted { color: var(--text-muted); }
@media (max-width: 900px) { .grid-2 { grid-template-columns: 1fr; } }
</style>
