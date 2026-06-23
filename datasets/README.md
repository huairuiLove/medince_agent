# Datasets

Static and reference data for MedSafe (imaging, knowledge, benchmarks, cases, formulary CSVs).

Runtime artifacts (SQLite DBs, imaging cache) stay under `data/`.

## Layout

| Path | Description |
|------|-------------|
| `mimic/`, `mimic_cxr/` | Chest X-ray samples |
| `chest_ct/`, `kits19/` | CT volumes (lung / kidney) |
| `brats2024/` | Brain MRI (BraTS) |
| `knowledge/` | Rules, KG, INN maps |
| `hospital/` | Formulary CSV sources |
| `cases/`, `case_templates/` | Case logs & templates |
| `benchmark/` | Stage 9 benchmark cases |
| `processed/` | MIMIC-III derived JSON |
| `external/` | Downloaded archives (NLMCXR, MIMIC demo) |

Fetch scripts: `data/scripts/fetch_demo_datasets.py`
