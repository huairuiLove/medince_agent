# MIMIC-III 完整数据接入指南

MedSafe 将 MIMIC-III Clinical Database 1.4 作为 **真实 EHR 数据源**，经 ETL 转为 `PatientContext` JSON，供会诊、CPOE、规则引擎与（可选）MIMIC-CXR 影像联动使用。

---

## 1. 数据放置

### 临床 CSV（必需）

从 [PhysioNet MIMIC-III](https://physionet.org/content/mimiciii/1.4/) 下载并解压到：

```text
datasets/mimic-iii-clinical-database-1.4/
├── PATIENTS.csv
├── ADMISSIONS.csv
├── PRESCRIPTIONS.csv
├── DIAGNOSES_ICD.csv
├── D_ICD_DIAGNOSES.csv
├── NOTEEVENTS.csv 或 NOTEEVENTS.csv.gz
├── LABEVENTS.csv 或 LABEVENTS.csv.gz
├── ICUSTAYS.csv
└── …
```

`config.yaml` 默认指向该目录：

```yaml
data:
  raw_dir: datasets/mimic-iii-clinical-database-1.4
  processed_dir: datasets/processed
  mimic:
    max_samples: 0              # 0 = 导出全部符合条件的住院
    require_medications: true   # 仅含至少一条医嘱的住院
    include_labs: true          # 合并 LABEVENTS（肌酐/eGFR/钾/INR 等）
    include_icu: true           # 标记 ICUSTAYS
    include_imaging: true       # 标记本地是否有 MIMIC-CXR-JPG
    skip_notes: false           # 解析 NOTEEVENTS 出院小结
```

### 胸片影像（可选）

[MIMIC-CXR-JPG](https://physionet.org/content/mimic-cxr-jpg/2.1.0/) 按官方目录解压到：

```text
datasets/mimic/p10000980/s53189527/*.jpg
datasets/mimic/p10000980/s53189527/s53189527.txt
```

然后重建 manifest：

```bash
python scripts/build_mimic_cxr_manifest.py
```

---

## 2. 构建 processed 索引

```bash
source .venv/bin/activate

# 验证原始表
python scripts/validate_mimic_data.py

# 全量构建（约 3–4 万条含药住院，含 NOTEEVENTS + LABEVENTS，耗时 30–90 分钟）
python -m src.cli build-mimic --max-samples 0

# 快速抽样（开发/CI）
python -m src.cli build-mimic --max-samples 500

# 跳过笔记（更快，无 chief complaint）
python -m src.cli build-mimic --max-samples 0 --skip-notes

# 跳过实验室
python -m src.cli build-mimic --max-samples 0 --no-labs
```

输出：`datasets/processed/mimiciii_patient_contexts.json`

每条记录包含：

| 字段 | 来源表 |
|------|--------|
| 人口学、年龄 | PATIENTS + ADMISSIONS |
| 诊断 | DIAGNOSES_ICD + D_ICD_DIAGNOSES |
| 当前用药 | PRESCRIPTIONS |
| 主诉/HPI/过敏/PMH | NOTEEVENTS（出院小结） |
| `labs` / `egfr` | LABEVENTS（肌酐等 → MDRD eGFR） |
| `icu_stay` | ICUSTAYS |
| `has_imaging` | 本地 MIMIC-CXR-JPG 目录 |

---

## 3. API 使用

| 接口 | 说明 |
|------|------|
| `GET /api/v1/mimic/stats` | 原始表/ processed 统计 |
| `GET /api/v1/mimic/patients?q=&icu_only=&has_imaging=` | 分页检索 |
| `GET /api/v1/mimic/patients/{subject_id}/{hadm_id}` | 完整 PatientContext |
| `GET /api/v1/mimic/patients/{subject_id}/{hadm_id}/imaging` | 关联胸片 study 列表 |

---

## 4. 前端

- **会诊页** `/consult`：顶部 **「MIMIC-III 真实病例」** 面板，点击住院记录自动填充结构化表单
- **影像页** `/imaging?patient=p10000980`：从会诊跳转至对应胸片

---

## 5. 与规则引擎的关系

构建时写入的 `egfr`、`pregnancy_status`、过敏与用药列表会直接参与：

- `ReviewEngine` 人群规则（肾剂量、妊娠禁忌等）
- CPOE `ReviewFacade`
- 多智能体会诊 Extract 跳过（已结构化时）

---

## 6. 常见问题

**构建很慢**  
NOTEEVENTS (~3.7GB) 与 LABEVENTS (~1.7GB) 需流式读取；首次全量构建正常。可用 `--max-samples 1000` 先验证。

**processed 只有 2000 条**  
旧默认 cap；请运行 `build-mimic --max-samples 0` 或确认 `config.yaml` → `data.mimic.max_samples: 0`。

**会诊看不到 MIMIC 面板**  
确认 `datasets/processed/mimiciii_patient_contexts.json` 存在且 `/api/v1/mimic/stats` 返回 `processed_available: true`。

**胸片 has_imaging=false**  
仅当 `datasets/mimic/p{subject_id:08d}/` 下有 study 目录时为 true；需单独下载 MIMIC-CXR-JPG。

---

## 7. 相关文件

| 文件 | 作用 |
|------|------|
| `src/build_mimic_samples.py` | ETL 主逻辑 |
| `src/mimic_store.py` | 运行时查询 |
| `src/mimic_io.py` | CSV/GZ 解析、eGFR 计算 |
| `scripts/validate_mimic_data.py` | 数据校验 |
| `scripts/generate_demo_data.py` | 演示 fixture + 小规模 build |
