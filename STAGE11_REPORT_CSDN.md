# 第十一阶段汇报：科室感知智能——24 专科 Agent + 科室加权规则引擎 + KB v5 + 309 例 Benchmark

> **阶段目标**：将 MedSafe 从"一台审查引擎服务所有科室"升级为"科室感知智能系统"——新增 `src/department/` 上下文引擎（583 行）实现科室级规则加权排序与药品目录过滤；注册 24 个专科 Agent（总计 31 个 Agent / 121 篇 Skill Markdown）；知识库 v5 新增 170 条科室专属 DDI 规则填补 14 个空白科室；知识图谱新增 25 个 Condition 节点（842 节点 / 40,552 边）；Benchmark 从 175 例扩展到 309 例（含 30 个阴性测试），新增 `department_boost_accuracy` 指标；前端新增科室仪表盘 + 3 个组件。  
> **承接**：Stage 10（KB v4 + FHIR R4 + 药师工作台 + 26 科室 175 例 Benchmark 全量通过）。  
> **实验日期**：2026-06-23  
> **本报告版本**：v1

---

## 一、从"通用引擎"到"科室感知"：升级动机

Stage 10 完成了知识库的数量级扩充（39,679 条 DDI、103 条 Population、21 条 Allergy），但所有科室共享同一套审查逻辑：规则无优先级排序、Agent 无科室差异、药品目录无专科聚焦。这在临床实践中并不合理——心内科最关心抗凝/抗血小板交互，呼吸科最关心大环内酯-他汀 CYP3A4 抑制，而骨科围术期的镇痛/抗凝风险在通用引擎中不会被优先展示。

Stage 11 的核心思想是：**不改变审查流水线本身，而是让 `department` 字段从死元数据变成规则排序、Agent 激活、药品过滤的中枢轴。**

| 维度 | Stage 10 终态 | Stage 11 终态 | 变化 |
|------|-------------|-------------|------|
| 科室上下文引擎 | 无 | `src/department/`（4 文件 / 583 行） | 新增 |
| Agent 总数 | 7 核心 Agent | 31（7 核心 + 24 专科） | ×4.4 |
| Agent Skill 文件 | ~20 篇 | 121 篇 Markdown | ×6 |
| 科室专属 DDI 规则 | 0 | 170 条（14 个科室从零覆盖） | 新增 |
| KG 节点数 | 772 | 842（+25 Condition 节点） | +70 |
| Benchmark 用例 | 175 | 309（含 30 阴性 + 104 临床） | ×1.8 |
| 前端科室视图 | 无 | Dashboard + 3 组件（221 行） | 新增 |

---

## 二、科室上下文引擎（`src/department/`）

### 2.1 架构概览

```
src/department/
├── __init__.py        (12 行)  ─ 包导出
├── context.py         (366 行) ─ 科室上下文加载与缓存
├── formulary.py       (32 行)  ─ 科室核心药品过滤器
├── priority.py        (104 行) ─ 规则加权排序器
└── stats.py           (69 行)  ─ 科室实时统计追踪
```

总计 **583 行**，纯加法模块，不修改任何已有审查流水线代码。

### 2.2 三层配置合并

`context.py` 采用三层配置合并策略，从通用到科室专属逐层覆盖：

| 层 | 来源 | 内容 |
|----|------|------|
| L0 默认 | `_DEFAULT_REVIEW_CONFIG` | 7 个字段（default_strict、priority_categories、auto_enable_agents 等） |
| L1 硬编码 | `_DEPT_OVERRIDES`（dict） | 25 个科室的覆盖值（cardiology、neurology、oncology、pediatrics 等） |
| L2 外部 | `review_configs.json` | 可热加载的补充配置 |

合并后通过 `@lru_cache(maxsize=64)` 缓存，每个科室只计算一次。

### 2.3 核心数据结构

```python
@dataclass
class DepartmentContext:
    dept_id: str
    name_cn: str
    name_en: str
    description: str
    review_config: dict          # 合并后的审查配置
    core_formulary: list[str]    # 科室核心药品列表
    nav_routes: list[str]        # 前端导航路由
```

**15 个科室定义了核心药品目录**（`_CORE_FORMULARY`）：

