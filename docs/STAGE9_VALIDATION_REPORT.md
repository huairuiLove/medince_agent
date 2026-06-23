# Stage 9 验证报告

> 生成时间：2026-06-22 17:58 UTC  
> 知识库：`hospital_production_v4.json`  
> Benchmark 报告目录：`data/benchmark/reports/`

## 1. 知识库终态

| 指标 | 数值 |
|------|------|
| interaction_rules | 39679 |
| population_rules | 103 |
| allergy_rules | 21 |
| scenario_rules | 4 |
| duplicate_rules | 449 |
| TWOSIDES 新增 DDI | 38702 |
| TWOSIDES 升级已有对 | 578 |
| TWOSIDES 原始信号 | 39280 |
| TWOSIDES CSV 行数 | 42,920,391 |

## 2. Drug KG v2

- 节点：772（Condition=9, Drug=519, DrugClass=219, Enzyme=8, Food=5, LabTest=4, Population=6, Transporter=2）
- 边：40481（BELONGS_TO_CLASS=510, CONTRAINDICATED_FOR=114, FOOD_INTERACTION=10, INDICATED_FOR=134, INTERACTS_WITH=39698, METABOLIZED_BY=15）
- 扩充来源：/Users/miaohuairui/PyCharmMiscProject/MIMIC_III_LoRA/medince_agent/data/hospital/formulary_demo.csv

## 3. Benchmark — rule-only（110 例 / 13 科室）

报告：`benchmark_rule-only_all_20260622T175459Z.json`

| 指标 | 实测 | 目标 | 结果 |
|------|------|------|------|
| Alert Sensitivity | 1.0000 | 0.90 | PASS |
| Alert Specificity | 1.0000 | 0.95 | PASS |
| Risk Level Accuracy | 1.0000 | 0.85 | PASS |
| Block Decision F1 | 1.0000 | 0.85 | PASS |
| Alert Attribution | 1.0000 | 0.80 | PASS |
| Passed Cases | 110/110 | 110/110 | PASS |

## 4. Benchmark — CPOE 路径

报告：`benchmark_cpoe_all_20260622T175508Z.json`

| 指标 | 实测 | 目标 | 结果 |
|------|------|------|------|
| Alert Sensitivity | 1.0000 | 0.90 | PASS |
| Alert Specificity | 1.0000 | 0.95 | PASS |
| Risk Level Accuracy | 1.0000 | 0.85 | PASS |
| Block Decision F1 | 1.0000 | 0.85 | PASS |
| Alert Attribution | 1.0000 | 0.80 | PASS |
| Passed Cases | 110/110 | 110/110 | PASS |

## 5. 知识库版本对比（expanded_mined_v1 → hospital_production_v4）

报告：`benchmark_compare_all_20260622T175539Z.json`

| KB | Sensitivity | Risk Acc | Block F1 | Passed |
|----|-------------|----------|----------|--------|
| expanded_mined_v1 | 0.0818 | 0.1545 | 0.6420 | 9/110 |
| hospital_production_v4 | 1.0000 | 1.0000 | 1.0000 | 110/110 |

### v4 分科室通过率

| Department | Cases | Sensitivity | Risk Acc | Block F1 | Passed |
|------------|-------|-------------|----------|----------|--------|
| cardiology | 15 | 1.00 | 1.00 | 1.00 | 15/15 |
| endocrinology | 10 | 1.00 | 1.00 | 1.00 | 10/10 |
| gastroenterology | 8 | 1.00 | 1.00 | 1.00 | 8/8 |
| geriatrics | 6 | 1.00 | 1.00 | 1.00 | 6/6 |
| hematology | 8 | 1.00 | 1.00 | 1.00 | 8/8 |
| icu | 6 | 1.00 | 1.00 | 1.00 | 6/6 |
| infectious | 8 | 1.00 | 1.00 | 1.00 | 8/8 |
| nephrology | 8 | 1.00 | 1.00 | 1.00 | 8/8 |
| neurology | 12 | 1.00 | 1.00 | 1.00 | 12/12 |
| obgyn | 5 | 1.00 | 1.00 | 1.00 | 5/5 |
| psychiatry | 6 | 1.00 | 1.00 | 1.00 | 6/6 |
| respiratory | 10 | 1.00 | 1.00 | 1.00 | 10/10 |
| rheumatology | 8 | 1.00 | 1.00 | 1.00 | 8/8 |

## 6. 复现命令

```bash
python scripts/import_twosides.py --csv data/TWOSIDES.csv
python scripts/build_stage9_kb.py --import-twosides --twosides-csv data/TWOSIDES.csv
python scripts/generate_benchmark_cases.py
python scripts/run_benchmark.py --mode rule-only --dept all
python scripts/run_benchmark.py --mode cpoe --dept all
python scripts/run_benchmark.py --mode compare --kb-v1 expanded_mined_v1 --kb-v2 hospital_production_v4
python scripts/generate_stage9_validation_report.py
```

## 7. 结论

- Stage 9 知识库 v4 与 TWOSIDES 层已成功合并，Benchmark 110/110 在 rule-only 与 CPOE 模式下全部通过。
- 相对 expanded_mined_v1，v4 将 Alert Sensitivity 从 8.2% 提升至 100.0%。
- full-pipeline 模式需配置 LLM API Key，未配置时显式抛出 `LLMNotConfiguredError`（无 mock 兜底）。

