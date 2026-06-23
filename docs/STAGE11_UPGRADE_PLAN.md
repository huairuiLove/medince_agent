# MedSafe Stage 11 升级方案：科室深度专业化——从"规则仓库"到"科室级智能审查"

## 〇、完善性审计结论

对 Stage 10 终态的三维度审计揭示了三个系统性缺口：

### 0.1 前端可视化：28 科室共享同一套通用视图

| 维度 | 现状 | 评估 |
|------|------|------|
| 科室专属视图 | **0 个** | 所有科室共用 ConsultView/CpoeReviewView/ImagingView |
| 科室选择器 | 仅注册时下拉框 | 登录后无法切换科室 |
| 科室仪表盘 | **不存在** | 无科室级审查统计、无科室特有指标 |
| 科室咨询表单 | **不存在** | 所有科室用同一个 consultation 输入框 |
| 科室影像过滤 | **不存在** | ImagingView 按 source 过滤（mimic_cxr/brats2024），不按科室 |
| 科室 case 模板 | **不存在** | CasesView 无科室过滤 |
| 科室 agent 选择 | **不存在** | 用户无法看到/配置本科室的 agent 偏好 |
| nav_routes 自定义 | 仅 2 个科室定义 | respiratory(8路由) + pharmacy(9路由)，其余 26 科室用默认全集 |

**结论：科室在前端仅体现为——侧栏用户名下方的科室名标签 + Settings 页的只读信息卡。没有科室级的功能差异化。**

### 0.2 知识库：11 科室有规则，14 科室零规则，运行时不过滤

**科室 DDI 规则分布（`stage9_curated_rules.py` 中标注的 department 字段）：**

| 覆盖等级 | 科室 | DDI 规则数 | Benchmark |
|----------|------|-----------|-----------|
| 深度 | 心内科 | 134 | 15 cases |
| 深度 | 肾内科 | 114 | 8 cases |
| 深度 | 神经内科 | 106 | 12 cases |
| 深度 | 老年科 | 90 + 4 scenario | 6 cases |
| 中度 | 内分泌 | 67 | 10 cases |
| 中度 | 精神科 | 56 | 6 cases |
| 浅度 | 感染科 | 24 | 8 cases |
| 浅度 | ICU | 16 | 6 cases |
| 浅度 | 风湿免疫 | 13 | 8 cases |
| 浅度 | 血液科 | 12 | 8 cases |
| 浅度 | 消化内科 | 7 | 8 cases |
| **零规则** | **14 科室** | **0** | 仅复用其他科室规则 |

**14 个零规则科室**：呼吸科、肿瘤科、急诊科、普通内科、儿科、骨科、泌尿外科、麻醉科、妇产科、神经外科、放射科、皮肤科、眼科、耳鼻喉科、康复科。

**核心问题**：规则上的 `department` 字段是**纯元数据标注**——`ReviewEngine` 和 `SafetyKnowledgeBase` 完全忽略此字段。一个心内科患者和一个皮肤科患者，只要开了同样的药对，触发的告警完全一样。

### 0.3 智能体：7 个通用 agent，零科室关联

| 维度 | 现状 | 评估 |
|------|------|------|
| agent 注册 | 7 个固定 agent | 按角色（药师/内科/过敏/库管/专科/主席/协调）分，不按科室 |
| agent prompt | 固定 skill markdown | 无科室变量替换，所有科室看同样的提示词 |
| specialist 激活 | 基于患者属性 | 药物关键词 + 年龄 + 性别触发，不看用户科室 |
| orchestrator | 无科室路由 | 全局单例，所有科室走同一条 agent 链路 |
| debate engine | 无科室过滤 | 所有 agent 对所有科室案件发表意见 |
| 科室目录 vs agent | **完全解耦** | `catalog.json` 与 `registry.yaml` 无任何交叉引用 |

**结论：当前系统是"一个审查引擎服务全院"模式。虽然规则量（39,679 DDI）已经够大，但缺乏科室级上下文感知——一个心内科主任登录系统看到的 agent 行为和一个皮肤科住院医完全一样。**

---

## 一、方向一：科室感知审查引擎（Department-Aware Review Engine）

### 1.1 科室上下文注入

**目标**：让科室信息从"用户元数据"升级为"审查流水线的核心上下文"。

**改动范围**：

