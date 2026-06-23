<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { RouterLink } from 'vue-router'
import { medsafeApi } from '@/api/medsafe'
import { useMultiConsult } from '@/composables/useMultiConsult'
import type { PatientContext, DrugItem, CaseTemplate } from '@/types'
import AgentOpinionCard from '@/components/consult/AgentOpinionCard.vue'
import RuleReviewSummary from '@/components/consult/RuleReviewSummary.vue'
import ClarifyPanel from '@/components/consult/ClarifyPanel.vue'
import DebatePanel from '@/components/consult/DebatePanel.vue'
import RiskBadge from '@/components/common/RiskBadge.vue'

const { loading, error, result, run, reset } = useMultiConsult()

const inputMode = ref<'text' | 'form'>('form')
const clinicalText = ref('')
const persist = ref(true)

const emptyPatient = (): PatientContext => ({
  gender: 'unknown',
  pregnancy_status: 'unknown',
  allergies: [],
  current_medications: [],
  missing_fields: [],
})

const patient = ref<PatientContext>(emptyPatient())
const drugs = ref<DrugItem[]>([])

const templates = ref<CaseTemplate[]>([])
const templatesError = ref('')
const selectedTemplateId = ref('')

const newDrugName = ref('')

onMounted(async () => {
  try {
    const res = await medsafeApi.listCaseTemplates()
    templates.value = res.templates
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

function loadTemplate(templateId: string) {
  const tpl = templates.value.find((t) => t.id === templateId)
  if (!tpl) return
  if (tpl.input_mode === 'text') {
    inputMode.value = 'text'
    clinicalText.value = tpl.text ?? ''
  } else {
    inputMode.value = 'form'
    patient.value = tpl.patient_context ? { ...tpl.patient_context } : emptyPatient()
  }
  drugs.value = tpl.candidate_drugs.map((d) => ({ ...d }))
}

function onTemplateSelect() {
  if (selectedTemplateId.value) loadTemplate(selectedTemplateId.value)
}

function clearForm() {
  clinicalText.value = ''
  patient.value = emptyPatient()
  drugs.value = []
  selectedTemplateId.value = ''
  reset()
}

async function submit() {
  if (inputMode.value === 'text' && !clinicalText.value.trim()) {
    error.value = '请填写病历文本'
    return
  }
  if (inputMode.value === 'form' && drugs.value.length === 0) {
    error.value = '请至少添加一种候选用药'
    return
  }
  const payload = {
    candidate_drugs: drugs.value,
    persist: persist.value,
    ...(inputMode.value === 'text'
      ? { text: clinicalText.value }
      : { patient_context: patient.value }),
  }
  await run(payload)
}

const arb = computed(() => result.value?.arbitration)
</script>

<template>
  <div class="consult-page">
    <header class="page-head">
      <div>
        <h1>多智能体会诊</h1>
        <p>Extract → 规则守门 → 多轮辩论 + Critic → Safety Panel → 主席仲裁</p>
      </div>
    </header>

    <div class="grid-2">
      <section class="card input-panel">
        <div v-if="templates.length" class="template-row">
          <label class="label">载入病例模板（可选）</label>
          <div class="template-controls">
            <select v-model="selectedTemplateId" class="select" @change="onTemplateSelect">
              <option value="">— 手动录入 —</option>
              <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.title }}</option>
            </select>
            <button type="button" class="btn-secondary" @click="clearForm">清空</button>
          </div>
          <p v-if="templatesError" class="hint-err">{{ templatesError }}</p>
        </div>

        <div class="mode-tabs">
          <button :class="{ active: inputMode === 'text' }" type="button" @click="inputMode = 'text'">自然语言</button>
          <button :class="{ active: inputMode === 'form' }" type="button" @click="inputMode = 'form'">结构化表单</button>
        </div>

        <div v-if="inputMode === 'text'" class="field">
          <label class="label">病历文本</label>
          <textarea v-model="clinicalText" class="textarea" rows="8" placeholder="输入患者病历、现病史与用药信息…" />
        </div>

        <div v-else class="form-grid">
          <div><label class="label">性别</label><select v-model="patient.gender" class="select"><option>unknown</option><option>M</option><option>F</option></select></div>
          <div><label class="label">年龄</label><input v-model.number="patient.age" type="number" class="input" min="0" /></div>
          <div><label class="label">妊娠状态</label><input v-model="patient.pregnancy_status" class="input" placeholder="unknown / pregnant / not_applicable" /></div>
          <div><label class="label">过敏 (逗号分隔)</label><input :value="(patient.allergies ?? []).join(', ')" class="input" @input="patient.allergies = ($event.target as HTMLInputElement).value.split(',').map(s=>s.trim()).filter(Boolean)" /></div>
          <div class="full"><label class="label">当前用药 (逗号分隔)</label><input :value="(patient.current_medications ?? []).map(m=>m.name).join(', ')" class="input" @input="patient.current_medications = ($event.target as HTMLInputElement).value.split(',').map(s=>({name:s.trim()})).filter(m=>m.name)" /></div>
        </div>

        <div class="field">
          <label class="label">候选用药</label>
          <ul v-if="drugs.length" class="drug-list">
            <li v-for="(d, i) in drugs" :key="i">
              <strong>{{ d.name }}</strong>
              <span v-if="d.dose">{{ d.dose }}</span>
              <span v-if="d.indication">{{ d.indication }}</span>
              <button type="button" class="btn-ghost" @click="removeDrug(i)">×</button>
            </li>
          </ul>
          <p v-else class="empty-hint">尚未添加候选用药</p>
          <div class="add-drug">
            <input v-model="newDrugName" class="input" placeholder="药名" @keyup.enter="addDrug" />
            <button type="button" class="btn-secondary" @click="addDrug">添加</button>
          </div>
        </div>

        <div class="opts">
          <label><input v-model="persist" type="checkbox" /> 保存 Case Log</label>
        </div>

        <button class="btn-primary submit" type="button" :disabled="loading" @click="submit">
          <span v-if="loading" class="spinner" /> 发起多智能体会诊
        </button>
        <p v-if="error" class="error">{{ error }}</p>
      </section>

      <section v-if="result" class="result-panel">
        <div class="card final-card">
          <h2>最终建议</h2>
          <RiskBadge v-if="arb" :level="arb.consensus_risk_level" :block="arb.consensus_block_decision" />
          <p class="final-text">{{ result.final_recommendation }}</p>
          <p v-if="result.case_id" class="case-id">
            Case: <RouterLink :to="`/cases/${result.case_id}`"><code>{{ result.case_id }}</code></RouterLink>
          </p>
        </div>

        <RuleReviewSummary :rule-output="result.rule_output" />

        <DebatePanel :debate="result.debate" :safety-panel="result.safety_panel" />

        <div class="card">
          <h3>会诊主席仲裁</h3>
          <p v-if="arb">{{ arb.arbitration_notes }}</p>
          <p v-if="arb?.conflict_detected" class="conflict">检测到专家意见冲突</p>
        </div>

        <div class="agents-grid">
          <h3>专家意见 ({{ result.agent_opinions.length }})</h3>
          <AgentOpinionCard v-for="o in result.agent_opinions" :key="o.agent_id" :opinion="o" />
        </div>

        <ClarifyPanel :clarify="result.clarify_output" />
      </section>

      <section v-else-if="!loading" class="card placeholder">
        <p>填写左侧患者信息与候选用药后提交，查看多智能体审查结果</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.page-head h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
.page-head p { color: var(--text-muted); margin-bottom: 1.5rem; }
.template-row { margin-bottom: 1rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border); }
.template-controls { display: flex; gap: 0.5rem; margin-top: 0.35rem; }
.template-controls .select { flex: 1; }
.hint-err { color: var(--danger); font-size: 0.82rem; margin-top: 0.35rem; }
.mode-tabs { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
.mode-tabs button {
  background: var(--surface-2);
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-size: 0.88rem;
}
.mode-tabs button.active { background: var(--primary); color: #fff; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 1rem; }
.form-grid .full { grid-column: 1 / -1; }
.field { margin-bottom: 1rem; }
.drug-list { list-style: none; margin-bottom: 0.5rem; }
.drug-list li {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.4rem 0; border-bottom: 1px solid var(--border);
  font-size: 0.9rem;
}
.empty-hint { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.5rem; }
.add-drug { display: flex; gap: 0.5rem; }
.opts { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.88rem; margin-bottom: 1rem; }
.submit { width: 100%; display: flex; align-items: center; justify-content: center; gap: 0.5rem; }
.error { color: var(--danger); margin-top: 0.75rem; font-size: 0.9rem; }
.result-panel { display: flex; flex-direction: column; gap: 1rem; }
.final-card h2 { margin-bottom: 0.75rem; }
.final-text { margin: 0.75rem 0; font-size: 1.05rem; line-height: 1.6; }
.case-id code { font-family: var(--mono); font-size: 0.85rem; }
.agents-grid h3 { margin-bottom: 0.75rem; }
.agents-grid { display: flex; flex-direction: column; gap: 0.75rem; }
.conflict { color: var(--warning); font-weight: 600; margin-top: 0.5rem; }
.placeholder { color: var(--text-muted); text-align: center; padding: 3rem; }
</style>
