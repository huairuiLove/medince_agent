# 第八阶段汇报：院级药库（PIS CSV）+ CPOE 审查 + 演示目录 1120 行

> **阶段目标**：将 MedSafe 从「文本 + 规则 Demo」推进到 **可对接医院药事系统（PIS）的用药审查主链路**——院目录 CSV 导入、术语解析、CPOE 结构化审查 API，并生成 1000+ 行演示 formulary。  
> **承接**：Stage 1~4 用药安全主线 + Stage 5~7 影像链路 + 多轮辩论（`src/debate/`）。  
> **实验日期**：2026-06-21  
> **本报告版本**：v1

---

## 一、承接 Stage 7 与产品重心调整

Stage 7 完成影像 **三维闭环**（MPR + VISTA3D）。Stage 8 将工程重心拉回 **进院主产品**：

| 维度 | Stage 7 终态 | Stage 8 |
|------|-------------|---------|
| 产品重心 | 影像 + 用药并列演示 | **药库 / CPOE 为主**，影像为辅助 |
| 药名解析 | `SafetyKnowledgeBase` 十几种 alias | **院内码 + RxNorm/ATC + 1120 行目录** |
| 审查入口 | 病历文本 `/consult` | **结构化医嘱** `/cpoe/medication-review` |
| 库存/目录 | `pharmacy_formulary.json`（12 条） | **SQLite 院目录 + CSV 同步** |
| 演示数据 | 手工 JSON | **formulary_demo.csv（1120 行）** |

**核心判断**：真实进院时，药学部与信息科首先验收的是 **药库能不能接、医嘱能不能审**，而非分割精度。

---

## 二、问题定义

Stage 8 需回答：

1. 医院 PIS 导出 **CSV** 如何映射为 MedSafe 可查询的院目录？
2. CPOE 开嘱时的输入是 **`hospital_drug_id`**，如何与 DDI 规则层对齐？
3. 没有真实医院 CSV 时，如何用 **公开术语 + 合成目录** 做可演示、可压测的数据集（≥1000 行）？
4. 审查结果如何以 **分级告警**（`hard_stop` / `warning` / `info`）回写 HIS，而非仅返回 Markdown？

---

## 三、院级药库架构

```
PIS / 药事系统 ── nightly CSV ──► scripts/sync_formulary.py
                                        │
                                        ▼
                              SQLite formulary.db
                              ├─ hospital_drugs（主表）
                              ├─ drug_aliases（中英文名/商品名/规格）
                              └─ formulary_sync_log（版本审计）
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
         CatalogAwareKnowledgeBase   PharmacyInventoryAgent   CpoeReviewFacade
         （术语 canonical_key）      （库存/目录内）          （CPOE 审查）
                    │                   │                   │
                    └───────────────────┴───────────────────┘
                                        ▼
                              ReviewEngine + Debate + SafetyPanel
```

| 模块 | 文件 | 职责 |
|------|------|------|
| CSV 导入 | `src/drug_catalog/csv_import.py` | 中英文表头映射、upsert、别名索引 |
| 目录服务 | `src/drug_catalog/catalog_service.py` | 按院内码/药名查询、搜索、统计 |
| 术语层 | `src/drug_catalog/terminology.py` | 院内码 → `canonical_key`（对齐规则库） |
| CPOE 门面 | `src/drug_catalog/review_facade.py` | 统一审查：目录告警 + 临床规则 |
| 同步脚本 | `scripts/sync_formulary.py` | CLI / cron 全量导入 |
| 演示生成 | `scripts/build_demo_formulary.py` | 1120 行 CSV 构建 |

---

## 四、PIS CSV 格式与导入

### 4.1 必填字段

| 列名（中/英） | 说明 |
|---------------|------|
| `hospital_drug_id` / 院内药品码 | CPOE 医嘱主键 |
| `generic_name_cn` / 通用名 | 中文通用名 |
| `generic_name_en` | 英文 INN（DDI 规则对齐） |
| `trade_name_cn` | 商品名 |
| `strength` / `dosage_form` / `route` | 规格、剂型、途径 |
| `in_formulary` / `in_stock` | 目录内 / 库存（1/0 或 是/否） |
| `rxnorm_rxcui` / `atc_code` | 可选，术语映射 |

### 4.2 导入命令

```bash
python scripts/build_demo_formulary.py          # 生成 1120 行演示 CSV
python scripts/sync_formulary.py --csv data/hospital/formulary_demo.csv
```

API 热更新（无需重启）：

```http
POST /api/v1/drug-catalog/sync
{"csv_path": "data/hospital/formulary_demo.csv"}
```

启动时若 DB 为空且 `auto_import_on_startup: true`，自动导入 `config.yaml` 中 `formulary_path`。

---

## 五、演示院目录规模（1120 行）

| 指标 | 数值 |
|------|------|
| CSV 行数 | **1120** |
| 中文通用名 | 1120 |
| 不重复英文成分 | 449 |
| 在库 | 1118 |
| 高警示 | 41 |
| 抗菌药（分级>0） | 176 |

**数据来源构成**：

