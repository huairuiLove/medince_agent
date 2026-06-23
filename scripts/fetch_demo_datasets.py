#!/usr/bin/env python3
"""Download public demo / starter datasets that do not require MIMIC credentialing.

Sources:
  - MIMIC-III Demo (PhysioNet open access, ~13 MB)
  - Open-I NLMCXR chest X-rays (subset → data/mimic_cxr/)
  - KiTS19 imaging via HuggingFace (neheller/KiTS-Challenge-Imaging)
  - MONAI BraTS sample + Open-I CXR (via fetch_imaging_samples)

MIMIC-III full + MIMIC-CXR require separate PhysioNet credentialing (user handles).
"""

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

MIMICIII_DEMO_URL = "https://physionet.org/files/mimiciii-demo/1.4/"
NLMCXR_PNG_TGZ = "https://openi.nlm.nih.gov/imgs/collections/NLMCXR_png.tgz"
NLMCXR_REPORTS_TGZ = "https://openi.nlm.nih.gov/imgs/collections/NLMCXR_reports.tgz"
KITS_HF_BASE = "https://huggingface.co/datasets/neheller/KiTS-Challenge-Imaging/resolve/main"
MONAI_RELEASE = "https://github.com/Project-MONAI/MONAI-extra-test-data/releases/download/0.8.1"
CHEST_CT_SAMPLES = (
    ("copd_insp", f"{MONAI_RELEASE}/copd1_highres_INSP_STD_COPD_img.nii.gz"),
    ("copd_exp", f"{MONAI_RELEASE}/copd1_highres_EXP_STD_COPD_img.nii.gz"),
)

# Known working Open-I direct PNG URLs (NLMCXR collection; many legacy paths return 404)
OPENI_CXR_URLS = [
    "https://openi.nlm.nih.gov/imgs/collections/NLMCXR/NLMCXR0001_0001.png",
]


def _map_png_to_mimic_cxr(png_path: Path, index: int) -> Path:
    patient_id = f"p_nlmcxr_{index:04d}"
    study_id = f"s_openi_{index:04d}"
    dest = ROOT / "datasets" / "mimic_cxr" / patient_id / study_id / f"{index:08d}.png"
    ensure_dir(dest.parent)
    shutil.copy2(png_path, dest)
    return dest


def extract_nlmcxr_to_mimic_cxr(archive_dir: Path, max_images: int, *, force: bool = False) -> int:
    """Copy first N PNGs from extracted NLMCXR archive into mimic_cxr scan layout."""
    png_root = archive_dir / "NLMCXR_png"
    if not png_root.exists():
        png_root = archive_dir
    png_files = sorted(png_root.rglob("*.png"))[:max_images]
    if not png_files:
        print("  no PNG files found under NLMCXR extract")
        return 0
    print(f"=== Map NLMCXR extract -> mimic_cxr ({len(png_files)} images) ===")
    count = 0
    for index, src in enumerate(png_files, start=1):
        dest = _map_png_to_mimic_cxr(src, index)
        if dest.exists() and dest.stat().st_size > 1000:
            count += 1
            print(f"  {dest.relative_to(ROOT)}")
    return count


def _download_stream(url: str, dest: Path, *, force: bool = False) -> bool:
    ensure_dir(dest.parent)
    if dest.exists() and dest.stat().st_size > 1000 and not force:
        print(f"  exists -> {dest.relative_to(ROOT)}")
        return True
    print(f"  GET {url[:90]}...")
    headers = {"User-Agent": "MedSafe/1.0 (research demo)"}
    with httpx.Client(timeout=600.0, follow_redirects=True, headers=headers) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with dest.open("wb") as handle:
                for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                    handle.write(chunk)
    print(f"  saved -> {dest.relative_to(ROOT)} ({dest.stat().st_size // 1024} KB)")
    return dest.exists()


MIMICIII_DEMO_FILES = (
    "PATIENTS.csv",
    "ADMISSIONS.csv",
    "PRESCRIPTIONS.csv",
    "LABEVENTS.csv",
    "DIAGNOSES_ICD.csv",
    "ICUSTAYS.csv",
    "CHARTEVENTS.csv",
    "INPUTEVENTS_MV.csv",
    "OUTPUTEVENTS.csv",
    "D_LABITEMS.csv",
    "D_ICD_DIAGNOSES.csv",
)


