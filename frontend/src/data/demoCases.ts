import type { DemoCase } from '@/types'

export const DEMO_CASES: DemoCase[] = [
  {
    id: 'demo-01',
    title: '高风险：华法林 + 布洛芬',
    description: 'DDI 出血风险，应阻断',
    mode: 'context',
    patient_context: {
      gender: 'M',
      age: 67,
      chief_complaint: '胸痛和呼吸困难',
      current_medications: [
        { name: 'warfarin', dose: '5mg', route: 'PO' },
        { name: 'aspirin', dose: '81mg', route: 'PO' },
      ],
      allergies: [],
      pregnancy_status: 'not_applicable',
      missing_fields: ['allergies'],
    },
    candidate_drugs: [{ name: 'ibuprofen', dose: '400mg', indication: '止痛' }],
  },
  {
    id: 'demo-02',
    title: '过敏史缺失 + 阿莫西林',
    description: '需追问 allergies',
    mode: 'context',
    patient_context: {
      gender: 'F',
      age: 28,
      current_medications: [{ name: 'levothyroxine' }],
      allergies: [],
      pregnancy_status: 'unknown',
      missing_fields: ['allergies'],
    },
    candidate_drugs: [{ name: 'amoxicillin', indication: '感染' }],
  },
  {
    id: 'demo-03',
    title: '妊娠状态未知 + 赖诺普利',
    description: 'ACEI 妊娠禁忌需澄清',
    mode: 'context',
    patient_context: {
      gender: 'F',
      age: 32,
      pregnancy_status: 'unknown',
      allergies: [],
      current_medications: [],
      missing_fields: ['pregnancy_status', 'allergies'],
    },
    candidate_drugs: [{ name: 'lisinopril', dose: '10mg', indication: '高血压' }],
  },
  {
    id: 'demo-04',
    title: '自然语言病历抽取',
    description: '自然语言病历 → LLM 结构化抽取',
    mode: 'text',
    text: '病人基本信息：性别M，年龄67。主诉胸痛和呼吸困难。既往有高血压和冠心病。当前服用 warfarin 和 metoprolol。候选用药 ibuprofen 400mg 止痛。',
    candidate_drugs: [{ name: 'ibuprofen', dose: '400mg' }],
  },
  {
    id: 'demo-05',
    title: '完整会诊 Case',
    description: '多候选药 + 青霉素过敏',
    mode: 'context',
    patient_context: {
      gender: 'F',
      age: 35,
      chief_complaint: '剧烈头痛',
      current_medications: [{ name: 'propranolol', dose: '40mg' }],
      allergies: ['penicillin'],
      pregnancy_status: 'unknown',
      missing_fields: ['pregnancy_status'],
    },
    candidate_drugs: [
      { name: 'lisinopril', indication: '高血压' },
      { name: 'ibuprofen', indication: '头痛' },
    ],
  },
]

export const DEMO_TEXT = `病人基本信息：
- 性别：M
- 年龄：67
主诉：胸痛和呼吸困难
既往：高血压、房颤，长期口服华法林
当前用药：warfarin 5mg；aspirin 81mg`