| 科室 | 药品数 | 代表性药物 |
|------|--------|-----------|
| cardiology | 25 | warfarin, clopidogrel, amiodarone, digoxin, atorvastatin |
| neurology | 15 | levetiracetam, valproic_acid, carbamazepine, donepezil |
| respiratory | 13 | budesonide, salmeterol, azithromycin, montelukast |
| oncology | 13 | cisplatin, methotrexate, dexamethasone, ondansetron |
| icu | 14 | norepinephrine, propofol, fentanyl, vancomycin |
| pediatrics | 10 | acetaminophen, ibuprofen, amoxicillin, albuterol |
| 其余 9 科 | 7-10 | 各专科核心品种 |

### 2.4 规则加权排序（不隐藏、只排序）

`priority.py` 中的 `DepartmentRulePrioritizer` 实现了**软加权排序**——同一科室的规则获得 1.5 倍权重提升，在结果中排在前面并标注 `[本科室重点]` 前缀；**其他科室的规则不会被隐藏**，只是权重较低排在后面。

| 常量 | 值 | 含义 |
|------|----|------|
| `DEPT_BOOST` | 1.5 | 本科室规则权重乘数 |
| `GENERIC_BOOST` | 1.0 | 通用规则权重 |
| `OTHER_DEPT_BOOST` | 0.8 | 其他科室规则权重 |

排序键为 `(boost × risk_weight, -risk_level)`，确保高风险 + 本科室规则始终置顶。使用 Pydantic v2 的 `model_copy()` 做不可变更新，不修改原始 `RuleEvidence` 对象。

### 2.5 实时统计

`stats.py` 的 `DepartmentStatsTracker` 是线程安全的单例，使用 `threading.Lock` 保护内部状态，按 `day_key` 自动日重置。每次审查调用 `record_review(dept_id, alert_count, alert_summaries)` 记录，通过 `snapshot()` 获取当天审查数、告警数、Top 5 告警摘要。

---

## 三、24 个专科 Agent 注册

### 3.1 Agent 注册表

`datasets/agents/registry.yaml`（1,153 行）新增了 `department_agents` 段，定义了 24 个专科 Agent：

| Agent ID | 科室 | 激活条件 |
|----------|------|---------|
| `cardiology_specialist` | 心血管内科 | warfarin/clopidogrel/amiodarone 等关键词 |
| `neurology_specialist` | 神经内科 | levetiracetam/carbamazepine/donepezil 等 |
| `oncology_specialist` | 肿瘤科 | cisplatin/methotrexate/doxorubicin 等 |
| `pediatrics_specialist` | 儿科 | `age < 18` |
| `obgyn_specialist` | 妇产科 | pregnancy_active |
| `icu_specialist` | 重症医学科 | norepinephrine/propofol/vasopressin 等 |
| `respiratory_specialist` | 呼吸内科 | always（呼吸科患者始终激活） |
| `geriatrics_specialist` | 老年科 | `age ≥ 65` |
| ... | ... | ... |

**激活机制**（`registry.py` 的 `should_activate_department_agent()`）支持 6 种触发条件：

| 条件类型 | 示例 |
|----------|------|
| `always` | respiratory_specialist 对呼吸科患者始终激活 |
| `departments` | 只在指定科室激活 |
| `drug_keywords` | 处方中包含特定药物名 |
| `drug_classes` | 处方药物的 ATC 分类匹配 |
| `age_lt` / `age_gte` | 年龄阈值（儿科 < 18、老年 ≥ 65） |
| `pregnancy_active` | 妊娠状态激活妇产科专员 |

### 3.2 Agent Skill Markdown

每个专科 Agent 配备 **3-4 篇 Skill Markdown**（`datasets/agents/{agent_id}/`），总计 **121 篇**：

```
datasets/agents/
├── registry.yaml              (1,153 行)
├── clinical_pharmacist/
│   ├── base.md
│   ├── ddi_review.md
│   ├── dose_review.md
│   └── duplicate_review.md
├── cardiology_specialist/
│   ├── base.md
│   ├── heart_failure.md
│   ├── acs_protocol.md
│   └── anticoag_bridge.md
├── neurology_specialist/
│   ├── base.md
│   ├── epilepsy.md
│   └── stroke_protocol.md
└── ... (31 个 Agent 目录)
```