def fetch_mimiciii_demo(dest: Path, *, force: bool = False) -> int:
    """MIMIC-III Demo CSV tables (100 patients, open access on PhysioNet)."""
    if not force and any(dest.rglob("PRESCRIPTIONS.csv")):
        print(f"MIMIC-III demo already present -> {dest.relative_to(ROOT)}")
        return 1
    ensure_dir(dest)
    print("=== MIMIC-III Demo (PhysioNet open access) ===")
    headers = {"User-Agent": "MedSafe/1.0 (research demo; +https://github.com)"}
    ok = 0
    with httpx.Client(timeout=120.0, follow_redirects=True, headers=headers) as client:
        for name in MIMICIII_DEMO_FILES:
            url = f"{MIMICIII_DEMO_URL}{name}"
            out = dest / name
            if out.exists() and out.stat().st_size > 100 and not force:
                ok += 1
                continue
            try:
                resp = client.get(url)
                resp.raise_for_status()
                if resp.text.lstrip().startswith("<!DOCTYPE") or resp.text.lstrip().startswith("<html"):
                    raise RuntimeError("HTML response (PhysioNet may require browser login from your network)")
                out.write_bytes(resp.content)
                print(f"  {name} ({len(resp.content) // 1024} KB)")
                ok += 1
            except Exception as exc:
                print(f"  skip {name}: {exc}")
    if ok == 0:
        print("  MIMIC-III demo unavailable from this network; download manually:")
        print(f"    {MIMICIII_DEMO_URL}")
    return 1 if any(dest.rglob("PRESCRIPTIONS.csv")) else 0


def fetch_openi_cxr_subset(max_images: int, *, force: bool = False) -> int:
    """Map Open-I NLMCXR PNGs into MIMIC-CXR-style folders for /imaging scan."""
    print(f"=== Open-I NLMCXR subset ({max_images} images) ===")
    base = ROOT / "datasets" / "mimic_cxr"
    count = 0
    for index, url in enumerate(OPENI_CXR_URLS[:max_images], start=1):
        patient_id = f"p_nlmcxr_{index:04d}"
        study_id = f"s_openi_{index:04d}"
        filename = f"{index:08d}.png"
        dest = base / patient_id / study_id / filename
        if force and dest.exists():
            dest.unlink()
        try:
            if _download_stream(url, dest, force=force):
                count += 1
        except Exception as exc:
            print(f"  skip {url}: {exc}")
    return count


def fetch_nlmcxr_archives(cache_dir: Path, *, force: bool = False) -> tuple[int, int]:
    """Download NLMCXR PNG + reports archives to data/external/."""
    print("=== NLMCXR full archives (Open-I) ===")
    png_dest = cache_dir / "NLMCXR_png.tgz"
    rep_dest = cache_dir / "NLMCXR_reports.tgz"
    png_ok = int(_download_stream(NLMCXR_PNG_TGZ, png_dest, force=force))
    rep_ok = int(_download_stream(NLMCXR_REPORTS_TGZ, rep_dest, force=force))
    extract_root = cache_dir / "NLMCXR_png"
    if png_ok and (force or not any(extract_root.rglob("*.png"))):
        ensure_dir(extract_root)
        print(f"  extracting {png_dest.name} ...")
        with tarfile.open(png_dest, "r:gz") as archive:
            try:
                archive.extractall(path=extract_root, filter="data")
            except TypeError:
                archive.extractall(path=extract_root)
    return png_ok, rep_ok


def fetch_kits19_cases(case_count: int, *, force: bool = False) -> int:
    """KiTS19 starter imaging volumes from HuggingFace (partial, not all 300)."""
    if case_count <= 0:
        return 0
    print(f"=== KiTS19 imaging ({case_count} cases via HuggingFace) ===")
    base = ROOT / "datasets" / "kits19"
    downloaded = 0
    for case_id in range(case_count):
        case_dir = base / f"case_{case_id:05d}"
        imaging = case_dir / "imaging.nii.gz"
        if imaging.exists() and imaging.stat().st_size > 1_000_000 and not force:
            print(f"  exists -> {imaging.relative_to(ROOT)}")
            downloaded += 1
            continue
        url = f"{KITS_HF_BASE}/images/case_{case_id:05d}.nii.gz"
        try:
            if _download_stream(url, imaging, force=force):
                downloaded += 1
        except Exception as exc:
            print(f"  skip case_{case_id:05d}: {exc}")
    return downloaded


def fetch_chest_ct_samples(*, force: bool = False) -> int:
    """Public lung/chest CT NIfTI samples (MONAI COPD demo volumes)."""
    print("=== Chest / lung CT samples (MONAI COPD) ===")
    base = ROOT / "datasets" / "chest_ct"
    downloaded = 0
    for case_id, url in CHEST_CT_SAMPLES:
        case_dir = base / case_id
        imaging = case_dir / "imaging.nii.gz"
        if imaging.exists() and imaging.stat().st_size > 1_000_000 and not force:
            print(f"  exists -> {imaging.relative_to(ROOT)}")
            downloaded += 1
            continue
        try:
            if _download_stream(url, imaging, force=force):
                downloaded += 1
        except Exception as exc:
            print(f"  skip {case_id}: {exc}")
    return downloaded


