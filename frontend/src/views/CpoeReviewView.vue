<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { medsafeApi } from '@/api/medsafe'
import type {
  CpoeMedicationOrder,
  CpoeMedicationReviewResponse,
  CpoePatientSnapshot,
  DepartmentContextResponse,
  DrugItem,
} from '@/types'
import RiskBadge from '@/components/common/RiskBadge.vue'
import DeptDrugPanel from '@/components/department/DeptDrugPanel.vue'
import DeptPriorityAlerts from '@/components/department/DeptPriorityAlerts.vue'

const auth = useAuthStore()
const loading = ref(false)
const error = ref('')
const response = ref<CpoeMedicationReviewResponse | null>(null)
const deptCtx = ref<DepartmentContextResponse | null>(null)

const encounterId = ref(`enc_${Date.now()}`)
const patient = ref<CpoePatientSnapshot>({
  patient_id: 'P001',
  gender: 'unknown',
  age: null,
  pregnancy_status: 'unknown',
  lactation_status: 'unknown',
  allergies: [],
  conditions: [],
})

const existingMeds = ref<DrugItem[]>([])
const newExistingMed = ref('')
const orders = ref<CpoeMedicationOrder[]>([])
const newOrder = ref<CpoeMedicationOrder>({
  order_id: '',
  hospital_drug_id: '',
  display_name: '',
  ingredient: '',
  dose: '',
  route: '',
  frequency: '',
  status: 'new',
})

onMounted(async () => {
  try {
    if (!auth.workspace) await auth.fetchMe()
    deptCtx.value = await medsafeApi.getDepartmentContext(auth.profile?.dept_id)
  } catch {
    deptCtx.value = null
  }
})

function pickFormularyDrug(drug: string) {
  newOrder.value.display_name = drug
  newOrder.value.ingredient = drug
}

function addExistingMed() {
  const name = newExistingMed.value.trim()
  if (!name) return
  existingMeds.value.push({ name })
  newExistingMed.value = ''
}

function removeExistingMed(i: number) {
  existingMeds.value.splice(i, 1)
}

function addOrder() {
  const displayName = (newOrder.value.display_name ?? '').trim()
  const ingredient = (newOrder.value.ingredient ?? '').trim()
  const hospitalDrugId = (newOrder.value.hospital_drug_id ?? '').trim()
  const name = displayName || ingredient
  if (!name && !hospitalDrugId) {
    error.value = '请填写院内码或药品名称'
    return
  }
  error.value = ''
  orders.value.push({
    ...newOrder.value,
    order_id: (newOrder.value.order_id ?? '').trim() || `ord_${Date.now()}_${orders.value.length + 1}`,
    display_name: name,
  })
  newOrder.value = {
    order_id: '',
    hospital_drug_id: '',
    display_name: '',
    ingredient: '',
    dose: '',
    route: '',
    frequency: '',
    status: 'new',
  }
}

function removeOrder(i: number) {
  orders.value.splice(i, 1)
}

function alertLevelClass(level: string) {
  if (level === 'hard_stop') return 'badge-high'
  if (level === 'warning') return 'badge-medium'
  return 'badge-none'
}

