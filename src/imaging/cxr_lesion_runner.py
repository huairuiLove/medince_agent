"""CXR pathology lesion segmentation — U-Net (opacity) + pathology Grad-CAM fallback."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from src.imaging.registry import model_dir
from src.logging_config import get_logger

logger = get_logger("imaging.cxr_lesion")

# MIMIC-ILS / common CXR lesion categories mapped to torchxrayvision pathology labels
CXR_LESION_MAP: dict[str, str] = {
    "opacity": "Lung Opacity",
    "consolidation": "Consolidation",
    "pneumonia": "Pneumonia",
    "atelectasis": "Atelectasis",
    "edema": "Edema",
    "cardiomegaly": "Cardiomegaly",
    "effusion": "Effusion",
    "pneumothorax": "Pneumothorax",
    "infiltration": "Infiltration",
    "nodule": "Nodule",
    "mass": "Mass",
}

# RSNA/SIIM pneumonia U-Net covers lung opacity–type lesions (pixel masks, not heatmaps)
UNET_LESION_TYPES = frozenset({
    "opacity",
    "consolidation",
    "pneumonia",
    "infiltration",
    "nodule",
    "mass",
})

_XRV_MODEL = None
_XRV_TRANSFORM = None
_UNET_MODEL = None


def pneumonia_unet_dir() -> Path:
    return model_dir("cxr_lesion") / "pneumonia_unet"


def unet_weights_present() -> bool:
    return (pneumonia_unet_dir() / "model.safetensors").exists()


def _load_image_array(image_path: Path) -> np.ndarray:
    img = np.asarray(Image.open(image_path).convert("L"), dtype=np.float32)
    if img.max() > 1.0:
        img = img / 255.0
    return img


def _lazy_load_xrv(device: str = "cpu"):
    global _XRV_MODEL, _XRV_TRANSFORM
    if _XRV_MODEL is not None:
        return _XRV_MODEL, _XRV_TRANSFORM
    try:
        import torchxrayvision as xrv
        import torchvision
    except ImportError as exc:
        raise RuntimeError(
            "torchxrayvision required for CXR pathology localization. "
            "Install: pip install torchxrayvision"
        ) from exc

    _XRV_MODEL = xrv.models.DenseNet(weights="densenet121-res224-all")
    _XRV_MODEL.eval()
    _XRV_MODEL.to(device)
    _XRV_TRANSFORM = torchvision.transforms.Compose([
        xrv.datasets.XRayCenterCrop(),
        xrv.datasets.XRayResizer(224),
    ])
    return _XRV_MODEL, _XRV_TRANSFORM


def _import_pneumonia_bundle(root: Path):
    """Load Dimaodessa/pneumonia-cxr custom modules from local snapshot."""
    import importlib.util
    import sys
    import types

    pkg_name = "cxr_pneumonia_hf"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(root)]
        sys.modules[pkg_name] = pkg

    modules: dict[str, object] = {}
    for sub in ("configuration", "unet", "modeling"):
        full = f"{pkg_name}.{sub}"
        path = root / f"{sub}.py"
        spec = importlib.util.spec_from_file_location(full, path, submodule_search_locations=[str(root)])
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load pneumonia module: {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full] = mod
        spec.loader.exec_module(mod)
        modules[sub] = mod
    return modules


def _lazy_load_unet(device: str = "cpu"):
    global _UNET_MODEL
    if _UNET_MODEL is not None:
        return _UNET_MODEL
    root = pneumonia_unet_dir()
    if not unet_weights_present():
        raise FileNotFoundError(
            "CXR U-Net weights missing. Run: python scripts/download_models.py --cxr-lesion"
        )
    try:
        import json
        from safetensors.torch import load_file
    except ImportError as exc:
        raise RuntimeError("safetensors required for CXR U-Net segmentation") from exc

    mods = _import_pneumonia_bundle(root)
    cfg_cls = mods["configuration"].PneumoniaConfig
    model_cls = mods["modeling"].PneumoniaModel
    cfg = cfg_cls(**json.loads((root / "config.json").read_text(encoding="utf-8")))
    model = model_cls(cfg)
    model.load_state_dict(load_file(root / "model.safetensors"))
    model.eval()
    model.to(device)
    _UNET_MODEL = model
    return _UNET_MODEL


def _run_unet_mask(
    image_path: Path,
    lesion: str,
    *,
    device: str = "cpu",
    threshold: float = 0.35,
) -> tuple[np.ndarray, dict]:
    model = _lazy_load_unet(device)
    raw = _load_image_array(image_path)
    h, w = raw.shape
    gray_u8 = (np.clip(raw, 0, 1) * 255).astype(np.uint8)

    with torch.inference_mode():
        tensor = torch.from_numpy(gray_u8).float().unsqueeze(0).unsqueeze(0).to(device)
        out = model(tensor)
        prob = out["mask"].squeeze().detach().cpu().numpy()
        cls_prob = float(out["cls"].squeeze().detach().cpu())

    if prob.shape != (h, w):
        prob = np.asarray(
            Image.fromarray(prob).resize((w, h), Image.BILINEAR),
            dtype=np.float32,
        )
    mask = (prob >= threshold).astype(np.uint8)

    label = CXR_LESION_MAP.get(lesion.lower(), "Lung Opacity")
    logger.info(
        "cxr_unet_done",
        extra={"lesion": label, "cls_prob": round(cls_prob, 3), "pixels": int(mask.sum())},
    )
    return mask, {
        "target_label": label,
        "lesion_probability": cls_prob,
        "segmentation_method": "unet_efficientnetv2_rsna_siim",
        "pretrained_on": "RSNA Pneumonia + SIIM-FISABIO-RSNA (Dimaodessa/pneumonia-cxr)",
        "top_pathologies": [(label, cls_prob)],
    }


def _run_gradcam_mask(
    image_path: Path,
    lesion: str,
    *,
    device: str = "cpu",
    threshold: float = 0.45,
) -> tuple[np.ndarray, dict]:
    image_path = Path(image_path)
    target_label = CXR_LESION_MAP.get(lesion.lower(), CXR_LESION_MAP["opacity"])

    model, transform = _lazy_load_xrv(device)
    raw = _load_image_array(image_path)
    h, w = raw.shape

    tensor = transform(raw)
    tensor = tensor[None, None, :, :].to(device)
    tensor.requires_grad_(True)

    if target_label not in model.pathologies:
        target_label = "Lung Opacity"
    class_idx = model.pathologies.index(target_label)

    activations: dict[str, torch.Tensor] = {}
    gradients: dict[str, torch.Tensor] = {}

    def fwd_hook(_module, _inp, out):
        activations["value"] = out

    def bwd_hook(_module, _gin, gout):
        gradients["value"] = gout[0]

    handle_f = model.features.denseblock4.register_forward_hook(fwd_hook)
    handle_b = model.features.denseblock4.register_full_backward_hook(bwd_hook)

    try:
        logits = model(tensor)
        score = logits[0, class_idx]
        model.zero_grad(set_to_none=True)
        score.backward()

        act = activations["value"][0]
        grad = gradients["value"][0]
        weights = grad.mean(dim=(1, 2))
        cam = torch.zeros(act.shape[1:], device=device)
        for i, w in enumerate(weights):
            cam += w * act[i]
        cam = F.relu(cam)
        cam = cam - cam.min()
        if cam.max() > 0:
            cam = cam / cam.max()
        cam_up = F.interpolate(cam[None, None, :, :], size=(h, w), mode="bilinear", align_corners=False)
        cam_np = cam_up.detach().cpu().numpy()[0, 0]
    finally:
        handle_f.remove()
        handle_b.remove()

    pred_probs = {p: float(logits[0, i].detach().cpu()) for i, p in enumerate(model.pathologies)}
    lesion_prob = float(torch.sigmoid(logits[0, class_idx]).detach().cpu())
    adaptive_thr = max(threshold, 0.35 + 0.25 * (1.0 - lesion_prob))
    mask = (cam_np >= adaptive_thr).astype(np.uint8)

    logger.info(
        "cxr_gradcam_done",
        extra={"lesion": target_label, "prob": round(lesion_prob, 3), "pixels": int(mask.sum())},
    )
    return mask, {
        "target_label": target_label,
        "lesion_probability": lesion_prob,
        "segmentation_method": "gradcam_torchxrayvision",
        "pretrained_on": "NIH/CheXpert/MIMIC-style CXR (torchxrayvision densenet121-res224-all)",
        "top_pathologies": sorted(pred_probs.items(), key=lambda x: x[1], reverse=True)[:5],
    }


def run_cxr_lesion_mask(
    image_path: str | Path,
    lesion: str = "opacity",
    *,
    device: str = "cpu",
    threshold: float = 0.45,
) -> tuple[np.ndarray, dict]:
    """
    Produce a 2D binary lesion mask.
    Opacity-type lesions use RSNA/SIIM U-Net pixel segmentation when weights are present;
    other labels fall back to pathology-specific Grad-CAM localization.
    """
    image_path = Path(image_path)
    key = lesion.lower()

    if key in UNET_LESION_TYPES and unet_weights_present():
        try:
            return _run_unet_mask(image_path, key, device=device, threshold=min(threshold, 0.4))
        except Exception as exc:
            logger.warning("cxr_unet_fallback", extra={"error": str(exc)})

    return _run_gradcam_mask(image_path, key, device=device, threshold=threshold)
