"""Load 2D visual images and optional NIfTI middle slices for viewer / segmentation."""
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image

from src.config import resolve_path
from src.utils import ensure_dir

ImageModality = Literal["CT", "MRI", "XR", "unknown"]
VISUAL_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def is_visual_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VISUAL_SUFFIXES


def load_grayscale_array(path: str | Path) -> np.ndarray:
    path = Path(path)
    if is_visual_image(path):
        img = Image.open(path).convert("L")
        return np.asarray(img, dtype=np.float32)

    try:
        import nibabel as nib
    except ImportError as exc:
        raise RuntimeError("nibabel required for NIfTI slice export") from exc

    vol = nib.load(str(path)).get_fdata(dtype=np.float32)
    if vol.ndim == 4:
        vol = vol[..., 0]
    if vol.ndim != 3:
        raise ValueError(f"Unsupported volume shape: {vol.shape}")
    mid = vol.shape[2] // 2
    slc = vol[:, :, mid]
    slc = _normalize_to_uint8(slc)
    return slc.astype(np.float32)


def export_slice_png(nii_path: str | Path, slice_index: int | None = None, out_dir: str | Path | None = None) -> Path:
    try:
        import nibabel as nib
    except ImportError as exc:
        raise RuntimeError("nibabel required") from exc

    nii_path = Path(nii_path)
    vol = nib.load(str(nii_path)).get_fdata(dtype=np.float32)
    if vol.ndim == 4:
        vol = vol[..., 0]
    if vol.ndim != 3:
        raise ValueError(f"Unsupported volume shape: {vol.shape}")

    idx = slice_index if slice_index is not None else vol.shape[2] // 2
    idx = max(0, min(idx, vol.shape[2] - 1))
    slc = _normalize_to_uint8(vol[:, :, idx])

    cache_root = resolve_path("data/imaging_cache/slices")
    target_dir = Path(out_dir) if out_dir else cache_root / nii_path.parent.name
    ensure_dir(target_dir)
    out = target_dir / f"{nii_path.stem}_z{idx:04d}.png"
    Image.fromarray(slc).save(out)
    return out


def list_volume_slices(nii_path: str | Path) -> list[int]:
    try:
        import nibabel as nib
    except ImportError:
        return [0]
    vol = nib.load(str(nii_path)).get_fdata()
    if vol.ndim == 4:
        vol = vol[..., 0]
    depth = vol.shape[2] if vol.ndim == 3 else 1
    step = max(1, depth // 24)
    return list(range(0, depth, step))


def save_overlay(base_path: str | Path, mask: np.ndarray, color: tuple[int, int, int] = (255, 64, 64), alpha: float = 0.45) -> Path:
    base_path = Path(base_path)
    base = np.asarray(Image.open(base_path).convert("RGB"), dtype=np.float32)
    if mask.shape[:2] != base.shape[:2]:
        mask_img = Image.fromarray((mask > 0).astype(np.uint8) * 255).resize((base.shape[1], base.shape[0]), Image.NEAREST)
        mask = np.asarray(mask_img) > 127
    else:
        mask = mask > 0

    overlay = base.copy()
    color_arr = np.array(color, dtype=np.float32)
    overlay[mask] = overlay[mask] * (1 - alpha) + color_arr * alpha

    out_dir = resolve_path("data/imaging_cache/overlays")
    ensure_dir(out_dir)
    out = out_dir / f"{base_path.stem}_overlay.png"
    Image.fromarray(overlay.astype(np.uint8)).save(out)
    return out


def image_to_base64(path: str | Path) -> str:
    data = Path(path).read_bytes()
    suffix = Path(path).suffix.lower().lstrip(".")
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    return f"data:image/{mime};base64," + base64.b64encode(data).decode("ascii")


def decode_base64_image(data_url: str, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    ensure_dir(out_path.parent)
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    out_path.write_bytes(base64.b64decode(data_url))
    return out_path


def _normalize_to_uint8(arr: np.ndarray) -> np.ndarray:
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    lo, hi = np.percentile(arr, 1), np.percentile(arr, 99)
    if hi <= lo:
        hi = lo + 1.0
    scaled = np.clip((arr - lo) / (hi - lo), 0, 1)
    return (scaled * 255).astype(np.uint8)


def guess_modality(path: str | Path) -> ImageModality:
    p = str(path).lower()
    if "brats" in p or "t1" in p or "t2" in p or "mri" in p:
        return "MRI"
    if "mimic" in p or "ct" in p:
        return "CT"
    return "unknown"