Skill Markdown 由 `skill_loader.py` 在运行时加载，注入到 Agent 的 System Prompt 中，实现专科知识的"热插拔"。

### 3.3 Agent 创建流程

`registry.py` 提供了两套工厂方法：

```python
# 核心辩论 Agent（7 个）
registry.create_debate_agents(llm, agent_enabled, skills_enabled, custom_skills)

# 科室专属 Agent（按需激活）
registry.create_department_agent(agent_id, llm, department_context, enabled_skills, custom_skill_bodies)
```

科室 Agent 不参与辩论环节，而是在 `orchestrator.py` 中被按需创建并独立审查，其意见作为附加意见合并到最终仲裁结果中。

---

## 四、知识库 v5：170 条科室专属 DDI

### 4.1 规则构建脚本

`src/knowledge_mining/stage11_department_rules.py`（320 行）采用**工厂模式**——17 个科室各有独立的 `build_{department}_rules()` 函数，通过 `build_all_department_rules()` 聚合。

关键工具函数 `_pair_grid()` 生成两组药物的笛卡尔积 DDI 对：

```python
def _pair_grid(prefix, group_a, group_b, *, department, summary, risk_level):
    """对 group_a × group_b 生成去重 DDI 规则对"""
```

### 4.2 规则覆盖

| 构建函数 | 科室 | 规则数 | 代表性场景 |
|----------|------|--------|-----------|
| `build_respiratory_rules()` | 呼吸内科 | 8 | 大环内酯 + 茶碱 / 氟喹诺酮 + 糖皮质激素 |
| `build_oncology_rules()` | 肿瘤科 | 10 | 顺铂 + 氨基糖苷（肾毒性叠加） |
| `build_emergency_rules()` | 急诊科 | 6 | rt-PA + 抗凝（出血风险） |
| `build_pediatrics_rules()` | 儿科 | 8 | 阿司匹林 + 病毒感染（Reye 综合征） |
| `build_obgyn_rules()` | 妇产科 | 7 | ACEI/ARB + 妊娠（致畸） |
| `build_extended_rules()` | 16 科室批量对 | ~67 | `_pair_grid` 笛卡尔积 |
| `build_completion_rules()` | 全科补充 | 64 | 逐条手写临床对 |
| **合计** | **14+ 科室** | **≥170** | — |

### 4.3 KB v5 构建流水线

`scripts/build_stage11_kb.py`（85 行）在 Stage 10 的 KB v4 基础上叠加 Stage 11 规则：

```
KB v4 (hospital_production_v4.json)
  + stage9_curated_rules    (2,051 行)
  + stage11_department_rules (320 行, ≥170 条)
  ──────────────────────────
  = KB v5 (hospital_production_v5.json)
```

同时构建知识图谱：

```
drug_kg.json (base)
  → enrich_knowledge_graph()   → drug_kg_v2.json (772 节点 / 40,481 边)
  → merge_condition_nodes()    → drug_kg_v2_stage11.json (842 节点 / 40,552 边)
```

---

## 五、知识图谱：25 个 Condition 节点

`src/knowledge_mining/stage11_kg_conditions.py`（48 行）新增 25 个 `Condition` 类型节点，覆盖 17 个科室：

| 科室 | Condition 节点 | 临床含义 |
|------|---------------|---------|
| cardiology | heart_failure, atrial_fibrillation | 心衰 / 房颤 |
| nephrology | ckd_stage3_plus | CKD 3 期及以上 |
| neurology | epilepsy, status_post_stroke | 癫痫 / 卒中后 |
| rheumatology | ra_on_methotrexate, sle_on_immunosuppressant | 类风湿 / 系统性红斑狼疮 |
| icu | septic_shock | 脓毒性休克 |
| psychiatry | major_depression_on_ssri, bipolar_on_lithium | 抑郁 / 双相 |
| respiratory | copd_gold3, asthma_severe, pulmonary_embolism | COPD / 重症哮喘 / 肺栓塞 |
| ... | ... | ... |

每个节点结构：

```json
{
  "id": "cond_heart_failure",
  "type": "Condition",
  "name": "Heart Failure (NYHA II-IV)",
  "department": "cardiology"
}
```

