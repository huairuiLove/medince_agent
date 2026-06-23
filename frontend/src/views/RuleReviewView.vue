<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { medsafeApi } from '@/api/medsafe'
import type { PatientContext, DrugItem, CaseTemplate, ReviewOutput } from '@/types'
import { drugsWithoutIndication, drugDetailParts, mergeDrugIndicationsIntoDiagnoses } from '@/utils/patientForm'
import RuleReviewSummary from '@/components/consult/RuleReviewSummary.vue'

const loading = ref(false)
const error = ref('')
const review = ref<ReviewOutput | null>(null)
const templates = ref<CaseTemplate[]>([])
const templatesError = ref('')
const selectedTemplateId = ref('')

const emptyPatient = (): PatientContext => ({
  gender: 'unknown',
  pregnancy_status: 'unknown',
  allergies: [],
  current_medications: [],
  missing_fields: [],
  diagnoses: [],
})

const patient = ref<PatientContext>(emptyPatient())
const drugs = ref<DrugItem[]>([])
const newDrugName = ref('')
const newDiagnosis = ref('')

onMounted(async () => {
  try {
    const res = await medsafeApi.listCaseTemplates()
    templates.value = res.templates.filter((t) => t.input_mode === 'context' && t.patient_context)
  } catch (e) {
    templatesError.value = e instanceof Error ? e.message : String(e)
  }
})

function addDrug() {
  if (newDrugName.value.trim()) {
    drugs.value.push({ name: newDrugName.value.trim() })
    newDrugName.value = ''
  }
}

function removeDrug(i: number) {
  drugs.value.splice(i, 1)
}

function addDiagnosis() {
  const name = newDiagnosis.value.trim()
  if (!name) return
  if (!patient.value.diagnoses) patient.value.diagnoses = []
  if (!patient.value.diagnoses.some((d) => d.name === name)) {
    patient.value.diagnoses.push({ name })
  }
  newDiagnosis.value = ''
}

function removeDiagnosis(i: number) {
  patient.value.diagnoses?.splice(i, 1)
}

function loadTemplate(templateId: string) {
  const tpl = templates.value.find((t) => t.id === templateId)
  if (!tpl?.patient_context) return
  patient.value = {
    ...tpl.patient_context,
    diagnoses: [...(tpl.patient_context.diagnoses ?? [])],
  }
  mergeDrugIndicationsIntoDiagnoses(patient.value, tpl.candidate_drugs)
  drugs.value = drugsWithoutIndication(tpl.candidate_drugs)
}

function onTemplateSelect() {
  if (selectedTemplateId.value) loadTemplate(selectedTemplateId.value)
}

async function runReview() {
  if (drugs.value.length === 0) {
    error.value = '请至少添加一种候选用药'
    return
  }
  loading.value = true
  error.value = ''
  review.value = null
  try {
    const res = await medsafeApi.ruleReview(patient.value, drugs.value)
    review.value = res.review_output
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div>
    <h1>规则审查</h1>
    <p class="sub">纯规则引擎，无 LLM 多智能体 — 确定性安全底线</p>

    <div class="card form-panel">
      <div v-if="templates.length" class="template-row">
        <label class="label">载入病例模板（可选）</label>
        <select v-model="selectedTemplateId" class="select" @change="onTemplateSelect">
          <option value="">— 手动录入 —</option>
          <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.title }}</option>
        </select>
        <p v-if="templatesError" class="err">{{ templatesError }}</p>
      </div>

      <div class="form-grid">
        <div><label class="label">性别</label><select v-model="patient.gender" class="select"><option>unknown</option><option>M</option><option>F</option></select></div>
        <div><label class="label">年龄</label><input v-model.number="patient.age" type="number" class="input" min="0" /></div>
        <div><label class="label">妊娠状态</label><input v-model="patient.pregnancy_status" class="input" /></div>
        <div class="full"><label class="label">过敏 (逗号分隔)</label><input :value="(patient.allergies ?? []).join(', ')" class="input" @input="patient.allergies = ($event.target as HTMLInputElement).value.split(',').map(s=>s.trim()).filter(Boolean)" /></div>
        <div class="full"><label class="label">当前用药 (逗号分隔)</label><input :value="(patient.current_medications ?? []).map(m=>m.name).join(', ')" class="input" @input="patient.current_medications = ($event.target as HTMLInputElement).value.split(',').map(s=>({name:s.trim()})).filter(m=>m.name)" /></div>
      </div>

      <div class="field">
        <label class="label">病症 / 诊断</label>
        <ul v-if="patient.diagnoses?.length" class="tag-list">
          <li v-for="(dx, i) in patient.diagnoses" :key="i">
            <span>{{ dx.name }}<small v-if="dx.icd9_code"> · {{ dx.icd9_code }}</small></span>
            <button type="button" class="btn-ghost" @click="removeDiagnosis(i)">×</button>
          </li>
        </ul>
        <p v-else class="empty-hint">尚未添加病症或诊断</p>
        <div class="add-drug">
          <input v-model="newDiagnosis" class="input" placeholder="如：社区获得性肺炎" @keyup.enter="addDiagnosis" />
          <button type="button" class="btn-secondary" @click="addDiagnosis">添加</button>
        </div>
      </div>

      <div class="field">
        <label class="label">候选用药</label>
        <ul v-if="drugs.length" class="drug-list">
          <li v-for="(d, i) in drugs" :key="i">
            <strong>{{ d.name }}</strong>
            <span v-for="(part, j) in drugDetailParts(d)" :key="j" class="drug-meta">{{ part }}</span>
            <button type="button" class="btn-ghost" @click="removeDrug(i)">×</button>
          </li>
        </ul>
        <div class="add-drug">
          <input v-model="newDrugName" class="input" placeholder="药名" @keyup.enter="addDrug" />
          <button type="button" class="btn-secondary" @click="addDrug">添加</button>
        </div>
      </div>

      <button class="btn-primary" type="button" :disabled="loading" @click="runReview">
        {{ loading ? '审查中…' : '运行规则审查' }}
      </button>
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <RuleReviewSummary v-if="review" :rule-output="review" />
    <p v-else-if="!loading" class="empty">填写患者信息与候选用药后运行审查</p>
  </div>
</template>

<style scoped>
h1 { margin-bottom: 0.25rem; }
.sub { color: var(--text-muted); margin-bottom: 1.5rem; }
.form-panel { display: flex; flex-direction: column; gap: 1rem; margin-bottom: 1rem; }
.template-row .select { max-width: 100%; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
.form-grid .full { grid-column: 1 / -1; }
.drug-list { list-style: none; margin: 0.35rem 0; }
.drug-list li { display: flex; gap: 0.5rem; align-items: center; padding: 0.25rem 0; }
.drug-meta { color: var(--text-muted); font-size: 0.85rem; }
.tag-list { list-style: none; margin: 0.35rem 0; }
.tag-list li { display: flex; gap: 0.5rem; align-items: center; padding: 0.25rem 0; }
.tag-list small { color: var(--text-muted); font-weight: normal; }
.empty-hint { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.35rem; }
.add-drug { display: flex; gap: 0.5rem; margin-top: 0.35rem; }
.err { color: var(--danger); }
.empty { color: var(--text-muted); margin-top: 1rem; }
</style>
