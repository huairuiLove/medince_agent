#!/usr/bin/env python3
"""Fetch small public imaging samples for local lesion-segmentation demo."""
from __future__ import annotations

import argparse
import shutil
import sys
import tarfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils import ensure_dir

# NIH Open-I public CXR samples (MIMIC-CXR-style directory layout)
BRATS_SAMPLE_ZIP = (
    "https://github.com/Project-MONAI/tutorials/releases/download/0.9.0/"
    "brats2018_validation_case001.tar.gz"
)
BRATS_FALLBACK_FILES = [
    (
        "https://github.com/Project-MONAI/MONAI-extra-test-data/releases/download/0.8.1/"
        "BraTS2018_2018-01-01_4134567_t1ce.nii.gz",
        "t1c",
    ),
]


def download_file(url: str, dest: Path) -> None:
    ensure_dir(dest.parent)
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"  exists -> {dest}")
        return
    print(f"  downloading {url[:80]}...")
    headers = {"User-Agent": "MedSafe/1.0 (research demo; +https://github.com)"}
    with httpx.Client(timeout=120.0, follow_redirects=True, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)


def fetch_cxr_samples(force: bool = False) -> int:
    count = 0
    base = ROOT / "data" / "mimic_cxr"
    samples = [
        ("p10000980", "s54577367", "00000001.png",
         "https://openi.nlm.nih.gov/imgs/collections/NLMCXR/NLMCXR0001_0001.png"),
        ("p10000980", "s54577367", "00000002.png",
         "https://openi.nlm.nih.gov/imgs/collections/NLMCXR/NLMCXR0002_0001.png"),
    ]
    for patient_id, study_id, filename, url in samples:
        out = base / patient_id / study_id / filename
        if force and out.exists():
            out.unlink()
        if not out.exists() or out.stat().st_size < 1000:
            try:
                download_file(url, out)
            except Exception as exc:
                print(f"  skip {filename}: {exc}")
                continue
        if out.exists() and out.stat().st_size > 1000:
            count += 1
            print(f"  CXR -> {out.relative_to(ROOT)}")
    return count


def fetch_brats_sample(force: bool = False) -> int:
    case_dir = ROOT / "data" / "brats2024" / "BraTS2024_001"
    if not force and any(case_dir.glob("*t1c*.nii.gz")):
        print(f"  BraTS case already present -> {case_dir}")
        return 1

    ensure_dir(case_dir)
    cache = ROOT / "data" / "imaging_cache" / "downloads"
    ensure_dir(cache)

    # Try MONAI tutorials release (single validation case tarball)
    tar_path = cache / "brats2018_validation_case001.tar.gz"
    try:
        if force and tar_path.exists():
            tar_path.unlink()
        if not tar_path.exists():
            download_file(BRATS_SAMPLE_ZIP, tar_path)
        if tar_path.exists():
            import tarfile
            with tarfile.open(tar_path, "r:gz") as tf:
                tf.extractall(path=cache / "brats_extract")
            extracted = cache / "brats_extract"
            nii_files = list(extracted.rglob("*.nii.gz"))
            for src in nii_files:
                name = src.name.lower()
                if "seg" in name:
                    continue
                suffix = None
                for tag in ("t1ce", "t1c", "t1n", "t2w", "t2f", "flair"):
                    if tag in name:
                        suffix = "t1c" if tag in ("t1ce", "t1c") else (
                            "t1n" if tag == "t1n" else (
                                "t2w" if tag == "t2w" else "t2f"
                            )
                        )
                        break
                if suffix:
                    dest = case_dir / f"BraTS2024_001-{suffix}.nii.gz"
                    shutil.copy2(src, dest)
                    print(f"  BraTS -> {dest.relative_to(ROOT)}")
            if any(case_dir.glob("*t1c*.nii.gz")):
                return 1
    except Exception as exc:
        print(f"  BraTS tarball skipped: {exc}")

    print("  BraTS: place 4 modalities manually under data/brats2024/{case_id}/")
    print("  Expected: *t1c*.nii.gz *t1n*.nii.gz *t2w*.nii.gz *t2f*.nii.gz")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch demo CXR / BraTS imaging samples")
    parser.add_argument("--cxr", action="store_true", help="Download sample MIMIC-CXR-style JPG/PNG")
    parser.add_argument("--brats", action="store_true", help="Download sample BraTS 4-modality case")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run_all = args.all or not (args.cxr or args.brats)

    print("=== Imaging sample fetch ===")
    cxr_n = fetch_cxr_samples(force=args.force) if (run_all or args.cxr) else 0
    brats_n = fetch_brats_sample(force=args.force) if (run_all or args.brats) else 0
    print(f"\nDone: {cxr_n} CXR image(s), {brats_n} BraTS case(s).")
    if cxr_n:
        print("  Scan: GET /api/v1/imaging/studies  (source=mimic_cxr)")
    if brats_n:
        print("  Scan: GET /api/v1/imaging/studies  (source=brats2024)")


if __name__ == "__main__":
    main()
