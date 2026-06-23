# Stage 11 Validation Report

> Generated: 2026-06-23T06:20:54.292482+00:00

## Knowledge Base (hospital_production_v5)

- Total interaction rules: **1115**
- Stage 11 department DDI rules: **170**

## Benchmark Cases

- Stage 11 clinical cases: **104**
- Stage 11 negative tests: **30**
- Total benchmark JSON files: **309**

## Latest rule-only Benchmark

- Alert sensitivity: 1.0
- Risk level accuracy: 1.0
- Department boost accuracy: 1.0
- Failed cases: 0

## Commands

```bash
python scripts/build_stage11_kb.py --without-twosides
python scripts/generate_stage11_clinical_benchmark.py --auto-per-dept 4
python scripts/run_benchmark.py --mode rule-only --dept all --kb hospital_production_v5
```