1. **205 条精选**（`scripts/demo_formulary_data.py`）— 华法林+布洛芬 DDI、缺货、目录外、高警示等演示场景  
2. **~900 条 ATC 模板展开**（`scripts/drug_template_catalog.py`）— 抗血栓、降压、降糖、抗感染、肿瘤、麻醉等 20+ 类，每药 3 规格  
3. RxCUI 对齐 [RxNorm Prescribable](https://www.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html) 概念（离线种子，无需 UMLS 许可）

> 国内 **国家医保药品目录** 为 PDF，无官方 PIS 型 CSV；演示库为 **合成院目录**，对接真实医院时替换 CSV 路径即可。

---

## 六、CPOE 审查 API

### 6.1 请求示例

```json
POST /api/v1/cpoe/medication-review
{
  "encounter_id": "ENC001",
  "patient": {
    "patient_id": "P001",
    "age": 72,
    "gender": "M",
    "allergies": []
  },
  "orders": [
    {"order_id": "O1", "hospital_drug_id": "H-DEMO-00006"}
  ],
  "existing_medications": [
    {"hospital_drug_id": "H-DEMO-00001", "name": "华法林钠 2.5mg"}
  ]
}
```

### 6.2 响应要点

| 字段 | 说明 |
|------|------|
| `overall_status` | `passed` / `warning` / `blocked` |
| `alerts[]` | 含 `alert_level`、`rule_id`、`overridable` |
| `unresolved_drugs` | 未识别药品（须显式告警，禁止 silent pass） |
| `requires_pharmacist_review` | 是否进药师队列 |
| `knowledge_version` | 规则 + 目录 sync 版本 |

### 6.3 告警分级

| 级别 | 典型场景 | 可 override |
|------|----------|-------------|
| `hard_stop` | 高风险 DDI + `rule_strict=true` | 否 |
| `warning` | 缺货、目录外、未识别药、中等风险 | 是（需原因） |
| `info` | 高警示提示 | 是 |

### 6.4 目录层规则 ID

| rule_id | 含义 |
|---------|------|
| `UNRESOLVED_DRUG` | 院内码/药名无法映射 |
| `NOT_IN_FORMULARY` | 不在基本目录 |
| `OUT_OF_STOCK` | 缺货（含 `alternatives` 院内码） |
| `HIGH_ALERT_DRUG` | 高警示药品双人核对提示 |
| `ddi_*` | 临床规则引擎命中 |

---

## 七、与现有流水线打通

| 入口 | 药库集成 |
|------|----------|
| `/api/v1/cpoe/medication-review` | **主入口**，`CpoeReviewFacade` |
| `/api/v1/review` / `/multi-consult` | `ReviewEngine` 注入 `CatalogAwareKnowledgeBase` |
| `PharmacyInventoryAgent` | 查 SQLite 库存/目录，不再读静态 JSON |
| `/api/v1/chat` | Graph RAG 仍用 `drug_kg.json`（解释层）；审查逻辑与 CPOE 共用 ReviewEngine |

**配置**（`config.yaml`）：

```yaml
drug_catalog:
  db_path: "data/hospital/formulary.db"
  formulary_path: "data/hospital/formulary_demo.csv"
  auto_import_on_startup: true

clinical_knowledge:
  version: "minimal_rules_v1"
```

---

## 八、集成测试

`scripts/run_integration_tests.py` 扩展 **Drug Catalog / CPOE** 段（共 **30 项 PASS**）：

| 用例 | 验证点 |
|------|--------|
| catalog: csv import | 样例 CSV upsert |
| catalog: lookup by id | 华法林 `warfarin` canonical |
| catalog: resolve chinese name | 「布洛芬」→ 院内码 |
| cpoe: warfarin+ibuprofen blocked | `overall_status=blocked` |
| cpoe: DDI alert present | `ddi_warfarin_ibuprofen_bleeding` |
| cpoe: out of stock warning | 克拉霉素 `OUT_OF_STOCK` |

---

## 九、八阶段总览

```
Stage 1: 方案设计 + LoRA 规划              ✅
Stage 2: Extract 原型（LoRA→API）            ✅
Stage 3: 规则引擎 review/clarify            ✅
Stage 4: 多智能体 + Vue + Docker            ✅
Stage 5: 临床 UI + 2D 影像分割              ✅
Stage 6: VLM 报告 + 段落 RAG                ✅
Stage 7: 3D MPR + VISTA3D Bundle            ✅
Stage 8: 院级药库 CSV + CPOE 审查           ✅ ← 进院主链路
```

**系统终态架构（Stage 8）**：

```
Vue 前端 (/consult + /imaging + /rule-review + /cases)
  → FastAPI
      ├─ 用药主链路: PIS CSV → 院目录 DB → CPOE Review → 规则 → 辩论 → 仲裁
      ├─ 文本侧:     Extract → Multi-Agent → Clarify
      └─ 影像侧:     Catalog → Segment(2D/3D) → VLM Report → RAG Q&A
```

---

## 十、后续可选（Stage 9+）

1. **TWOSIDES / DrugBank DDI** 扩容确定性规则层（当前仍为 12 条 demo 规则 + KG）
2. **FHIR R4** `MedicationRequest` Bundle 适配（与 CSV 并列）
3. **药师工作台** — `requires_pharmacist_review` 队列 + override 审计
4. **国家医保编码** 批量映射 `insurance_code` 列
5. **肾/eGFR 调量** 规则 + `Observation` 字段

---

## 十一、Stage 8 交付物

- [x] `src/drug_catalog/` 模块（DB / CSV / 术语 / CPOE Facade）
- [x] `POST /api/v1/cpoe/medication-review` 及药库 CRUD API
- [x] `formulary_demo.csv`（1120 行）+ `formulary_sample.csv`（联调样例）
- [x] `scripts/sync_formulary.py` / `build_demo_formulary.py`
- [x] `PharmacyInventoryAgent` 接 SQLite 院目录
- [x] README 院级药库 / CPOE 运行手册
- [x] 集成测试 30/30 PASS
- [x] GitHub 推送（`master` @ `2b8712e`）

---

## 十二、一句话总结

Stage 8 让 MedSafe 具备 **真实医院对接的用药主链路骨架**——PIS CSV 院目录入库、院内码术语解析、CPOE 分级告警 API 与 1120 行可演示 formulary；影像能力保留为辅助，进院验收焦点回归 **药库 + 审查 + 工作流**。
