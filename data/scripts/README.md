# Deprecated location

ETL / fetch / build scripts live under **`scripts/`** at the project root.

Dataset files live under **`datasets/`**. Runtime artifacts (SQLite, cache) stay under **`data/`**.

## Common commands

```bash
# Download demo imaging + clinical samples
python scripts/fetch_demo_datasets.py --chest-ct --kits-cases 8 --monai-samples --nlmcxr-map 50

# Rebuild CXR manifest after adding images
python scripts/build_mimic_cxr_manifest.py

# Validate imaging + MIMIC layout
python scripts/validate_mimic_data.py
```

The duplicate copies that previously lived in `data/scripts/` were removed in Stage 10.