```
CpoeMedicationReviewRequest  → +department: str（用户科室）
  → PatientContext           → +department: str
    → ReviewEngine.review()  → 接收 department 参数
      → SafetyKnowledgeBase  → 新增 interaction_rules_for_pair(drug_a, drug_b, department=None)
```

**规则优先级策略（非过滤，是加权）**：

```
对于每个匹配到的 rule:
  if rule.department == patient.department:
    → priority_boost = 1.5（本科室规则优先展示）
    → alert_summary 前缀加 "[本科室重点]"
  elif rule.department is None:
    → priority_boost = 1.0（通用规则不变）
  else:
    → priority_boost = 0.8（他科规则降权但不隐藏）
```

**设计原则：不隐藏任何规则，只做优先级排序。** 心内科患者开皮肤科的药物，仍然能看到皮肤科规则的告警，但本科室的核心规则排在前面。

### 1.2 科室级审查配置

在 `catalog.json` 中为每个科室新增 `review_config` 字段：

```json
{
  "dept_id": "cardiology",
  "review_config": {
    "default_strict": true,
    "priority_categories": ["drug_interaction", "duplicate_ingredient"],
    "auto_enable_agents": ["clinical_pharmacist", "internal_medicine", "allergy_specialist"],
    "conditional_agents": {
      "specialist": {"always": true}
    },
    "lab_context_defaults": ["INR", "eGFR", "血钾", "QTc", "BNP"],
    "formulary_scope": "cardiology_formulary"
  }
}
```

### 1.3 新增文件

| 文件 | 职责 |
|------|------|
| `src/department/context.py` | `DepartmentContext` 类：加载 review_config、agent 策略、lab 默认值 |
| `src/department/priority.py` | `DepartmentRulePrioritizer`：规则加权排序逻辑 |
| `src/department/formulary.py` | 科室级药典过滤（`formulary_scope` → 过滤院内目录） |

---

## 二、方向二：科室专属智能体专业化

### 2.1 科室专科 Agent（新增 6 个科室专属角色）

当前 `specialist` agent 是唯一的条件激活 agent，但它的 prompt 过于笼统（"你是专科医生（心内/妇产/老年/感染等）"——一个 prompt 覆盖所有专科）。

**方案：拆分为 6 个高频科室专属 agent**，各自有独立的 skill markdown 和激活条件：

| agent_id | 角色 | 激活条件 | 专属 Skill 文件 |
|----------|------|----------|----------------|
| `cardiology_specialist` | 心内专科 | 科室=心内 OR 药物含抗凝/抗心律失常/强心苷 | `heart_failure.md`, `acs_protocol.md`, `anticoag_bridge.md` |
| `neurology_specialist` | 神经专科 | 科室=神内 OR 药物含抗癫痫/帕金森/镇静 | `epilepsy_combo.md`, `parkinson_ddi.md`, `stroke_prevention.md` |
| `oncology_specialist` | 肿瘤专科 | 科室=肿瘤 OR 药物含化疗/靶向/免疫抑制 | `chemo_ddi.md`, `immunosuppress.md`, `antiemetic_combo.md` |
| `pediatrics_specialist` | 儿科专科 | 科室=儿科 OR 年龄<18 | `pediatric_dosing.md`, `growth_impact.md`, `vaccine_interaction.md` |
| `obgyn_specialist` | 妇产专科 | 科室=妇产 OR pregnancy_status≠not_applicable | `teratogen.md`, `lactation_safety.md`, `tocolysis.md` |
| `icu_specialist` | 重症专科 | 科室=ICU OR 药物含血管活性/镇静/肌松 | `vasoactive.md`, `sedation_protocol.md`, `crRT_adjustment.md` |

### 2.2 现有 Agent Prompt 科室化增强

不新增 agent，但为现有 4 个核心 agent 的 skill markdown 增加科室上下文变量：

**`clinical_pharmacist/ddi_review.md`** 增强：
```markdown
## 科室重点审查
当患者来自 {{department}} 科室时，优先关注以下交互类型：
- {{priority_categories}} 对应的规则
- 科室专属药典范围内的药物优先审查
- {{lab_context_defaults}} 相关检验指标异常时的剂量调整
```

**`internal_medicine/indication_match.md`** 增强：
```markdown
## 科室适应症基线
{{department}} 常见适应证：{{common_indications}}
当候选药物与科室常见适应证不匹配时，标注 off-label 使用并给出文献支持等级。
```