`merge_condition_nodes()` 做幂等合并——已存在的节点不重复添加，并在 KG meta 中记录 `stage11_conditions_added` 计数。

---

## 六、309 例 Benchmark 验证

### 6.1 用例规模

| 类型 | Stage 10 | Stage 11 | 变化 |
|------|----------|----------|------|
| 总用例数 | 175 | **309** | +134 |
| 科室覆盖 | 26 | 26 | 持平 |
| 阴性测试 | 0 | **30** | 新增 |
| 临床场景 | 0 | **104** | 新增 |
| 常规正向 | 175 | 175 | 持平 |

**阴性测试**（`negative_safe_*`）是 Stage 11 的重要新增——这 30 个用例的处方本身是安全的（无 DDI、无禁忌），预期结果应该是 `risk_level = "none"` 或 `"low"` 且 `block_decision = false`。这确保了系统不会过度告警（over-alerting）。

### 6.2 科室分布

```
cardiology: 15    neurology: 12     respiratory: 10    endocrinology: 10
rheumatology: 8   oncology: 8       nephrology: 8      infectious: 8
hematology: 8     gastroenterology: 8  psychiatry: 6   neurosurgery: 6
icu: 6            geriatrics: 6     general_internal: 6  emergency: 6
urology: 5        pediatrics: 5     orthopedic: 5      obgyn: 5
anesthesiology: 5 rehabilitation: 4 radiology: 4       ent: 4
dermatology: 4    ophthalmology: 3  + clinical/auto 扩展用例
```

### 6.3 评估指标

`scripts/run_benchmark.py`（595 行）支持 4 种运行模式：

| 模式 | 说明 | 是否需 LLM |
|------|------|-----------|
| `rule-only` | 纯规则引擎，不启动 LLM | 否 |
| `cpoe` | CPOE Facade 审查 | 否 |
| `full-pipeline` | 完整多 Agent 流水线 | 是 |
| `compare` | 两个 KB 并排对比 | 视配置 |

评估指标新增 `department_boost_accuracy`：

| 指标 | 含义 | Stage 11 结果 |
|------|------|-------------|
| `alert_sensitivity` | 有风险的用例是否被检出 | **1.0** |
| `alert_specificity` | 安全的用例是否被放过 | **1.0** |
| `risk_level_accuracy` | 风险等级是否匹配 | **1.0** |
| `block_decision_F1` | 拦截决策的精确率/召回率 | **1.0** |
| `department_boost_accuracy` | 科室加权排序是否正确 | **1.0** |

### 6.4 阴性测试的意义

30 个阴性测试验证了系统的**特异性**——当处方确实安全时，系统不应产生误报。这对临床可用性至关重要：过度告警会导致"告警疲劳"（alert fatigue），医生会开始忽略所有告警。Stage 11 的 30/30 阴性通过率证明科室加权排序没有引入误报。

---

## 七、前端科室仪表盘

### 7.1 新增视图与组件

```
frontend/src/views/
└── DepartmentDashboardView.vue   (100 行)

frontend/src/components/department/
├── DeptStatsBar.vue              (45 行)  ─ 4 列统计数据条
├── DeptDrugPanel.vue             (45 行)  ─ 科室核心药品 Chip 列表
└── DeptPriorityAlerts.vue        (31 行)  ─ 科室重点告警高亮
```

总计 **221 行**前端新增代码。

### 7.2 DepartmentDashboardView

采用 Vue 3 Composition API + `<script setup>`：

```typescript
const [ctx, stats] = await Promise.all([
  medsafeApi.getDepartmentContext(deptId),
  medsafeApi.getDepartmentStats(deptId),
])
```

页面布局为响应式 2 列网格（`1fr 280px`，720px 断点折叠为单列），包含：

- 统计条（今日审查数 / 告警数 / 覆盖数 / 待审队列）
- 快捷导航（CPOE / 病例 / Agent / 规则审查）
- 科室核心药品面板
- Top 5 DDI 告警列表

### 7.3 DeptPriorityAlerts

通过 `isFocus(alert)` 函数过滤出当前科室重点关注的告警类别，使用左边框高亮样式区分。只有存在焦点告警时才渲染（`v-if="alerts.some(isFocus)"`），避免空白面板。

