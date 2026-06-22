<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { medsafeApi } from '@/api/medsafe'
import type { OverrideAuditLog, PharmacyStats } from '@/types'

const loading = ref(false)
const error = ref('')
const logs = ref<OverrideAuditLog[]>([])
const stats = ref<PharmacyStats | null>(null)
const total = ref(0)

const filters = ref({
  start_date: '',
  end_date: '',
  drug_name: '',
  alert_level: '',
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [audit, st] = await Promise.all([
      medsafeApi.pharmacyAudit(filters.value),
      medsafeApi.pharmacyStats(),
    ])
    logs.value = audit.items
    total.value = audit.total
    stats.value = st
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function exportCsv() {
  const q = new URLSearchParams()
  if (filters.value.start_date) q.set('start_date', filters.value.start_date)
  if (filters.value.end_date) q.set('end_date', filters.value.end_date)
  if (filters.value.drug_name) q.set('drug_name', filters.value.drug_name)
  if (filters.value.alert_level) q.set('alert_level', filters.value.alert_level)
  const blob = await medsafeApi.pharmacyAuditExport(q.toString())
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'override_audit.csv'
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(load)
</script>

<template>
  <div>
    <header class="head">
      <div>
        <h1>Override 审计</h1>
        <p class="sub">药师 override 记录与统计</p>
      </div>
      <RouterLink to="/pharmacy" class="btn-secondary link-btn">← 工作台</RouterLink>
    </header>

    <div v-if="stats" class="stats-bar card">
      <span>待审 {{ stats.pending_count }}</span>
      <span>本周 override 率 {{ (stats.override_rate * 100).toFixed(1) }}%</span>
      <span>高风险 override 率 {{ (stats.high_risk_override_rate * 100).toFixed(1) }}%</span>
      <span v-if="stats.top_override_drugs[0]">Top 药物：{{ stats.top_override_drugs[0]?.drug_name }}</span>
    </div>

    <div class="card filters">
      <input v-model="filters.start_date" type="date" class="input" placeholder="开始日期" />
      <input v-model="filters.end_date" type="date" class="input" placeholder="结束日期" />
      <input v-model="filters.drug_name" type="text" class="input" placeholder="药物名" />
      <select v-model="filters.alert_level" class="select">
        <option value="">全部级别</option>
        <option value="hard_stop">hard_stop</option>
        <option value="warning">warning</option>
        <option value="info">info</option>
      </select>
      <button type="button" class="btn-primary" :disabled="loading" @click="load">查询</button>
      <button type="button" class="btn-secondary" @click="exportCsv">导出 CSV</button>
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <div class="card table-wrap">
      <table>
        <thead>
          <tr>
            <th>时间</th>
            <th>药师</th>
            <th>药物</th>
            <th>级别</th>
            <th>操作</th>
            <th>原因</th>
            <th>风险接受</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in logs" :key="row.log_id">
            <td>{{ new Date(row.timestamp).toLocaleString() }}</td>
            <td>{{ row.pharmacist_name }}</td>
            <td>{{ row.drug_name }}</td>
            <td>{{ row.alert_level }}</td>
            <td>{{ row.action }}</td>
            <td>{{ row.override_reason }}</td>
            <td>{{ row.risk_acceptance }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!logs.length && !loading" class="empty">暂无审计记录</p>
      <p class="muted">共 {{ total }} 条</p>
    </div>
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem; }
.sub { color: var(--text-muted); }
.stats-bar { display: flex; flex-wrap: wrap; gap: 1.5rem; padding: 0.75rem 1rem; margin-bottom: 1rem; font-size: 0.9rem; }
.filters { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1rem; align-items: center; }
.input, .select { max-width: 160px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid var(--border); }
.empty, .muted { color: var(--text-muted); padding: 0.5rem 0; }
.err { color: var(--danger); }
.link-btn { text-decoration: none; }
</style>
