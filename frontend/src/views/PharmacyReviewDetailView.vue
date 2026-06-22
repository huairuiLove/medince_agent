<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { medsafeApi } from '@/api/medsafe'
import type { AlertDecisionAction, PharmacistReview, RiskAcceptance } from '@/types'
import RiskBadge from '@/components/common/RiskBadge.vue'

const route = useRoute()
const router = useRouter()
const reviewId = computed(() => String(route.params.id ?? ''))

const loading = ref(false)
const error = ref('')
const review = ref<PharmacistReview | null>(null)
const submitting = ref(false)

const overrideDialog = ref<{ alertId: string; open: boolean }>({ alertId: '', open: false })
const overrideReason = ref('')
const overrideRisk = ref<RiskAcceptance>('medium')
const overrideNotes = ref('')

const reasonOptions = [
  '临床获益大于风险',
  '已调整剂量',
  '患者知情同意',
  '无替代方案',
  '其他（见备注）',
]

const decisionsByAlert = computed(() => {
  const map = new Map<string, { action: string; at?: string }>()
  for (const d of review.value?.alert_decisions ?? []) {
    map.set(d.alert_id, { action: d.action, at: d.decided_at })
  }
  return map
})

async function loadReview() {
  loading.value = true
  error.value = ''
  try {
    review.value = await medsafeApi.pharmacyReview(reviewId.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function decide(alertId: string, action: AlertDecisionAction, extra?: {
  override_reason?: string
  override_risk_acceptance?: RiskAcceptance
  pharmacist_notes?: string
}) {
  if (!review.value) return
  try {
    review.value = await medsafeApi.pharmacyDecide(reviewId.value, {
      alert_id: alertId,
      action,
      ...extra,
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

function promptOverride(alertId: string, level: string) {
  if (level === 'hard_stop' && !window.confirm('此为强制拦截，Override 将记录审计日志并由上级药师复核。确认继续？')) {
    return
  }
  overrideDialog.value = { alertId, open: true }
  overrideReason.value = reasonOptions[0]!
  overrideRisk.value = 'medium'
  overrideNotes.value = ''
}

async function confirmOverride() {
  const { alertId } = overrideDialog.value
  overrideDialog.value.open = false
  await decide(alertId, 'override', {
    override_reason: overrideReason.value,
    override_risk_acceptance: overrideRisk.value,
    pharmacist_notes: overrideNotes.value || undefined,
  })
}

async function submitAll() {
  if (!review.value) return
  submitting.value = true
  error.value = ''
  try {
    review.value = await medsafeApi.pharmacySubmit(reviewId.value, {})
    router.push('/pharmacy')
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    submitting.value = false
  }
}

const allDecided = computed(() => {
  if (!review.value) return false
  const ids = new Set(review.value.cpoe_response.alerts.map(a => a.alert_id))
  const decided = new Set(review.value.alert_decisions.map(d => d.alert_id))
  for (const id of ids) {
    if (!decided.has(id)) return false
  }
  return ids.size > 0
})

onMounted(loadReview)
</script>

<template>
  <div v-if="loading" class="muted">加载审查详情…</div>
  <div v-else-if="review" class="detail">
    <header class="head">
      <button type="button" class="btn-secondary" @click="router.push('/pharmacy')">← 返回队列</button>
      <div>
        <h1>审查 #{{ review.review_id.slice(0, 8) }}</h1>
        <p class="sub">患者 {{ review.patient_id || '—' }} · {{ review.department }} · {{ review.status }}</p>
      </div>
      <button type="button" class="btn-primary" :disabled="!allDecided || submitting || review.status !== 'pending'" @click="submitAll">
        {{ submitting ? '提交中…' : '提交全部决策' }}
      </button>
    </header>

    <p v-if="error" class="err">{{ error }}</p>

    <div class="columns">
      <section class="card alerts">
        <h2>Alert 列表</h2>
        <article v-for="alert in review.cpoe_response.alerts" :key="alert.alert_id" class="alert-row">
          <div class="alert-head">
            <span class="level" :class="alert.alert_level">{{ alert.alert_level }}</span>
            <strong>{{ alert.summary }}</strong>
          </div>
          <p class="rec">{{ alert.recommendation }}</p>
          <p v-if="decisionsByAlert.has(alert.alert_id)" class="done">
            已决策：{{ decisionsByAlert.get(alert.alert_id)?.action }}
          </p>
          <div v-else-if="review.status === 'pending'" class="btns">
            <button type="button" class="btn-secondary" @click="decide(alert.alert_id, 'acknowledge')">确认</button>
            <button type="button" class="btn-secondary" @click="decide(alert.alert_id, 'hold')">暂缓</button>
            <button type="button" class="btn-secondary" @click="decide(alert.alert_id, 'escalate')">上报</button>
            <button type="button" class="btn-danger" @click="promptOverride(alert.alert_id, alert.alert_level)">Override</button>
          </div>
        </article>
      </section>

      <aside class="card context">
        <h2>患者上下文</h2>
        <dl>
          <dt>整体状态</dt>
          <dd><RiskBadge :level="review.cpoe_response.overall_status === 'blocked' ? 'high' : 'medium'" /></dd>
          <dt>Alert 数</dt>
          <dd>{{ review.cpoe_response.alerts.length }}</dd>
          <dt>需药师复核</dt>
          <dd>{{ review.cpoe_response.requires_pharmacist_review ? '是' : '否' }}</dd>
        </dl>
      </aside>
    </div>

    <dialog v-if="overrideDialog.open" open class="dialog card">
      <h3>Override 决策</h3>
      <label class="label">原因（必填）</label>
      <select v-model="overrideReason" class="select">
        <option v-for="r in reasonOptions" :key="r" :value="r">{{ r }}</option>
      </select>
      <label class="label">风险接受度</label>
      <select v-model="overrideRisk" class="select">
        <option value="low">低</option>
        <option value="medium">中</option>
        <option value="high">高</option>
      </select>
      <label class="label">备注</label>
      <textarea v-model="overrideNotes" rows="3" class="textarea" />
      <div class="dialog-actions">
        <button type="button" class="btn-secondary" @click="overrideDialog.open = false">取消</button>
        <button type="button" class="btn-danger" @click="confirmOverride">确认 Override</button>
      </div>
    </dialog>
  </div>
</template>

<style scoped>
.head { display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; margin-bottom: 1rem; }
.sub { color: var(--text-muted); }
.columns { display: grid; grid-template-columns: 1fr 300px; gap: 1rem; }
.alert-row { border-top: 1px solid var(--border); padding: 0.75rem 0; }
.alert-head { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.level { font-size: 0.7rem; padding: 0.1rem 0.4rem; border-radius: 4px; text-transform: uppercase; }
.level.hard_stop { background: #fee2e2; color: #991b1b; }
.level.warning { background: #fef3c7; color: #92400e; }
.rec { font-size: 0.9rem; color: var(--text-muted); margin: 0.35rem 0; }
.btns { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.5rem; }
.done { color: var(--success, #059669); font-size: 0.85rem; }
.dialog { max-width: 420px; margin: 1rem auto; padding: 1rem; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem; }
.textarea { width: 100%; }
.err { color: var(--danger); }
.muted { color: var(--text-muted); }
</style>
