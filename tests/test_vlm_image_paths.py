"""VLM image path filtering — exclude NIfTI and invalid rasters."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from src.imaging.volume_io import is_vlm_compatible_image, resolve_vlm_image_paths
from src.llm.vision_client import OpenAIVisionClient


def test_openai_vision_client_encode_image(tmp_path: Path) -> None:
    png = tmp_path / "096052b7-d256dc40.jpg"
    Image.new("RGB", (16, 16), color=(80, 80, 80)).save(png, format="JPEG")
    client = OpenAIVisionClient("sk-test", "https://example.com/v1", "qwen3-vl-plus")
    encoded = client._encode_image(str(png))
    assert encoded["type"] == "image_url"
    assert encoded["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_is_vlm_compatible_image_rejects_nifti(tmp_path: Path) -> None:
    nii = tmp_path / "vol.nii.gz"
    nii.write_bytes(b"\x1f\x8b" + b"\x00" * 20)
    assert is_vlm_compatible_image(nii) is False


def test_resolve_vlm_image_paths_keeps_png_skips_nifti(tmp_path: Path) -> None:
    png = tmp_path / "overlay.png"
    Image.new("RGB", (8, 8), color=(120, 40, 40)).save(png)
    nii = tmp_path / "volume.nii.gz"
    nii.write_bytes(b"\x1f\x8b" + b"\x00" * 20)

    resolved = resolve_vlm_image_paths([str(nii), str(png)])
    assert len(resolved) == 1
    assert resolved[0].endswith("overlay.png")
