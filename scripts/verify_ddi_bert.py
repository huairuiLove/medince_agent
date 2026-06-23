#!/usr/bin/env python3
"""Smoke-test DDI-BERT: download checkpoint, load model, run SMILES pair inference."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify ltmai/Bio_ClinicalBERT_DDI_finetuned setup")
    parser.add_argument("--download", action="store_true", help="Download model if missing")
    parser.add_argument("--force-download", action="store_true", help="Re-download model weights")
    args = parser.parse_args()

    if args.download or args.force_download:
        cmd = [sys.executable, str(PROJECT_ROOT / "scripts/download_models.py"), "--ddi-bert"]
        if args.force_download:
            cmd.append("--force")
        subprocess.check_call(cmd)

    from src.safety_models.ddi_classifier import get_ddi_classifier, is_ddi_bert_enabled

    if not is_ddi_bert_enabled():
        print("FAIL: safety_models.ddi_bert.enabled is false in config.yaml")
        return 1

    classifier = get_ddi_classifier().require_ready()
    status = classifier.status()
    print("OK: model loaded")
    print(f"  repo: {status['hf_repo']}")
    print(f"  dir:  {status['model_dir']}")
    print(f"  thresholds: high={status['high_threshold']}, medium={status['medium_threshold']}")

    pairs = [
        ("warfarin", "ibuprofen"),
        ("metoprolol", "clopidogrel"),
    ]
    for drug_a, drug_b in pairs:
        result = classifier.predict_pair(drug_a, drug_b)
        if not result:
            print(f"SKIP: {drug_a} + {drug_b} (SMILES unavailable)")
            continue
        print(
            f"  {drug_a} + {drug_b}: prob={result['positive_prob']:.3f} "
            f"risk={result['risk_level']}"
        )

    from src.review_engine import ReviewEngine
    from src.schemas import CandidateDrug, PatientContext

    engine = ReviewEngine()
    out = engine.review(
        PatientContext(
            gender="M",
            age=60,
            current_medications=[{"name": "metoprolol", "dose": "25mg"}],
            allergies=[],
            pregnancy_status="not_applicable",
        ),
        [CandidateDrug(name="clopidogrel", dose="75mg")],
    )
    model_hits = [e for e in out.evidence if e.source == "ddi_bert_model"]
    print(f"OK: ReviewEngine model supplement hits={len(model_hits)}, risk={out.risk_level}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