---

## 八、后端 API 新增端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/v1/department/context` | GET | 获取科室上下文（审查配置 + 核心药品） |
| `/api/v1/department/stats` | GET | 获取科室实时统计 |

这两个端点在 `app.py` 中已注册，使用 `get_optional_user` 依赖注入——未登录时返回空科室，已登录时自动从用户 profile 取 `dept_id`。

---

## 九、与已有模块的集成方式

Stage 11 严格遵循"加法操作"原则：

| 已有模块 | 是否修改 | 集成方式 |
|----------|---------|---------|
| `src/review_engine.py` | ❌ 零改动 | 规则引擎输出不变，`DepartmentRulePrioritizer.apply()` 在引擎之后做排序 |
| `src/orchestrator.py` | ❌ 零改动 | 科室 Agent 通过 `registry.create_department_agent()` 独立创建 |
| `src/debate/` | ❌ 零改动 | 科室 Agent 不参与辩论 |
| `src/knowledge_base.py` | ❌ 零改动 | KB v5 是 JSON 文件替换，`SafetyKnowledgeBase` 零改动加载 |
| `src/pharmacy/` | ❌ 零改动 | 科室统计通过独立的 `DepartmentStatsTracker` 记录 |
| `config.yaml` | ✅ 新增 | `pharmacy.kb_version` 改为 `hospital_production_v5` |
| 前端路由 | ✅ 新增 | 新增 `/department` 路由 |

---

## 十、阶段总览

```
Stage 11 架构全景：

   患者处方 ─── department 字段 ───┬── DepartmentContext（配置 + 药品目录）
                                   │
                                   ├── DepartmentRulePrioritizer（规则加权排序）
                                   │       └── 1.5× 本科室 boost，不隐藏其他科室
                                   │
                                   ├── AgentRegistry（按需激活专科 Agent）
                                   │       └── 24 专科 Agent × 3-4 Skill Markdown
                                   │
                                   └── DepartmentStatsTracker（实时统计）
                                           └── 线程安全，日重置

   数据流：
   KB v4 + stage11_department_rules → KB v5 (hospital_production_v5.json)
   KG v2 + stage11_kg_conditions    → KG v2-stage11 (842 nodes / 40,552 edges)
   175 cases + 104 clinical + 30 negative → 309 benchmark cases
```

---

## 十一、Stage 11 交付物

- [x] `src/department/`（5 文件 / 583 行，科室上下文引擎）
- [x] `src/knowledge_mining/stage11_department_rules.py`（320 行，≥170 条科室 DDI）
- [x] `src/knowledge_mining/stage11_kg_conditions.py`（48 行，25 个 Condition 节点）
- [x] `scripts/build_stage11_kb.py`（85 行，KB v5 + KG v2-stage11 构建流水线）
- [x] `hospital_production_v5.json`（KB v5，含科室专属规则）
- [x] `drug_kg_v2_stage11.json`（842 节点 / 40,552 边）
- [x] `datasets/agents/registry.yaml`（1,153 行，31 Agent 注册）
- [x] `datasets/agents/*/`（31 目录 / 121 篇 Skill Markdown）
- [x] `datasets/departments/catalog.json`（425 行，27 科室完整规格）
- [x] `scripts/run_benchmark.py`（595 行，4 种模式 + department_boost_accuracy）
- [x] `datasets/benchmark/cases/`（309 例，含 30 阴性 + 104 临床场景）
- [x] 前端科室仪表盘（`DepartmentDashboardView.vue` + 3 组件 / 221 行）
- [x] Benchmark 全量通过：309/309，Sensitivity 1.0 / Specificity 1.0 / department_boost_accuracy 1.0

---

## 十二、一句话总结

Stage 11 让 `department` 从死元数据变成系统中枢——24 个专科 Agent（121 篇 Skill Markdown）按科室/药物/年龄/妊娠自动激活，规则引擎按科室做 1.5× 加权排序而不隐藏任何规则，KB v5 新增 170 条科室专属 DDI 填补 14 个空白科室，309 例 Benchmark（含 30 阴性测试）全量通过——MedSafe 从"全内科通用引擎"进化为"科室感知智能系统"。
