"""Segmentation model registry — doctor selects models in UI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.config import resolve_path

ModelId = Literal["totalsegmentator", "vista3d", "sam_med3d", "sam2d"]
ModalitySupport = Literal["CT", "MRI", "XR", "ALL"]


@dataclass(frozen=True)
class SegModelSpec:
    model_id: ModelId
    name: str
    description: str
    modalities: tuple[ModalitySupport, ...]
    dim: Literal["2d", "3d"]
    local_dir: str
    organs: tuple[str, ...] = ()


MODEL_REGISTRY: dict[ModelId, SegModelSpec] = {
    "totalsegmentator": SegModelSpec(
        model_id="totalsegmentator",
        name="TotalSegmentator",
        description="CT 全器官分割（2D 切片模式，串行推理，fast）",
        modalities=("CT",),
        dim="2d",
        local_dir="models/totalsegmentator",
        organs=("multi_organ",),
    ),
    "vista3d": SegModelSpec(
        model_id="vista3d",
        name="VISTA3D",
        description="MONAI VISTA3D — 脑 / 肝 / 肺 交互式 2D 切片分割",
        modalities=("CT", "MRI"),
        dim="2d",
        local_dir="models/vista3d",
        organs=("brain", "liver", "lung"),
    ),
    "sam_med3d": SegModelSpec(
        model_id="sam_med3d",
        name="SAM-Med3D",
        description="SAM-Med3D Turbo — 医学 3D/2D 切片分割",
        modalities=("CT", "MRI", "ALL"),
        dim="2d",
        local_dir="models/SAM-Med3D",
        organs=("interactive",),
    ),
    "sam2d": SegModelSpec(
        model_id="sam2d",
        name="SAM2D",
        description="SAM2D 纯 2D 视觉分割（点/框提示）",
        modalities=("CT", "MRI", "XR", "ALL"),
        dim="2d",
        local_dir="models/SAM2D",
        organs=("interactive",),
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
            "organs": list(spec.organs),
            "local_dir": spec.local_dir,
            "weights_present": _weights_present(spec.model_id),
        }
        for spec in MODEL_REGISTRY.values()
    ]


def _weights_present(model_id: ModelId) -> bool:
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
