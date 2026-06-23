<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { medsafeApi } from '@/api/medsafe'
import type { CaseSummary } from '@/types'

const auth = useAuthStore()
const cases = ref<CaseSummary[]>([])
const error = ref('')

const deptLabel = computed(() => auth.department?.name_cn ?? auth.profile?.dept_id ?? '—')

onMounted(async () => {
  try {
    if (!auth.workspace) await auth.fetchMe()
    if (!auth.profile?.dept_id) return
    cases.value = (await medsafeApi.listCases(50)).cases
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})
</script>

<template>
  <div>
    <h1>Case 回放</h1>
    <p class="sub">本科室多智能体会诊历史 · 科室：{{ deptLabel }}</p>

    <p v-if="error" class="err">{{ error }}</p>
    <p v-else-if="!auth.profile?.dept_id" class="empty">登录后可查看本科室 Case 回放</p>

    <div v-else-if="cases.length" class="case-table card">
      <table>
        <thead>
          <tr>
            <th>科室</th>
            <th>Case ID</th>
            <th>更新时间</th>
            <th>专家数</th>
            <th>最终建议</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in cases" :key="item.case_id">
            <td>{{ item.department_name_cn || deptLabel }}</td>
            <td><code>{{ item.case_id }}</code></td>
            <td>{{ item.updated_at || item.created_at }}</td>
            <td>{{ item.agent_count }}</td>
            <td class="rec">{{ item.final_recommendation || '—' }}</td>
            <td>
              <RouterLink :to="`/cases/${item.case_id}`" class="link">查看详情 →</RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-else-if="!error" class="empty">
      本科室暂无多智能体会诊回放。完成一次「多智能体会诊」后将自动保存到此列表。
    </p>
  </div>
</template>

<style scoped>
.sub { color: var(--text-muted); margin-bottom: 1rem; }
.case-table { overflow-x: auto; padding: 0; }
table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
th, td { border-bottom: 1px solid var(--border); padding: 0.65rem 0.75rem; text-align: left; vertical-align: top; }
th { background: var(--surface-2); color: var(--text-muted); font-weight: 600; }
code { font-family: var(--mono); font-size: 0.82rem; }
.rec { max-width: 360px; color: var(--text-muted); }
.link { color: var(--primary); text-decoration: none; white-space: nowrap; }
.link:hover { text-decoration: underline; }
.empty, .err { color: var(--text-muted); }
.err { color: var(--danger); }
</style>