def fetch_monai_imaging_samples(*, force: bool = False) -> tuple[int, int]:
    print("=== MONAI / Open-I imaging samples (fetch_imaging_samples) ===")
    from scripts.fetch_imaging_samples import fetch_brats_sample, fetch_cxr_samples

    return fetch_cxr_samples(force=force), fetch_brats_sample(force=force)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch public demo datasets for MedSafe")
    parser.add_argument("--all", action="store_true", help="Download all supported demo sources")
    parser.add_argument("--mimiciii-demo", action="store_true", help="MIMIC-III Demo CSV (~13 MB)")
    parser.add_argument("--openi-cxr", type=int, default=0, metavar="N", help="Open-I CXR PNG count")
    parser.add_argument("--nlmcxr-archives", action="store_true", help="NLMCXR png+reports tgz (~1 GB)")
    parser.add_argument(
        "--nlmcxr-map",
        type=int,
        default=0,
        metavar="N",
        help="Map first N PNGs from extracted NLMCXR archive into data/mimic_cxr/",
    )
    parser.add_argument("--kits-cases", type=int, default=0, metavar="N", help="KiTS19 CT cases from HF")
    parser.add_argument("--chest-ct", action="store_true", help="MONAI COPD chest/lung CT samples")
    parser.add_argument("--monai-samples", action="store_true", help="BraTS MONAI sample + CXR count")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    run_all = args.all
    if run_all:
        args.mimiciii_demo = True
        args.nlmcxr_archives = True
        args.nlmcxr_map = args.nlmcxr_map or 50
        args.kits_cases = args.kits_cases or 8
        args.chest_ct = True
        args.monai_samples = True

    if not any(
        [
            args.mimiciii_demo,
            args.openi_cxr,
            args.nlmcxr_archives,
            args.kits_cases,
            args.chest_ct,
            args.monai_samples,
            run_all,
        ]
    ):
        parser.error("Specify --all or at least one source flag")

    summary: dict[str, object] = {}

    if args.mimiciii_demo:
        dest = ROOT / "datasets" / "external" / "mimiciii-demo"
        summary["mimiciii_demo"] = fetch_mimiciii_demo(dest, force=args.force)

    if args.openi_cxr:
        summary["openi_cxr_images"] = fetch_openi_cxr_subset(args.openi_cxr, force=args.force)

    if args.nlmcxr_archives:
        cache = ROOT / "datasets" / "external" / "nlmcxr"
        png_ok, rep_ok = fetch_nlmcxr_archives(cache, force=args.force)
        summary["nlmcxr_png_archive"] = png_ok
        summary["nlmcxr_reports_archive"] = rep_ok
        if args.nlmcxr_map:
            summary["nlmcxr_mapped_cxr"] = extract_nlmcxr_to_mimic_cxr(
                cache, args.nlmcxr_map, force=args.force
            )
            from scripts.build_mimic_cxr_manifest import main as build_cxr_manifest
            try:
                build_cxr_manifest()
                summary["cxr_manifest"] = 1
            except Exception as exc:
                print(f"  cxr manifest skip: {exc}")
                summary["cxr_manifest"] = 0

    if args.kits_cases:
        summary["kits19_cases"] = fetch_kits19_cases(args.kits_cases, force=args.force)

    if args.chest_ct:
        summary["chest_ct_cases"] = fetch_chest_ct_samples(force=args.force)

    if args.monai_samples:
        cxr_n, brats_n = fetch_monai_imaging_samples(force=args.force)
        summary["monai_cxr"] = cxr_n
        summary["monai_brats"] = brats_n

    print("\n=== Summary ===")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print("\nMedSafe scan paths:")
    print("  data/mimic_cxr/     -> GET /api/v1/imaging/studies?source=mimic_cxr")
    print("  data/chest_ct/      -> source=chest_ct (lung/chest CT NIfTI)")
    print("  data/kits19/        -> source=kits19 (renal CT NIfTI)")
    print("  data/brats2024/     -> source=brats2024 (brain MRI)")
    print("  data/mimic/         -> MIMIC-CXR-JPG layout (scanned as mimic_cxr, not CT)")
    print("  data/external/mimiciii-demo/ -> clinical tables for Extract / ICU demo")


if __name__ == "__main__":
    main()
