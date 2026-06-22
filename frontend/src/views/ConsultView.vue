<script setup lang="ts">
import { ref, computed } from 'vue'
import { RouterLink } from 'vue-router'
import { useMultiConsult } from '@/composables/useMultiConsult'
import { DEMO_CASES, DEMO_TEXT } from '@/data/demoCases'
import type { PatientContext, DrugItem } from '@/types'
import AgentOpinionCard from '@/components/consult/AgentOpinionCard.vue'
import RuleReviewSummary from '@/components/consult/RuleReviewSummary.vue'
import ClarifyPanel from '@/components/consult/ClarifyPanel.vue'
import DebatePanel from '@/components/consult/DebatePanel.vue'
import RiskBadge from '@/components/common/RiskBadge.vue'

const { loading, error, result, run } = useMultiConsult()

const inputMode = ref<'text' | 'form'>('text')
const clinicalText = ref(DEMO_TEXT)
const unableToAnswer = ref(false)
const persist = ref(true)

const patient = ref<PatientContext>({
  gender: 'M',
  age: 67,
  pregnancy_status: 'unknown',
  allergies: [],
  current_medications: [{ name: 'warfarin' }],
  missing_fields: [],
})
const drugs = ref<DrugItem[]>([{ name: 'ibuprofen', dose: '400mg', indication: '止痛' }])

const newDrugName = ref('')

function addDrug() {
  if (newDrugName.value.trim()) {
    drugs.value.push({ name: newDrugName.value.trim() })
    newDrugName.value = ''
  }
}

function removeDrug(i: number) {
  drugs.value.splice(i, 1)
}

function loadDemo(demoId: string) {
  const d = DEMO_CASES.find((c) => c.id === demoId)
  if (!d) return
  if (d.mode === 'text') {
    inputMode.value = 'text'
    clinicalText.value = d.text ?? ''
  } else {
    inputMode.value = 'form'
    patient.value = { ...d.patient_context! }
  }
  drugs.value = [...d.candidate_drugs]
}

async function submit() {
  const payload = {
    candidate_drugs: drugs.value,
    unable_to_answer: unableToAnswer.value,
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

    <div class="demo-bar card">
      <span class="label">快速载入 Demo</span>
      <div class="demo-btns">
        <button
          v-for="d in DEMO_CASES"
          :key="d.id"
          class="btn-secondary"
          type="button"
          @click="loadDemo(d.id)"
        >
          {{ d.title }}
        </button>
      </div>
    </div>

    <div class="grid-2">
      <section class="card input-panel">
        <div class="mode-tabs">
          <button :class="{ active: inputMode === 'text' }" type="button" @click="inputMode = 'text'">自然语言</button>
          <button :class="{ active: inputMode === 'form' }" type="button" @click="inputMode = 'form'">结构化表单</button>
        </div>

        <div v-if="inputMode === 'text'" class="field">
          <label class="label">病历文本</label>
          <textarea v-model="clinicalText" class="textarea" rows="8" />
        </div>

        <div v-else class="form-grid">
          <div><label class="label">性别</label><select v-model="patient.gender" class="select"><option>M</option><option>F</option></select></div>
          <div><label class="label">年龄</label><input v-model.number="patient.age" type="number" class="input" /></div>
          <div><label class="label">妊娠状态</label><input v-model="patient.pregnancy_status" class="input" /></div>
          <div><label class="label">过敏 (逗号分隔)</label><input :value="(patient.allergies ?? []).join(', ')" class="input" @input="patient.allergies = ($event.target as HTMLInputElement).value.split(',').map(s=>s.trim()).filter(Boolean)" /></div>
          <div class="full"><label class="label">当前用药 (逗号分隔)</label><input :value="(patient.current_medications ?? []).map(m=>m.name).join(', ')" class="input" @input="patient.current_medications = ($event.target as HTMLInputElement).value.split(',').map(s=>({name:s.trim()})).filter(m=>m.name)" /></div>
        </div>

        <div class="field">
          <label class="label">候选用药</label>
          <ul class="drug-list">
            <li v-for="(d, i) in drugs" :key="i">
              <strong>{{ d.name }}</strong>
              <span v-if="d.dose">{{ d.dose }}</span>
              <span v-if="d.indication">{{ d.indication }}</span>
              <button type="button" class="btn-ghost" @click="removeDrug(i)">×</button>
            </li>
          </ul>
          <div class="add-drug">
            <input v-model="newDrugName" class="input" placeholder="药名" @keyup.enter="addDrug" />
            <button type="button" class="btn-secondary" @click="addDrug">添加</button>
          </div>
        </div>

        <div class="opts">
          <label><input v-model="unableToAnswer" type="checkbox" /> 无法补充信息（保守降级）</label>
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
        <p>填写左侧信息并提交，查看多智能体审查结果</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.page-head h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
.page-head p { color: var(--text-muted); margin-bottom: 1.5rem; }
.demo-bar { margin-bottom: 1rem; }
.demo-btns { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }
.demo-btns button { font-size: 0.82rem; padding: 0.45rem 0.75rem; }
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
