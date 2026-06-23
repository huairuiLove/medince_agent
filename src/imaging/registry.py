"""Segmentation model registry — doctor selects models in UI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.config import resolve_path

ModelId = Literal[
    "totalsegmentator",
    "vista3d",
    "sam_med3d",
    "sam2d",
    "cxr_lesion",
    "brats_tumor",
]
ModalitySupport = Literal["CT", "MRI", "XR", "ALL"]
TaskKind = Literal["organ", "lesion", "interactive"]


@dataclass(frozen=True)
class SegModelSpec:
    model_id: ModelId
    name: str
    description: str
    modalities: tuple[ModalitySupport, ...]
    dim: Literal["2d", "3d"]
    local_dir: str
    task: TaskKind = "organ"
    organs: tuple[str, ...] = ()
    datasets: tuple[str, ...] = ()


MODEL_REGISTRY: dict[ModelId, SegModelSpec] = {
    "cxr_lesion": SegModelSpec(
        model_id="cxr_lesion",
        name="CXR Lesion (U-Net + pathology)",
        description="MIMIC 胸片病灶分割 — opacity/pneumonia 用 RSNA U-Net 像素掩膜；effusion/pneumothorax 等用 pathology Grad-CAM",
        modalities=("XR",),
        dim="2d",
        local_dir="models/cxr_lesion",
        task="lesion",
        organs=(
            "opacity",
            "consolidation",
            "pneumonia",
            "atelectasis",
            "edema",
            "cardiomegaly",
            "effusion",
            "pneumothorax",
        ),
        datasets=("mimic_cxr",),
    ),
    "brats_tumor": SegModelSpec(
        model_id="brats_tumor",
        name="BraTS Tumor (MONAI)",
        description="BraTS 胶质瘤病灶 3D 分割 — WT / TC / ET（MONAI brats_mri_segmentation 预训练权重）",
        modalities=("MRI",),
        dim="3d",
        local_dir="models/brats_tumor",
        task="lesion",
        organs=("whole_tumor", "tumor_core", "enhancing_tumor"),
        datasets=("brats2024",),
    ),
    "totalsegmentator": SegModelSpec(
        model_id="totalsegmentator",
        name="TotalSegmentator",
        description="CT 全器官分割（2D 切片模式，串行推理，fast）",
        modalities=("CT",),
        dim="2d",
        local_dir="models/totalsegmentator",
        task="organ",
        organs=("multi_organ",),
        datasets=("mimic", "kits19"),
    ),
    "vista3d": SegModelSpec(
        model_id="vista3d",
        name="VISTA3D",
        description="MONAI VISTA3D — 脑 / 肝 / 肺 交互式 2D 切片分割",
        modalities=("CT", "MRI"),
        dim="2d",
        local_dir="models/vista3d",
        task="organ",
        organs=("brain", "liver", "lung"),
        datasets=("mimic", "brats2024", "kits19"),
    ),
    "sam_med3d": SegModelSpec(
        model_id="sam_med3d",
        name="SAM-Med3D",
        description="SAM-Med3D Turbo — 医学 3D/2D 切片分割",
        modalities=("CT", "MRI", "ALL"),
        dim="2d",
        local_dir="models/SAM-Med3D",
        task="interactive",
        organs=("interactive",),
        datasets=("mimic", "brats2024", "kits19"),
    ),
    "sam2d": SegModelSpec(
        model_id="sam2d",
        name="SAM2D",
        description="SAM2D 纯 2D 视觉分割（点/框提示）",
        modalities=("CT", "MRI", "XR", "ALL"),
        dim="2d",
        local_dir="models/SAM2D",
        task="interactive",
        organs=("interactive",),
        datasets=("mimic", "mimic_cxr", "brats2024", "kits19"),
    ),
}


def model_dir(model_id: ModelId):
    return resolve_path(MODEL_REGISTRY[model_id].local_dir)


def list_models() -> list[dict]:
    return [
        {
            "model_id": spec.model_id,
            "name": spec.name,
            "description": spec.description,
            "modalities": list(spec.modalities),
            "dim": spec.dim,
            "task": spec.task,
            "organs": list(spec.organs),
            "datasets": list(spec.datasets),
            "local_dir": spec.local_dir,
            "weights_present": _weights_present(spec.model_id),
        }
        for spec in MODEL_REGISTRY.values()
    ]


def _weights_present(model_id: ModelId) -> bool:
    if model_id == "cxr_lesion":
        unet = model_dir("cxr_lesion") / "pneumonia_unet" / "model.safetensors"
        if unet.exists():
            return True
        try:
            import torchxrayvision  # noqa: F401
            return True
        except ImportError:
            return False
    if model_id == "brats_tumor":
        return (model_dir("brats_tumor") / "models" / "model.pt").exists()
    d = model_dir(model_id)
    if model_id == "totalsegmentator":
        ts = d / "nnunet" / "results" / "Dataset297_TotalSegmentator_total_3mm_1559subj"
        return ts.exists()
    if not d.exists():
        return False
    files = list(d.rglob("*"))
    return any(f.is_file() and f.suffix in {".pth", ".pt", ".ckpt", ".onnx", ".ts", ".pkl"} for f in files) or any(
        f.is_file() and f.stat().st_size > 1_000_000 for f in files
    )
