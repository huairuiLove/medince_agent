"""MONAI VISTA3D bundle runner — real 3D volume segmentation."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from src.config import resolve_path
from src.config import resolve_path
from src.imaging.monai_bundle_runner import run_monai_bundle_inference
from src.imaging.registry import model_dir
from src.logging_config import get_logger
from src.utils import ensure_dir

logger = get_logger("imaging.vista3d_runner")

ORGAN_LABELS: dict[str, list[int]] = {
    "brain": [22],
    "liver": [1],
    "lung": [28, 29, 30, 31, 32],
    "kidney": [5, 14],
}

_LABELS_PATH = Path(__file__).resolve().parents[2] / "models" / "vista3d" / "docs" / "labels.json"


def _load_organ_labels() -> dict[str, list[int]]:
    if _LABELS_PATH.exists():
        raw = json.loads(_LABELS_PATH.read_text())
        if "brain" in raw:
            return {
                "brain": [int(raw["brain"])],
                "liver": [int(raw["liver"])],
                "lung": [28, 29, 30, 31, 32],
                "kidney": [int(raw["right kidney"]), int(raw["left kidney"])],
            }
    return ORGAN_LABELS


def _is_mri(path: Path) -> bool:
    p = str(path).lower()
    return any(k in p for k in ("brats", "mri", "t1c", "t1n", "t2w", "t2f"))


def _needs_scale_intensity(path: Path) -> bool:
    """Non-HU sources (MRI, 2D JPG pseudo-volumes) skip CT Hounsfield windowing."""
    p = str(path).lower()
    if _is_mri(path):
        return True
    return "pseudo_vol" in p or "_pseudo.nii" in p


def _volume_stem(path: Path) -> str:
    return path.name.replace(".nii.gz", "").replace(".nii", "")


def _find_mask(out_dir: Path, stem: str) -> Path:
    preferred = out_dir / stem / f"{stem}_trans.nii.gz"
    if preferred.exists():
        return preferred
    candidates = sorted(out_dir.rglob("*_trans.nii.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError("VISTA3D finished but no output mask found")
    return candidates[0]


def run_vista3d_volume(
    volume_path: str | Path,
    organ: str = "brain",
    *,
    device: str = "cpu",
) -> Path:
    """Run VISTA3D bundle on a NIfTI volume; return path to segmentation mask."""
    volume_path = Path(volume_path).resolve()
    if not volume_path.exists():
        raise FileNotFoundError(f"Volume not found: {volume_path}")

    bundle_root = model_dir("vista3d").resolve()
    if not (bundle_root / "models" / "model.pt").exists():
        raise FileNotFoundError(f"VISTA3D weights missing under {bundle_root}")

    labels = _load_organ_labels().get(organ, [22])
    stem = _volume_stem(volume_path)
    out_dir = resolve_path(f"data/imaging_cache/vista3d/{stem}")
    ensure_dir(out_dir)

    organ_mask = out_dir / f"{stem}_{organ}_trans.nii.gz"
    if organ_mask.exists():
        logger.info("vista3d_cache_hit", extra={"path": str(organ_mask)})
        return organ_mask

    # Reuse mask from a prior run (different cache layout)
    legacy = list(resolve_path("data/imaging_cache").glob(f"**/vista3d*/**/{stem}_trans.nii.gz"))
    if legacy:
        import shutil
        shutil.copy2(legacy[0], organ_mask)
        return organ_mask

    prev_cwd = os.getcwd()
    sys.path.insert(0, str(bundle_root))
    try:
        os.chdir(bundle_root)
        overrides: dict = {
            "input_dict": {"image": str(volume_path), "label_prompt": labels},
            "output_dir": str(out_dir.resolve()),
            "sw_batch_size": 1,
            "use_point_window": False,
        }
        if _needs_scale_intensity(volume_path):
            parser_pre = __import__("monai.bundle", fromlist=["ConfigParser"]).ConfigParser()
            parser_pre.read_config(str(bundle_root / "configs" / "inference.json"))
            transforms = list(parser_pre["preprocessing_transforms"])
            for t in transforms:
                if isinstance(t, dict) and t.get("_target_") == "ScaleIntensityRanged":
                    t["_disabled_"] = True
            transforms.append({
                "_target_": "ScaleIntensityd",
                "keys": "@image_key",
                "minv": 0.0,
                "maxv": 1.0,
            })
            overrides["preprocessing_transforms"] = transforms

        logger.info(
            "vista3d_3d_start",
            extra={"volume": volume_path.name, "organ": organ, "labels": labels},
        )
        run_monai_bundle_inference(
            bundle_root,
            device=device,
            overrides=overrides,
        )
    finally:
        os.chdir(prev_cwd)

    produced = _find_mask(out_dir, stem)
    if produced != organ_mask:
        import shutil
        shutil.copy2(produced, organ_mask)

    logger.info("vista3d_3d_done", extra={"mask": str(organ_mask)})
    return organ_mask
