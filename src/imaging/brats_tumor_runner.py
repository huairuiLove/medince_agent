"""MONAI BraTS glioma tumor subregion segmentation (ET / TC / WT)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

from src.config import resolve_path
from src.imaging.registry import model_dir
from src.logging_config import get_logger
from src.utils import ensure_dir

logger = get_logger("imaging.brats_tumor")

MODALITY_SUFFIXES = ("t1c", "t1n", "t2w", "t2f")
MODALITY_ALIASES: dict[str, tuple[str, ...]] = {
    "t1c": ("t1c", "t1ce", "t1_ce"),
    "t1n": ("t1n", "t1"),
    "t2w": ("t2w", "t2"),
    "t2f": ("t2f", "flair", "t2flair"),
}
TUMOR_REGIONS = {
    "whole_tumor": {1, 2, 4},
    "tumor_core": {1, 4},
    "enhancing_tumor": {4},
}


def _volume_stem(path: Path) -> str:
    return path.name.replace(".nii.gz", "").replace(".nii", "")


def find_brats_modalities(case_dir: str | Path) -> dict[str, Path]:
    case_dir = Path(case_dir)
    found: dict[str, Path] = {}
    for canonical, aliases in MODALITY_ALIASES.items():
        matches: list[Path] = []
        for alias in aliases:
            matches.extend(sorted(case_dir.glob(f"*{alias}*.nii.gz")))
        matches = [m for m in matches if "seg" not in m.name.lower()]
        if matches:
            found[canonical] = matches[0]
    return found


def stack_brats_case(case_dir: str | Path, out_path: str | Path | None = None) -> Path:
    """Stack BraTS T1c/T1n/T2w/T2F into a 4-channel NIfTI for MONAI bundle inference."""
    case_dir = Path(case_dir)
    mods = find_brats_modalities(case_dir)
    missing = [s for s in MODALITY_SUFFIXES if s not in mods]
    if missing:
        raise FileNotFoundError(
            f"BraTS case missing modalities {missing}. Found: {list(mods.keys())} in {case_dir}"
        )

    ref = nib.load(str(mods["t1c"]))
    ref_affine = ref.affine
    channels: list[np.ndarray] = []
    for suffix in MODALITY_SUFFIXES:
        vol = np.asarray(nib.load(str(mods[suffix])).get_fdata(dtype=np.float32))
        if vol.ndim == 4:
            vol = vol[..., 0]
        channels.append(vol)

    stacked = np.stack(channels, axis=0).astype(np.float32)
    cache_dir = resolve_path("data/imaging_cache/brats_input")
    ensure_dir(cache_dir)
    stem = case_dir.name
    out = Path(out_path) if out_path else cache_dir / f"{stem}_4ch.nii.gz"
    nib.save(nib.Nifti1Image(stacked, ref_affine), str(out))
    return out


def _extract_region_mask(seg_path: Path, region: str) -> Path:
    labels = TUMOR_REGIONS.get(region, TUMOR_REGIONS["whole_tumor"])
    vol = np.asarray(nib.load(str(seg_path)).get_fdata(dtype=np.float32))
    if vol.ndim == 4:
        vol = vol[..., 0]
    mask = np.isin(np.rint(vol).astype(np.int32), list(labels)).astype(np.uint8)
    out = seg_path.with_name(f"{seg_path.stem}_{region}.nii.gz")
    nib.save(nib.Nifti1Image(mask, nib.load(str(seg_path)).affine), str(out))
    return out


def run_brats_tumor_volume(
    volume_path: str | Path,
    *,
    region: str = "whole_tumor",
    device: str = "cpu",
) -> Path:
    """Run MONAI brats_mri_segmentation bundle; return region-specific mask NIfTI."""
    volume_path = Path(volume_path).resolve()
    case_dir = volume_path.parent if volume_path.is_file() else volume_path
    if volume_path.is_file() and volume_path.name.endswith((".nii.gz", ".nii")):
        case_dir = volume_path.parent

    bundle_root = model_dir("brats_tumor").resolve()
    ckpt = bundle_root / "models" / "model.pt"
    if not ckpt.exists():
        raise FileNotFoundError(
            f"BraTS tumor weights missing. Run: python scripts/download_models.py --brats-tumor"
        )

    stacked = stack_brats_case(case_dir)
    stem = case_dir.name
    out_dir = resolve_path(f"data/imaging_cache/brats_tumor/{stem}")
    ensure_dir(out_dir)
    raw_seg = out_dir / f"{stem}_seg.nii.gz"
    region_mask = out_dir / f"{stem}_seg_{region}.nii.gz"
    if region_mask.exists():
        return region_mask

    try:
        import torch
        from monai.bundle import ConfigParser
    except ImportError as exc:
        raise RuntimeError("monai required for BraTS tumor segmentation") from exc

    prev_cwd = os.getcwd()
    sys.path.insert(0, str(bundle_root))
    try:
        os.chdir(bundle_root)
        parser = ConfigParser()
        parser.read_config(str(bundle_root / "configs" / "inference.json"))
        parser["device"] = torch.device(device)
        parser["input_dict"] = {"image": str(stacked.resolve())}
        parser["output_dir"] = str(out_dir.resolve())
        parser["sw_batch_size"] = 1

        logger.info("brats_tumor_start", extra={"case": stem, "region": region})
        parser.parse(True)
        parser.get_parsed_content("initialize", eval=True)
        evaluator = parser.get_parsed_content("evaluator")
        evaluator.run()
    finally:
        os.chdir(prev_cwd)

    produced = sorted(out_dir.rglob("*.nii.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not produced:
        raise RuntimeError("BraTS tumor inference finished but no segmentation output found")
    if not raw_seg.exists():
        import shutil
        shutil.copy2(produced[0], raw_seg)

    return _extract_region_mask(raw_seg, region)
