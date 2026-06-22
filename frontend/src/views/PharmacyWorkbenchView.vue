<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { medsafeApi } from '@/api/medsafe'
import type { PharmacyQueueItem } from '@/types'

const router = useRouter()
const loading = ref(false)
const error = ref('')
const items = ref<PharmacyQueueItem[]>([])
const total = ref(0)

const grouped = computed(() => {
  const buckets: Record<string, PharmacyQueueItem[]> = {
    hard_stop: [],
    warning: [],
    info: [],
  }
  for (const item of items.value) {
    const key = item.max_alert_level in buckets ? item.max_alert_level : 'info'
    buckets[key]!.push(item)
  }
  return buckets
})

async function loadQueue() {
  loading.value = true
  error.value = ''
  try {
    const res = await medsafeApi.pharmacyQueue()
    items.value = res.items
    total.value = res.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function openReview(id: string) {
  router.push(`/pharmacy/review/${id}`)
}

function levelLabel(level: string) {
  if (level === 'hard_stop') return '强制拦截'
  if (level === 'warning') return '警告'
  return '提示'
}

onMounted(loadQueue)
</script>

<template>
  <div class="workbench">
    <header class="header">
      <div>
        <h1>药师工作台</h1>
        <p class="sub">待审查队列 · 按严重度分组</p>
      </div>
      <div class="actions">
        <button type="button" class="btn-secondary" :disabled="loading" @click="loadQueue">刷新</button>
        <RouterLink to="/pharmacy/audit" class="btn-secondary link-btn">审计日志</RouterLink>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>
    <p v-if="loading" class="muted">加载中…</p>

    <div v-else class="layout">
      <aside class="queue-panel">
        <div class="panel-head">
          <strong>审查队列</strong>
          <span class="badge">{{ total }} 待处理</span>
        </div>
        <section v-for="level in ['hard_stop', 'warning', 'info']" :key="level" class="group">
          <h3>{{ levelLabel(level) }} ({{ grouped[level]?.length ?? 0 }})</h3>
          <button
            v-for="item in grouped[level]"
            :key="item.review_id"
            type="button"
            class="queue-item"
            @click="openReview(item.review_id)"
          >
            <span class="pid">{{ item.patient_id || '未知患者' }}</span>
            <span class="meta">{{ item.department }} · {{ item.alert_count }} 条 alert</span>
            <span class="wait">等待 {{ Math.round(item.wait_minutes) }} 分钟</span>
          </button>
          <p v-if="!grouped[level]?.length" class="empty">暂无</p>
        </section>
      </aside>

      <main class="placeholder">
        <p>从左侧选择一条审查记录，或等待 CPOE 触发 <code>requires_pharmacist_review</code> 后自动入队。</p>
      </main>
    </div>
  </div>
</template>

<style scoped>
.workbench { display: flex; flex-direction: column; gap: 1rem; min-height: 70vh; }
.header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; }
.sub { color: var(--text-muted); margin-top: 0.25rem; }
.actions { display: flex; gap: 0.5rem; }
.link-btn { text-decoration: none; display: inline-flex; align-items: center; }
.layout { display: grid; grid-template-columns: 280px 1fr; gap: 1rem; flex: 1; }
.queue-panel { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; max-height: 75vh; overflow-y: auto; }
.panel-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
.badge { font-size: 0.75rem; background: var(--primary-soft); padding: 0.15rem 0.5rem; border-radius: 999px; }
.group h3 { font-size: 0.85rem; color: var(--text-muted); margin: 0.75rem 0 0.35rem; }
.queue-item { width: 100%; text-align: left; border: 1px solid var(--border); background: var(--bg); border-radius: 6px; padding: 0.5rem 0.65rem; margin-bottom: 0.35rem; cursor: pointer; }
.queue-item:hover { border-color: var(--primary); }
.pid { display: block; font-weight: 600; }
.meta, .wait { display: block; font-size: 0.8rem; color: var(--text-muted); }
.placeholder { border: 1px dashed var(--border); border-radius: 8px; display: flex; align-items: center; justify-content: center; padding: 2rem; color: var(--text-muted); }
.empty { font-size: 0.8rem; color: var(--text-muted); margin: 0.25rem 0; }
.err { color: var(--danger); }
.muted { color: var(--text-muted); }
</style>
