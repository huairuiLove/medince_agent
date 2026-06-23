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
VolumeAxis = Literal["axial", "coronal", "sagittal"]
VISUAL_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def is_visual_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VISUAL_SUFFIXES


def is_vlm_compatible_image(path: str | Path) -> bool:
    """True if path is a readable PNG/JPEG/WebP/BMP suitable for Qwen VLM."""
    p = Path(path)
    if not p.is_file():
        return False
    if is_nifti(p):
        return False
    if p.suffix.lower() not in VISUAL_SUFFIXES:
        return False
    try:
        with Image.open(p) as img:
            img.verify()
        with Image.open(p) as img:
            img.load()
        return True
    except Exception:
        return False


def resolve_vlm_image_paths(paths: list[str]) -> list[str]:
    """Resolve project-relative paths and keep only VLM-safe raster images."""
    root = resolve_path(".")
    resolved: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        if not raw:
            continue
        target = Path(raw)
        if not target.is_absolute():
            target = (root / raw).resolve()
        else:
            target = target.resolve()
        key = str(target)
        if key in seen:
            continue
        if is_vlm_compatible_image(target):
            seen.add(key)
            resolved.append(key)
    return resolved


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
    if out.is_file() and out.stat().st_size > 1000:
        return out
    Image.fromarray(slc).save(out)
    return out


def list_volume_slices(nii_path: str | Path) -> list[int]:
    try:
        import nibabel as nib
    except ImportError:
        return [0]
    shape = nib.load(str(nii_path)).shape
    if len(shape) == 4:
        depth = shape[2]
    elif len(shape) == 3:
        depth = shape[2]
    else:
        depth = 1
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


def is_nifti(path: str | Path) -> bool:
    p = Path(path)
    return str(p).endswith(".nii.gz") or p.suffix == ".nii"


def load_nifti_volume(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    try:
        import nibabel as nib
    except ImportError as exc:
        raise RuntimeError("nibabel required for NIfTI volumes") from exc
    img = nib.load(str(path))
    vol = np.asarray(img.get_fdata(dtype=np.float32))
    if vol.ndim == 4:
        vol = vol[..., 0]
    if vol.ndim != 3:
        raise ValueError(f"Unsupported volume shape: {vol.shape}")
    return vol, img.affine


def get_volume_meta(path: str | Path) -> dict:
    vol, affine = load_nifti_volume(path)
    spacing = np.sqrt((affine[:3, :3] ** 2).sum(axis=0)).tolist()
    shape = list(vol.shape)
    return {
        "shape": shape,
        "spacing": [float(s) for s in spacing],
        "slice_counts": {
            "axial": shape[2],
            "coronal": shape[1],
            "sagittal": shape[0],
        },
        "modality": guess_modality(path),
    }


def _extract_slice(vol: np.ndarray, axis: VolumeAxis, index: int) -> np.ndarray:
    if axis == "axial":
        idx = max(0, min(index, vol.shape[2] - 1))
        return vol[:, :, idx]
    if axis == "coronal":
        idx = max(0, min(index, vol.shape[1] - 1))
        return vol[:, idx, :]
    idx = max(0, min(index, vol.shape[0] - 1))
    return vol[idx, :, :]


def export_volume_slice(
    volume_path: str | Path,
    axis: VolumeAxis = "axial",
    slice_index: int = 0,
    mask_path: str | Path | None = None,
    overlay_color: tuple[int, int, int] = (25, 118, 210),
    alpha: float = 0.45,
) -> Path:
    """Export MPR slice PNG; optionally composite with 3D mask overlay."""
    volume_path = Path(volume_path)
    vol, _ = load_nifti_volume(volume_path)
    slc = _extract_slice(vol, axis, slice_index)
    base_u8 = _normalize_to_uint8(slc)

    cache_root = resolve_path("data/imaging_cache/mpr")
    stem = volume_path.name.replace(".nii.gz", "").replace(".nii", "")
    tag = f"{stem}_{axis}_{slice_index:04d}"
    out = cache_root / f"{tag}.png"
    ensure_dir(out.parent)

    if mask_path and Path(mask_path).exists():
        mask_vol, _ = load_nifti_volume(mask_path)
        if mask_vol.shape == vol.shape:
            mslc = _extract_slice(mask_vol, axis, slice_index) > 0
            base_rgb = np.stack([base_u8] * 3, axis=-1).astype(np.float32)
            color_arr = np.array(overlay_color, dtype=np.float32)
            base_rgb[mslc] = base_rgb[mslc] * (1 - alpha) + color_arr * alpha
            Image.fromarray(base_rgb.astype(np.uint8)).save(out)
            return out

    Image.fromarray(base_u8).save(out)
    return out


def save_overlay_from_volume_slice(
    volume_path: str | Path,
    mask_path: str | Path,
    axis: VolumeAxis,
    slice_index: int,
    color: tuple[int, int, int] = (25, 118, 210),
) -> Path:
    return export_volume_slice(
        volume_path,
        axis=axis,
        slice_index=slice_index,
        mask_path=mask_path,
        overlay_color=color,
    )


def export_pseudo_nifti_from_image(
    image_path: str | Path,
    depth: int = 16,
    spacing: tuple[float, float, float] = (1.5, 1.5, 1.5),
    max_side: int = 384,
) -> tuple[Path, int]:
    """Stack a 2D JPG/PNG into a thin axial NIfTI for VISTA3D bundle inference."""
    try:
        import nibabel as nib
    except ImportError as exc:
        raise RuntimeError("nibabel required") from exc

    image_path = Path(image_path)
    arr = load_grayscale_array(image_path)
    h, w = arr.shape
    if max(h, w) > max_side:
        scale = max_side / max(h, w)
        nh, nw = int(h * scale), int(w * scale)
        arr = np.asarray(
            Image.fromarray(arr.astype(np.uint8)).resize((nw, nh), Image.BILINEAR),
            dtype=np.float32,
        )
    vol = np.stack([arr] * depth, axis=-1).astype(np.float32)
    affine = np.diag([spacing[0], spacing[1], spacing[2], 1.0]).astype(np.float64)

    cache_dir = resolve_path("data/imaging_cache/pseudo_vol")
    ensure_dir(cache_dir)
    out = cache_dir / f"{image_path.stem}_pseudo_d{depth}_s{max_side}.nii.gz"
    nib.save(nib.Nifti1Image(vol, affine), str(out))
    return out, depth // 2


def save_overlay_from_mask_volume(
    display_path: str | Path,
    mask_path: str | Path,
    axis: VolumeAxis = "axial",
    slice_index: int = 0,
    color: tuple[int, int, int] = (25, 118, 210),
) -> Path:
    """Composite a mask volume slice onto a 2D display image."""
    mask_vol, _ = load_nifti_volume(mask_path)
    mslc = _extract_slice(mask_vol, axis, slice_index) > 0
    return save_overlay(display_path, mslc, color=color)
