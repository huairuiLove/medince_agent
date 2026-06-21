"""Download segmentation model weights into project models/ directory."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"


def ensure_hf():
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
        return hf_hub_download, snapshot_download
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
        from huggingface_hub import hf_hub_download, snapshot_download
        return hf_hub_download, snapshot_download


def download_vista3d():
    _, snapshot_download = ensure_hf()
    target = MODELS / "vista3d"
    target.mkdir(parents=True, exist_ok=True)
    print("Downloading MONAI/vista3d @ 0.5.11 ...")
    snapshot_download(repo_id="MONAI/vista3d", revision="0.5.11", local_dir=str(target))
    print(f"  -> {target}")


def download_sam_med3d():
    hf_hub_download, _ = ensure_hf()
    target = MODELS / "SAM-Med3D"
    target.mkdir(parents=True, exist_ok=True)
    for fname in [
        "sam_med3d_turbo.pth",
        "sam_med3d_turbo_cvpr_coreset.pth",
    ]:
        print(f"Downloading blueyo0/SAM-Med3D/{fname} ...")
        path = hf_hub_download(repo_id="blueyo0/SAM-Med3D", filename=fname, local_dir=str(target))
        print(f"  -> {path}")


def download_sam2d():
    hf_hub_download, _ = ensure_hf()
    target = MODELS / "SAM2D"
    target.mkdir(parents=True, exist_ok=True)
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
    # Fallback: reuse SAM-Med3D turbo for 2D slice mode
    med3d = MODELS / "SAM-Med3D" / "sam_med3d_turbo.pth"
    if med3d.exists():
        import shutil
        dest = target / "sam2d_from_med3d.pth"
        if not dest.exists():
            shutil.copy2(med3d, dest)
        print(f"  Fallback SAM2D weights -> {dest}")
    else:
        print("  Place your SAM2D .pth weights in models/SAM2D/")


def download_totalsegmentator():
    print("Installing TotalSegmentator via pip (weights download on first run) ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "TotalSegmentator"])
    ts_home = MODELS / "totalsegmentator"
    ts_home.mkdir(parents=True, exist_ok=True)
    os.environ["TOTALSEG_HOME"] = str(ts_home)
    print(f"  TOTALSEG_HOME={ts_home}")
    print("  Weights will populate on first inference.")


def main():
    parser = argparse.ArgumentParser(description="Download MedSafe segmentation models")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--vista3d", action="store_true")
    parser.add_argument("--sam-med3d", action="store_true")
    parser.add_argument("--sam2d", action="store_true")
    parser.add_argument("--totalsegmentator", action="store_true")
    args = parser.parse_args()
    run_all = args.all or not any([args.vista3d, args.sam_med3d, args.sam2d, args.totalsegmentator])

    if run_all or args.vista3d:
        download_vista3d()
    if run_all or args.sam_med3d:
        download_sam_med3d()
    if run_all or args.sam2d:
        download_sam2d()
    if run_all or args.totalsegmentator:
        download_totalsegmentator()
    print("Done.")


if __name__ == "__main__":
    main()