async function runReview() {
  if (!orders.value.length) {
    error.value = '请至少添加一条待审查医嘱'
    return
  }
  loading.value = true
  error.value = ''
  response.value = null
  try {
    response.value = await medsafeApi.cpoeMedicationReview({
      encounter_id: encounterId.value,
      patient: {
        ...patient.value,
        allergies: [...(patient.value.allergies ?? [])],
        conditions: [...(patient.value.conditions ?? [])],
      },
      orders: orders.value,
      existing_medications: existingMeds.value,
      review_mode: 'pre_save',
      department: auth.profile?.dept_id,
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="cpoe-page">
    <header class="page-head">
      <div>
        <h1>CPOE 用药审查</h1>
        <p class="sub">
          科室：{{ auth.department?.name_cn ?? '未登录' }}
          · 院目录解析 · 规则引擎 · 药师队列联动
        </p>
      </div>
    </header>

    <div class="grid-3">
      <DeptDrugPanel
        v-if="deptCtx?.core_formulary?.length"
        :drugs="deptCtx.core_formulary"
        @select="pickFormularyDrug"
      />

      <section class="card form-panel">
        <label class="field">
          <span class="label">就诊 ID</span>
          <input v-model="encounterId" class="input" />
        </label>

        <h3>患者快照</h3>
        <div class="form-grid">
          <label class="field">
            <span class="label">患者 ID</span>
            <input v-model="patient.patient_id" class="input" />
          </label>
          <label class="field">
            <span class="label">性别</span>
            <select v-model="patient.gender" class="select">
              <option value="unknown">unknown</option>
              <option value="M">M</option>
              <option value="F">F</option>
            </select>
          </label>
          <label class="field">
            <span class="label">年龄</span>
            <input v-model.number="patient.age" type="number" class="input" min="0" />
          </label>
          <label class="field">
            <span class="label">eGFR</span>
            <input v-model.number="patient.egfr" type="number" class="input" min="0" step="1" />
          </label>
          <template v-if="deptCtx?.review_config?.lab_context_defaults">
            <p class="lab-hint">科室关注检验：{{ (deptCtx.review_config.lab_context_defaults as string[]).join(' · ') }}</p>
          </template>
          <label class="field full">
            <span class="label">过敏（逗号分隔）</span>
            <input
              :value="(patient.allergies ?? []).join(', ')"
              class="input"
              @input="patient.allergies = ($event.target as HTMLInputElement).value.split(',').map(s => s.trim()).filter(Boolean)"
            />
          </label>
          <label class="field full">
            <span class="label">合并症（逗号分隔）</span>
            <input
              :value="(patient.conditions ?? []).join(', ')"
              class="input"
              @input="patient.conditions = ($event.target as HTMLInputElement).value.split(',').map(s => s.trim()).filter(Boolean)"
            />
          </label>
        </div>

        <h3>在院用药</h3>
        <ul v-if="existingMeds.length" class="chip-list">
          <li v-for="(m, i) in existingMeds" :key="i">
            {{ m.name }}
            <button type="button" class="btn-ghost" @click="removeExistingMed(i)">×</button>
          </li>
        </ul>
        <div class="add-row">
          <input v-model="newExistingMed" class="input" placeholder="药名" @keyup.enter="addExistingMed" />
          <button type="button" class="btn-secondary" @click="addExistingMed">添加</button>
        </div>

        <h3>新开医嘱</h3>
        <div class="order-form">
          <input v-model="newOrder.hospital_drug_id" class="input" placeholder="院内码（可选）" />
          <input v-model="newOrder.display_name" class="input" placeholder="展示名 / 商品名" />
          <input v-model="newOrder.ingredient" class="input" placeholder="成分 / 通用名" />
          <input v-model="newOrder.dose" class="input" placeholder="剂量" />
          <input v-model="newOrder.route" class="input" placeholder="途径 PO/IV" />
          <input v-model="newOrder.frequency" class="input" placeholder="频次" />
          <button type="button" class="btn-secondary" @click="addOrder">添加医嘱</button>
        </div>

        <ul v-if="orders.length" class="order-list">
          <li v-for="(o, i) in orders" :key="o.order_id">
            <strong>{{ o.display_name || o.ingredient || o.hospital_drug_id }}</strong>
            <span>{{ o.dose }} {{ o.route }} {{ o.frequency }}</span>
            <code v-if="o.hospital_drug_id">{{ o.hospital_drug_id }}</code>
            <button type="button" class="btn-ghost" @click="removeOrder(i)">×</button>
          </li>
        </ul>

        <button class="btn-primary submit" type="button" :disabled="loading" @click="runReview">
          {{ loading ? '审查中…' : '提交 CPOE 审查' }}
        </button>
        <p v-if="error" class="err">{{ error }}</p>
      </section>

      <section v-if="response" class="result-panel">
        <DeptPriorityAlerts
          :alerts="response.alerts"
          :focus-categories="response.department_focus_categories ?? []"
        />
        <div class="card summary-card">
          <h2>审查结果</h2>
          <RiskBadge
            :level="response.overall_status === 'blocked' ? 'high' : response.overall_status === 'warning' ? 'medium' : 'none'"
            :block="response.overall_status === 'blocked'"
          />
          <p class="status-line">
            状态：<strong>{{ response.overall_status }}</strong>
            · 告警 {{ response.alerts.length }} 条
            <span v-if="response.formulary_drug_count"> · 药库 {{ response.formulary_drug_count }} 条</span>
          </p>
          <p v-if="response.requires_pharmacist_review" class="pharm-hint">
            已触发药师复核，请前往
            <RouterLink to="/pharmacy">药师工作台</RouterLink>
            处理队列。
          </p>
          <p v-if="response.unresolved_drugs?.length" class="warn">
            未解析药品：{{ response.unresolved_drugs.join('、') }}
          </p>
        </div>

        <div v-if="response.alerts.length" class="card">
          <h3>告警明细</h3>
          <article v-for="a in response.alerts" :key="a.alert_id" class="alert-row">
            <header>
              <span class="badge" :class="alertLevelClass(a.alert_level)">{{ a.alert_level }}</span>
              <strong>{{ a.display_name || a.summary.slice(0, 40) }}</strong>
            </header>
            <p>{{ a.summary }}</p>
            <p v-if="a.recommendation" class="rec">{{ a.recommendation }}</p>
            <p v-if="a.implicated_drugs?.length" class="meta">涉及：{{ a.implicated_drugs.join('、') }}</p>
          </article>
        </div>
        <p v-else class="card ok-msg">未发现告警，可保存医嘱。</p>
      </section>

      <section v-else-if="!loading" class="card placeholder">
        <p>填写患者信息与新开医嘱后提交，查看 CPOE 审查结果与药师队列触发情况。</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.page-head h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
.sub { color: var(--text-muted); margin-bottom: 1.5rem; font-size: 0.9rem; }
.grid-3 { display: grid; grid-template-columns: 220px 1fr 1fr; gap: 1rem; align-items: start; }
@media (max-width: 1100px) { .grid-3 { grid-template-columns: 1fr; } }
.lab-hint { grid-column: 1 / -1; font-size: 0.78rem; color: var(--text-muted); margin: 0; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; align-items: start; }
@media (max-width: 960px) { .grid-2 { grid-template-columns: 1fr; } }
.form-panel h3 { font-size: 0.92rem; margin: 1rem 0 0.5rem; color: var(--primary-dark); }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.65rem; }
.form-grid .full { grid-column: 1 / -1; }
.field { display: block; margin-bottom: 0.5rem; }
.chip-list { list-style: none; margin-bottom: 0.5rem; }
.chip-list li { display: flex; align-items: center; gap: 0.5rem; padding: 0.25rem 0; font-size: 0.88rem; }
.add-row, .order-form { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem; }
.order-form .input { flex: 1 1 140px; }
.order-list { list-style: none; margin-bottom: 1rem; font-size: 0.88rem; }
.order-list li { padding: 0.45rem 0; border-bottom: 1px solid var(--border); display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; }
.order-list code { font-size: 0.75rem; color: var(--text-muted); }
.submit { width: 100%; margin-top: 0.5rem; }
.err { color: var(--danger); margin-top: 0.75rem; }
.result-panel { display: flex; flex-direction: column; gap: 1rem; }
.summary-card h2 { margin-bottom: 0.65rem; }
.status-line { margin: 0.65rem 0; font-size: 0.92rem; }
.pharm-hint { color: var(--primary); font-size: 0.88rem; }
.warn { color: var(--warning); font-size: 0.88rem; }
.alert-row { padding: 0.75rem 0; border-bottom: 1px solid var(--surface-2); }
.alert-row header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.35rem; }
.rec { color: var(--text-muted); font-size: 0.88rem; }
.meta { font-size: 0.78rem; color: var(--text-muted); }
.ok-msg { color: var(--success, #2e7d32); text-align: center; padding: 2rem; }
.placeholder { color: var(--text-muted); text-align: center; padding: 3rem; }
</style>