### 2.3 Orchestrator 科室路由

修改 `MultiAgentOrchestrator._active_agents()`：

```python
def _active_agents(self, patient_context, candidate_drugs, department_context=None):
    agents = [self.pharmacist, self.attending, self.allergy, self.pharmacy]
    
    # 通用 specialist（保留）
    if SpecialistAgent.should_activate(patient_context, candidate_drugs):
        agents.append(self.specialist)
    
    # 科室专属 agents
    if department_context:
        for dept_agent in self.department_agents.values():
            if dept_agent.should_activate(patient_context, candidate_drugs, department_context):
                agents.append(dept_agent)
    
    return agents
```

### 2.4 Agent 注册表扩展

`registry.yaml` 新增 `department_agents` 段：

```yaml
department_agents:
  cardiology_specialist:
    agent_name: 心内专科
    role: 心衰多药联合、抗凝桥接、抗心律失常审查
    activate_when:
      departments: [cardiology]
      drug_classes: [anticoagulant, antiarrhythmic, cardiac_glycoside, antiplatelet]
    skills: [base, heart_failure, acs_protocol, anticoag_bridge]
    debate: true
    default_enabled: false

  # ... 其余 5 个科室 agent
```

---

## 三、方向三：科室前端工作台

### 3.1 科室仪表盘（DepartmentDashboardView）

**路由**：`/department`（登录后默认首页，替代当前 HomeView）

**布局（三区域）**：

| 区域 | 内容 |
|------|------|
| 顶部统计条 | 本科室今日审查数 / 告警数 / override 数 / 待审队列长度 |
| 左侧快捷入口 | 科室专属快捷按钮（"本科室 CPOE 审查"、"本科室病例库"、"本科室常用药"） |
| 右侧科室信息 | 科室介绍、核心药典（前 20 种常用药）、常见 DDI 警示（Top 5 高频告警） |

### 3.2 科室 CPOE 审查增强

在 `CpoeReviewView.vue` 中增加科室上下文：

- **自动填充科室**：从用户 profile 获取 `dept_id`，注入到 CPOE request 中
- **科室常用药面板**：右侧新增"本科室常用药"快捷选择面板（从 `formulary_scope` 过滤）
- **科室特有风险提示**：审查结果顶部新增"科室关注"区域，高亮本科室 priority_categories 的告警
- **检验指标预设**：根据 `lab_context_defaults` 自动展示相关检验值输入框

### 3.3 科室病例库增强

`CasesView.vue` 增加科室过滤：

- 顶部科室标签栏（Tag filter）：All | 本科室 | 其他科室
- 每个 case card 显示科室标签
- 科室默认过滤到本科室 case

### 3.4 科室 Agent 面板增强

`AgentsView.vue` 增加科室视角：

- 显示本科室激活的 agent 列表（含科室专属 agent 标识）
- 显示每个 agent 的科室专属 skill 文件列表
- 允许用户调整本科室 agent 权重（不影响全局配置）

### 3.5 新增前端文件

| 文件 | 行数预估 | 职责 |
|------|----------|------|
| `views/DepartmentDashboardView.vue` | ~300 | 科室仪表盘 |
| `components/department/DeptDrugPanel.vue` | ~120 | 科室常用药快捷选择面板 |
| `components/department/DeptStatsBar.vue` | ~80 | 科室统计条 |
| `components/department/DeptPriorityAlerts.vue` | ~100 | 科室关注告警高亮区域 |

---

## 四、方向四：知识库科室补全

### 4.1 14 个零规则科室补全

