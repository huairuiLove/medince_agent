<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { medsafeApi } from '@/api/medsafe'

const cases = ref<string[]>([])
const error = ref('')

onMounted(async () => {
  try {
    cases.value = (await medsafeApi.listCases(50)).cases
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})
</script>

<template>
  <div>
    <h1>Case 回放</h1>
    <p class="sub">查看历史审查记录与事件链</p>
    <p v-if="error" class="err">{{ error }}</p>
    <div v-if="cases.length" class="case-list">
      <RouterLink v-for="id in cases" :key="id" :to="`/cases/${id}`" class="case-item card">
        <code>{{ id }}</code>
        <span>查看详情 →</span>
      </RouterLink>
    </div>
    <p v-else-if="!error" class="empty">暂无属于您的 Case，请在会诊页提交并勾选「保存 Case Log」（需已登录）</p>
  </div>
</template>

<style scoped>
.sub { color: var(--text-muted); margin-bottom: 1.5rem; }
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
