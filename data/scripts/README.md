# Data processing scripts

Dataset files live under `datasets/` at the project root.  
This folder holds **ETL / fetch / build** scripts only.

## Common commands

```bash
# Download demo imaging + clinical samples
python data/scripts/fetch_demo_datasets.py --chest-ct --kits-cases 8 --monai-samples --nlmcxr-map 50

# Rebuild CXR manifest after adding images
python data/scripts/build_mimic_cxr_manifest.py

# Validate imaging + MIMIC layout
python data/scripts/validate_mimic_data.py
```

Legacy entry points under `scripts/` forward here for backward compatibility.