| 科室 | 需补充的核心规则 | 预期数量 |
|------|------------------|----------|
| 呼吸科 | 茶碱+CYP1A2 抑制剂、ICS+强 CYP3A4 抑制剂、抗结核药交互、氧疗+百草枯 | 20+ |
| 肿瘤科 | 化疗药+CYP 抑制剂/诱导剂、靶向药 DDI、止吐药联合、G-CSF 时机 | 25+ |
| 急诊科 | 解毒剂组合（纳洛酮/氟马西尼/NAC）、中毒处理、急性过敏 | 15+ |
| 儿科 | 年龄分级剂量（已有 population rules，缺 DDI 的儿科特异性） | 15+ |
| 骨科 | NSAIDs+骨愈合、抗凝+手术时机、镇痛阶梯 | 10+ |
| 泌尿外科 | 抗胆碱能+尿路、5α还原酶抑制剂、膀胱灌注药 | 8+ |
| 麻醉科 | 麻醉药+CYP 底物、肌松药拮抗、恶性高热触发药 | 15+ |
| 妇产科 | 宫缩剂交互、促排卵药、妊娠期安全替代方案 | 12+ |
| 神经外科 | 抗癫痫+围术期、脑水肿脱水药、颅内压管理 | 10+ |
| 皮肤科 | 光敏性药物组合、免疫抑制剂+UV、维A酸类 | 10+ |
| 眼科 | 局部+全身β阻滞剂叠加、抗青光眼药+心血管、散瞳药 | 8+ |
| 耳鼻喉科 | 减充血剂+高血压、抗组胺+CNS 抑制 | 6+ |
| 康复科 | 肌松药+CNS 抑制、抗痉挛药阶梯 | 6+ |
| 放射科 | 造影剂+肾功能（已有，需增强）、碘过敏替代 | 5+ |

**总计预期新增：~170 条科室 DDI 规则**

### 4.2 科室级药典定义

为每个科室在 `catalog.json` 中定义 `core_formulary`（科室核心药典，20-50 种常用药）：

```json
{
  "dept_id": "cardiology",
  "core_formulary": [
    "warfarin", "rivaroxaban", "apixaban", "dabigatran",
    "metoprolol", "bisoprolol", "carvedilol",
    "lisinopril", "enalapril", "valsartan", "losartan",
    "atorvastatin", "rosuvastatin",
    "amiodarone", "sotalol", "dronedarone",
    "digoxin", "furosemide", "spironolactone",
    "aspirin", "clopidogrel", "ticagrelor",
    "nitroglycerin", "isosorbide",
    "sildenafil"
  ]
}
```

**用途**：
- 科室仪表盘"常用药"面板数据来源
- CPOE 审查时科室药典内药物优先显示
- 科室 case 生成的候选药物池

### 4.3 KG v2 科室条件节点扩充

当前仅 9 个 Condition 节点。需扩充到科室相关病种：

| 新增 Condition 节点 | 关联科室 |
|---------------------|----------|
| 心力衰竭 | 心内科 |
| 急性冠脉综合征 | 心内科 |
| 慢性肾病(CKD) | 肾内科 |
| 癫痫 | 神经内科 |
| 帕金森病 | 神经内科 |
| 类风湿关节炎 | 风湿免疫科 |
| 系统性红斑狼疮 | 风湿免疫科 |
| 急性白血病 | 血液科 |
| 肝硬化 | 消化内科 |
| 炎症性肠病 | 消化内科 |
| 败血症 | 感染科/ICU |
| HIV/AIDS | 感染科 |
| 抑郁症 | 精神科 |
| 精神分裂症 | 精神科 |
| 甲状腺功能亢进 | 内分泌科 |
| 骨质疏松 | 内分泌科/骨科 |
| 前列腺增生 | 泌尿外科 |
| 青光眼 | 眼科 |
| 银屑病 | 皮肤科 |

**预期新增 Condition 节点：25+**

---

## 五、方向五：临床级 Benchmark 升级

### 5.1 从"规则触发测试"到"临床场景测试"

当前 175 个 case 的问题：
- 每个 case 只测试一条规则的触发
- 患者上下文极简（单药 + 单候选）
- 诊断是占位符标签，不是真实 ICD 编码
- 无多规则交互场景
- 无阴性测试（应该通过的处方）

### 5.2 手工精编临床场景（每科室 3-5 个复杂 case）

**示例：心内科复杂场景**

