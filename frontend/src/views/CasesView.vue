<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { medsafeApi } from '@/api/medsafe'

const auth = useAuthStore()
const cases = ref<string[]>([])
const error = ref('')
const filter = ref<'all' | 'dept' | 'other'>('dept')

const myDept = computed(() => auth.profile?.dept_id ?? '')

const filteredCases = computed(() => {
  if (filter.value === 'all') return cases.value
  return cases.value.filter(id => {
    const isDept = id.includes(myDept.value) || id.includes('clinical_' + myDept.value.replace('_', ''))
    return filter.value === 'dept' ? isDept || !myDept.value : !isDept
  })
})

onMounted(async () => {
  try {
    if (!auth.workspace) await auth.fetchMe()
    cases.value = (await medsafeApi.listCases(50)).cases
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})
</script>

<template>
  <div>
    <h1>Case 回放</h1>
    <p class="sub">查看历史审查记录与事件链 · 科室：{{ auth.department?.name_cn ?? '—' }}</p>

    <div class="filters">
      <button type="button" :class="{ active: filter === 'all' }" @click="filter = 'all'">All</button>
      <button type="button" :class="{ active: filter === 'dept' }" @click="filter = 'dept'">本科室</button>
      <button type="button" :class="{ active: filter === 'other' }" @click="filter = 'other'">其他科室</button>
    </div>

    <p v-if="error" class="err">{{ error }}</p>
    <div v-if="filteredCases.length" class="case-list">
      <RouterLink v-for="id in filteredCases" :key="id" :to="`/cases/${id}`" class="case-item card">
        <code>{{ id }}</code>
        <span>查看详情 →</span>
      </RouterLink>
    </div>
    <p v-else-if="!error" class="empty">暂无匹配的 Case，请在会诊页提交并勾选「保存 Case Log」（需已登录）</p>
  </div>
</template>

<style scoped>
.sub { color: var(--text-muted); margin-bottom: 1rem; }
.filters { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
.filters button {
  border: 1px solid var(--border); background: var(--surface-2);
  padding: 0.3rem 0.75rem; border-radius: 999px; cursor: pointer; font-size: 0.82rem;
}
.filters button.active { border-color: var(--primary); color: var(--primary); }
.case-list { display: flex; flex-direction: column; gap: 0.65rem; }
.case-item {
  display: flex; justify-content: space-between; align-items: center;
  text-decoration: none; color: inherit;
}
.case-item:hover { border-color: var(--primary); }
code { font-family: var(--mono); }
.empty, .err { color: var(--text-muted); }
.err { color: var(--danger); }
</style>
