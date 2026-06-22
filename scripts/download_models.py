"""Download segmentation model weights into project models/ directory."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"

# TotalSegmentator official weight location inside project
TS_WEIGHTS = MODELS / "totalsegmentator" / "nnunet" / "results"


def ensure_hf():
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
        return hf_hub_download, snapshot_download
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--trusted-host", "pypi.org",
             "--trusted-host", "files.pythonhosted.org", "huggingface_hub"],
        )
        from huggingface_hub import hf_hub_download, snapshot_download
        return hf_hub_download, snapshot_download


def _exists(path: Path, min_mb: float = 1.0) -> bool:
    if not path.exists():
        return False
    if path.is_file():
        return path.stat().st_size >= min_mb * 1024 * 1024
    return any(f.is_file() and f.stat().st_size >= min_mb * 1024 * 1024 for f in path.rglob("*"))


def download_vista3d(force: bool = False):
    target = MODELS / "vista3d"
    ckpt = target / "models" / "model.pt"
    if not force and _exists(ckpt, min_mb=100):
        print(f"VISTA3D already present -> {ckpt}")
        return
    _, snapshot_download = ensure_hf()
    target.mkdir(parents=True, exist_ok=True)
    print("Downloading MONAI/vista3d @ 0.5.11 ...")
    snapshot_download(repo_id="MONAI/vista3d", revision="0.5.11", local_dir=str(target))
    print(f"  -> {target}")


def download_sam_med3d(force: bool = False):
    hf_hub_download, _ = ensure_hf()
    target = MODELS / "SAM-Med3D"
    target.mkdir(parents=True, exist_ok=True)
    for fname in ["sam_med3d_turbo.pth", "sam_med3d_turbo_cvpr_coreset.pth"]:
        dest = target / fname
        if not force and _exists(dest, min_mb=100):
            print(f"SAM-Med3D already present -> {dest}")
            continue
        print(f"Downloading blueyo0/SAM-Med3D/{fname} ...")
        path = hf_hub_download(repo_id="blueyo0/SAM-Med3D", filename=fname, local_dir=str(target))
        print(f"  -> {path}")


def download_sam2d(force: bool = False):
    hf_hub_download, _ = ensure_hf()
    target = MODELS / "SAM2D"
    target.mkdir(parents=True, exist_ok=True)
    dest = target / "medsam_vit_b.pth"
    if not force and _exists(dest, min_mb=100):
        print(f"SAM2D already present -> {dest}")
        return
    candidates = [
        ("GleghornLab/medsam-vit-b", "medsam_vit_b.pth"),
        ("bowang-lab/MedSAM", "medsam_vit_b.pth"),
    ]
    for repo, fname in candidates:
        print(f"Downloading SAM2D from {repo}/{fname} ...")
        try:
            path = hf_hub_download(repo_id=repo, filename=fname, local_dir=str(target))
            print(f"  -> {path}")
            return
        except Exception as exc:
            print(f"  skipped: {exc}")
    med3d = MODELS / "SAM-Med3D" / "sam_med3d_turbo.pth"
    if med3d.exists():
        fallback = target / "sam2d_from_med3d.pth"
        if not fallback.exists():
            shutil.copy2(med3d, fallback)
        print(f"  Fallback SAM2D weights -> {fallback}")
    else:
        print("  Place your SAM2D .pth weights in models/SAM2D/")


def _setup_totalseg_env() -> None:
    TS_WEIGHTS.mkdir(parents=True, exist_ok=True)
    os.environ["TOTALSEG_WEIGHTS_PATH"] = str(TS_WEIGHTS)
    os.environ["TOTALSEG_HOME_DIR"] = str(MODELS / "totalsegmentator")


def download_totalsegmentator(force: bool = False, include_mr: bool = True):
    """Download TotalSegmentator nnU-Net weights into models/totalsegmentator/."""
    print("Ensuring TotalSegmentator package ...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--trusted-host", "pypi.org",
         "--trusted-host", "files.pythonhosted.org", "TotalSegmentator"],
    )
    _setup_totalseg_env()

    from totalsegmentator.libs import download_pretrained_weights
    from totalsegmentator.config import setup_totalseg, set_config_key

    setup_totalseg()
    set_config_key("statistics_disclaimer_shown", True)

    # MedSafe uses fast CT (297) + fastest CT (298); optional fast MR for BraTS
    task_ids: list[int] = [297, 298]
    if include_mr:
        task_ids.extend([852, 853])

    for task_id in task_ids:
        folder_names = {
            297: "Dataset297_TotalSegmentator_total_3mm_1559subj",
            298: "Dataset298_TotalSegmentator_total_6mm_1559subj",
            852: "Dataset852_TotalSegMRI_total_3mm_1088subj",
            853: "Dataset853_TotalSegMRI_total_6mm_1088subj",
        }
        weights_path = TS_WEIGHTS / folder_names[task_id]
        if not force and weights_path.exists():
            print(f"TotalSegmentator task {task_id} already present -> {weights_path}")
            continue
        print(f"Downloading TotalSegmentator task {task_id} ({folder_names[task_id]}) ...")
        download_pretrained_weights(task_id)
        print(f"  -> {weights_path}")

    print(f"TotalSegmentator weights root: {TS_WEIGHTS}")


def download_ddi_bert(force: bool = False):
    """Download Bio_ClinicalBERT DDI classifier to models/ddi_bert/."""
    _, snapshot_download = ensure_hf()
    target = MODELS / "ddi_bert"
    ckpt = target / "pytorch_model.bin"
    if not force and _exists(ckpt, min_mb=100):
        print(f"DDI BERT already present -> {ckpt}")
        return
    target.mkdir(parents=True, exist_ok=True)
    print("Downloading ltmai/Bio_ClinicalBERT_DDI_finetuned ...")
    snapshot_download(repo_id="ltmai/Bio_ClinicalBERT_DDI_finetuned", local_dir=str(target))
    print(f"  -> {target}")


def download_med7(force: bool = False):
    """Download Med7 spaCy wheel to models/med7/."""
    hf_hub_download, _ = ensure_hf()
    target = MODELS / "med7"
    target.mkdir(parents=True, exist_ok=True)
    wheel_name = "en_core_med7_lg-1.1.0-py3-none-any.whl"
    dest = target / wheel_name
    if not force and _exists(dest, min_mb=100):
        print(f"Med7 wheel already present -> {dest}")
        return
    print(f"Downloading kormilitzin/en_core_med7_lg/{wheel_name} ...")
    path = hf_hub_download(
        repo_id="kormilitzin/en_core_med7_lg",
        filename=wheel_name,
        local_dir=str(target),
    )
    print(f"  -> {path}")
    print("Install with: pip install models/med7/en_core_med7_lg-1.1.0-py3-none-any.whl")


def download_brats_tumor(force: bool = False):
    """Download MONAI brats_mri_segmentation bundle (BraTS glioma ET/TC/WT)."""
    _, snapshot_download = ensure_hf()
    target = MODELS / "brats_tumor"
    ckpt = target / "models" / "model.pt"
    if not force and _exists(ckpt, min_mb=10):
        print(f"BraTS tumor bundle already present -> {ckpt}")
        return
    target.mkdir(parents=True, exist_ok=True)
    print("Downloading MONAI/brats_mri_segmentation @ main ...")
    snapshot_download(repo_id="MONAI/brats_mri_segmentation", local_dir=str(target))
    print(f"  -> {target}")


def download_cxr_lesion(force: bool = False):
    """Download CXR lesion U-Net (RSNA/SIIM) + install torchxrayvision for pathology fallback."""
    print("Installing CXR lesion dependencies (torchxrayvision, timm, albumentations) ...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--trusted-host", "pypi.org",
         "--trusted-host", "files.pythonhosted.org",
         "torchxrayvision>=1.2.0", "timm>=0.9.0", "albumentations>=1.3.0"],
    )
    _, snapshot_download = ensure_hf()
    target = MODELS / "cxr_lesion" / "pneumonia_unet"
    ckpt = target / "model.safetensors"
    if not force and _exists(ckpt, min_mb=10):
        print(f"CXR pneumonia U-Net already present -> {ckpt}")
    else:
        target.mkdir(parents=True, exist_ok=True)
        print("Downloading Dimaodessa/pneumonia-cxr (EfficientNetV2 U-Net, RSNA+SIIM) ...")
        snapshot_download(repo_id="Dimaodessa/pneumonia-cxr", local_dir=str(target))
        print(f"  -> {target}")

    readme = MODELS / "cxr_lesion" / "README.txt"
    if force or not readme.exists():
        readme.parent.mkdir(parents=True, exist_ok=True)
        readme.write_text(
            "CXR lesion segmentation:\n"
            "  - Opacity/consolidation/pneumonia: Dimaodessa/pneumonia-cxr U-Net (pneumonia_unet/)\n"
            "  - Effusion/pneumothorax/etc.: torchxrayvision Grad-CAM fallback\n"
            "Download: python scripts/download_models.py --cxr-lesion\n",
            encoding="utf-8",
        )
    print(f"  -> {MODELS / 'cxr_lesion'}")


def verify_all() -> bool:
    checks = {
        "vista3d": MODELS / "vista3d" / "models" / "model.pt",
        "sam_med3d": MODELS / "SAM-Med3D" / "sam_med3d_turbo.pth",
        "sam2d": MODELS / "SAM2D" / "medsam_vit_b.pth",
        "totalseg_297": TS_WEIGHTS / "Dataset297_TotalSegmentator_total_3mm_1559subj",
        "totalseg_298": TS_WEIGHTS / "Dataset298_TotalSegmentator_total_6mm_1559subj",
        "brats_tumor": MODELS / "brats_tumor" / "models" / "model.pt",
        "cxr_lesion": MODELS / "cxr_lesion" / "pneumonia_unet" / "model.safetensors",
        "ddi_bert": MODELS / "ddi_bert" / "pytorch_model.bin",
        "med7": MODELS / "med7" / "en_core_med7_lg-1.1.0-py3-none-any.whl",
    }
    sam2d_alt = MODELS / "SAM2D" / "sam2d_from_med3d.pth"
    ok = True
    print("\n=== Weight verification ===")
    for name, path in checks.items():
        if name == "sam2d" and not path.exists() and sam2d_alt.exists():
            path = sam2d_alt
        present = path.exists()
        size = ""
        if present and path.is_file():
            size = f" ({path.stat().st_size / 1024 / 1024:.0f} MB)"
        elif present:
            total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            size = f" ({total / 1024 / 1024:.0f} MB)"
        status = "OK" if present else "MISSING"
        print(f"  [{status}] {name}: {path}{size}")
        ok = ok and present
    return ok


def main():
    parser = argparse.ArgumentParser(description="Download MedSafe models to models/")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-download even if present")
    parser.add_argument("--vista3d", action="store_true")
    parser.add_argument("--sam-med3d", action="store_true")
    parser.add_argument("--sam2d", action="store_true")
    parser.add_argument("--totalsegmentator", action="store_true")
    parser.add_argument("--brats-tumor", action="store_true", help="MONAI BraTS glioma lesion segmentation")
    parser.add_argument("--cxr-lesion", action="store_true", help="torchxrayvision CXR pathology lesion model")
    parser.add_argument("--safety-models", action="store_true", help="Med7 + Bio_ClinicalBERT DDI")
    parser.add_argument("--ddi-bert", action="store_true")
    parser.add_argument("--med7", action="store_true")
    parser.add_argument("--no-mr", action="store_true", help="Skip TotalSegmentator MRI weights")
    args = parser.parse_args()
    run_all = args.all or not any([
        args.vista3d, args.sam_med3d, args.sam2d, args.totalsegmentator,
        args.brats_tumor, args.cxr_lesion,
        args.safety_models, args.ddi_bert, args.med7,
    ])

    if run_all or args.vista3d:
        download_vista3d(force=args.force)
    if run_all or args.sam_med3d:
        download_sam_med3d(force=args.force)
    if run_all or args.sam2d:
        download_sam2d(force=args.force)
    if run_all or args.totalsegmentator:
        download_totalsegmentator(force=args.force, include_mr=not args.no_mr)
    if run_all or args.brats_tumor:
        download_brats_tumor(force=args.force)
    if run_all or args.cxr_lesion:
        download_cxr_lesion(force=args.force)
    if run_all or args.safety_models or args.ddi_bert:
        download_ddi_bert(force=args.force)
    if run_all or args.safety_models or args.med7:
        download_med7(force=args.force)

    verify_all()
    print("\nDone.")


if __name__ == "__main__":
    main()
