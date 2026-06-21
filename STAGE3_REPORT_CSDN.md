# 第三阶段汇报：规则引擎 Review / Clarify 骨架

> **阶段目标**：构建确定性用药安全审查与信息补全能力。  
> **承接**：Stage 2 Extract 产出 PatientContext，Stage 3 做安全审查。  
> **原第四阶段联调**：42/42 测试通过（2026-05-02）  
> **报告更新**：2026-06-21

---

## 一、阶段定位

Stage 3 是 MedSafe 的**安全硬底线**——无论后续用本地 LoRA 还是 API 多智能体，规则引擎必须先跑。

```
PatientContext + candidate_drugs
  → ReviewEngine（规则匹配）
  → ClarifyEngine（追问 / 保守降级）
  → CaseStore（JSON 持久化）
```

---

## 二、核心模块（延续初版 Stage 3 设计）

| 模块 | 文件 | 职责 |
|------|------|------|
| 规则库 | `minimal_drug_safety_rules.json` | 12 条规则，4 类 |
| 知识库 | `knowledge_base.py` | 13 种药名别名归一化 |
| 审查引擎 | `review_engine.py` | DDI/过敏/妊娠/重复 |
| 追问引擎 | `clarify_engine.py` | 7 类字段模板追问 |
| Case Log | `case_store.py` | 事件链持久化 |

---

## 三、规则覆盖

1. **DDI**：warfarin+aspirin、warfarin+ibuprofen、heparin+warfarin、clarithromycin+simvastatin
2. **重复成分**：acetaminophen/paracetamol
3. **妊娠禁忌**：pregnant + lisinopril/losartan
4. **过敏**：penicillin allergy + amoxicillin

---

## 四、API 接口

| 接口 | 说明 |
|------|------|
| `POST /api/v1/review` | 规则审查 |
| `POST /api/v1/clarify` | 追问 / 保守降级 |
| `POST /api/v1/consult` | 规则-only 全流程（兼容） |

---

## 五、历史联调记录（原 Stage 4 任务 C~F）

2026-05-02 完成的 42 项集成测试（规则引擎专项）：

```
测试总数:  42
通过数量:  42
通过率:    100.0%
```

代表性 case：

| Case | 场景 | 预期 |
|------|------|------|
| review_case_01 | warfarin + ibuprofen | high + block |
| review_case_02 | 过敏史缺失 + amoxicillin | need_clarify |
| review_case_03 | 妊娠未知 + lisinopril | pregnancy clarify |
| clarify_case_02 | unable_to_answer | conservative_fallback |

---

## 六、现版联调（v2 测试套件）

| 测试项 | 结果 |
|--------|------|
| S3-C1~C3 规则审查 | PASS |
| S3-D1~D2 Clarify | PASS |

---

## 七、Vue 前端「规则审查」页

`frontend/src/views/RuleReviewView.vue` 直接调用 `/api/v1/review`，可视化：

- 风险等级 Badge
- 规则 evidence 列表
- clarification targets

---

## 八、与 Stage 4 衔接

- 规则输出 `ReviewOutput.evidence` 注入所有 LLM Agent
- `rule_strict=true` 时 high 风险不可被 LLM 覆盖
- Stage 4 新增 events：`rule_gate`

---

## 九、一句话总结

Stage 3 的规则引擎是初版 Stage 4 联调验证的核心成果；现版继续作为多智能体系统的 Layer 1 守门层，并在 Vue 前端独立展示。