```json
{
  "case_id": "clinical_cardio_polypharmacy_01",
  "department": "cardiology",
  "description": "72岁男性，心衰+房颤+CKD3期，当前用药：地高辛0.125mg+呋塞米40mg+华法林3mg+螺内酯20mg，新增胺碘酮200mg",
  "difficulty": "expert",
  "request": {
    "patient_context": {
      "age": 72, "gender": "M", "egfr": 42,
      "diagnoses": [
        {"icd9_code": "428.0", "name": "Congestive heart failure"},
        {"icd9_code": "427.31", "name": "Atrial fibrillation"},
        {"icd9_code": "585.3", "name": "CKD stage 3"}
      ],
      "current_medications": [
        {"name": "digoxin", "dose": "0.125mg"},
        {"name": "furosemide", "dose": "40mg"},
        {"name": "warfarin", "dose": "3mg"},
        {"name": "spironolactone", "dose": "20mg"}
      ]
    },
    "candidate_drugs": [
      {"name": "amiodarone", "dose": "200mg"}
    ]
  },
  "ground_truth": {
    "risk_level": "high",
    "block_decision": true,
    "required_alerts": [
      {"rule_id": "ddi_digoxin_amiodarone", "category": "drug_interaction"},
      {"rule_id": "ddi_warfarin_amiodarone", "category": "drug_interaction"},
      {"rule_id": "ddi_acei_spironolactone", "category": "drug_interaction"},
      {"rule_id": "pop_elderly_digoxin_beers", "category": "special_population"},
      {"rule_id": "pop_renal_digoxin", "category": "special_population"}
    ],
    "expected_department_boost": "cardiology",
    "expected_overridable": false
  }
}
```

**预期**：28 科室 × 3-5 个复杂 case = 84-140 个手工精编 case

### 5.3 阴性测试集

新增 30 个"应该通过"的安全处方场景：
- 正确的抗凝桥接方案
- 安全的降压药联合
- 合理的降糖阶梯
- 标准抗感染方案

---

## 六、实施路线图

```
Phase 1: 科室感知审查引擎（1.5 周）
├── DepartmentContext + review_config 加载
├── ReviewEngine 接收 department 参数
├── SafetyKnowledgeBase 规则加权排序
└── CpoeMedicationReviewRequest +department 字段

Phase 2: 科室专属 Agent（2 周）
├── 6 个科室专属 agent 编写（prompt + skill markdown）
├── Orchestrator 科室路由改造
├── 现有 4 agent prompt 科室变量注入
└── registry.yaml 扩展

Phase 3: 科室前端工作台（1.5 周）
├── DepartmentDashboardView
├── CpoeReviewView 科室增强
├── CasesView 科室过滤
└── AgentsView 科室视角

Phase 4: 知识库科室补全（2 周）
├── 14 个零规则科室补全（~170 条规则）
├── 28 科室 core_formulary 定义
├── KG v2 新增 25+ Condition 节点
└── KB 合并 → v5.0

Phase 5: 临床级 Benchmark（1 周）
├── 84-140 个手工精编复杂场景
├── 30 个阴性测试
├── 科室感知评估指标（department_boost_accuracy）
└── 验证报告 v5
```

**总预估：8 周（Phase 1+4 并行 → 6 周，Phase 2+3 并行 → 可进一步压缩到 5 周）**

---

## 七、对现有代码的影响

| 文件 | 影响 | 说明 |
|------|------|------|
| `src/knowledge_base.py` | **小改动** | +department 参数、规则加权排序 |
| `src/review_engine.py` | **小改动** | +department 参数传递 |
| `src/orchestrator.py` | **中改动** | +科室路由逻辑、department_agents 加载 |
| `src/debate/debate_engine.py` | **零改动** | 接收 agents 列表不变 |
| `src/schemas.py` | **小改动** | CpoeMedicationReviewRequest +department |
| `src/drug_catalog/review_facade.py` | **小改动** | 传入 department context |
| `src/app.py` | **小改动** | +科室 API 端点、department context 注入 |
| `data/departments/catalog.json` | **大改动** | +review_config + core_formulary |
| `data/agents/registry.yaml` | **中改动** | +department_agents 段 |
| `data/agents/*/` | **新增** | 6 个科室 agent skill markdown 目录 |
| `frontend/src/views/` | **新增+改动** | +DepartmentDashboardView、CpoeReviewView 增强 |
| `frontend/src/api/medsafe.ts` | **小改动** | +department API |

**核心原则：Phase 1 的改动是向后兼容的——department 参数可选，不传时行为与 Stage 10 完全一致。**

---

## 八、一句话总结

Stage 11 将 MedSafe 从"一个审查引擎服务全院"升级为"28 科室各有专属规则优先级、专属 Agent、专属前端工作台"的科室级智能审查系统——规则加权不隐藏、Agent 按科室激活、前端按科室定制，填补从"规则仓库"到"科室级临床伙伴"的最后一公里。
