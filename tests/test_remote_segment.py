"""Tests for remote segment orchestration and client helpers."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.imaging.backends.base import SegmentResult
from src.imaging.remote_client import RemoteSegmentOutcome, remote_segment_status
from src.imaging.segment_orchestrator import run_segment_with_fallback


@pytest.fixture
def segment_service() -> MagicMock:
    svc = MagicMock()
    svc.segment_serial.return_value = [
        SegmentResult(
            model_id="sam2d",
            source_image="datasets/demo/x.png",
            overlay_path="data/imaging_cache/overlays/x_overlay.png",
            labels=["sam2d"],
        )
    ]
    return svc


def test_remote_segment_status_disabled():
    with patch("src.imaging.remote_client.remote_segment_configured", return_value=False):
        with patch("src.imaging.remote_client.get_remote_segment_config", return_value={
            "enabled": False,
            "base_url": "",
            "fallback_to_local": True,
        }):
            status = remote_segment_status()
    assert status["enabled"] is False
    assert status["reachable"] is False


def test_fallback_to_local_when_remote_fails(segment_service: MagicMock, tmp_path: Path):
    image_abs = tmp_path / "img.png"
    image_abs.write_bytes(b"png")

    remote_fail = RemoteSegmentOutcome(ok=False, error="connection refused")

    cfg = {
        "fallback_to_local": True,
        "local_fallback_device": "cpu",
    }

    with patch("src.imaging.segment_orchestrator.remote_segment_configured", return_value=True):
        with patch("src.imaging.segment_orchestrator.run_remote_segment", return_value=remote_fail):
            with patch("src.imaging.segment_orchestrator.get_remote_segment_config", return_value=cfg):
                results, peak, mode, message, fallback = run_segment_with_fallback(
                    segment_service=segment_service,
                    visual="datasets/demo/x.png",
                    model_ids=["sam2d"],
                    image_abs=image_abs,
                    volume_abs=None,
                    kwargs={"organ": "brain", "device": "cuda"},
                    organ="brain",
                    slice_axis="axial",
                    slice_index=0,
                )

    assert mode == "local"
    assert fallback is True
    assert "本地 CPU" in message
    assert results[0].model_id == "sam2d"
    segment_service.segment_serial.assert_called_once()
    call_kwargs = segment_service.segment_serial.call_args.kwargs
    assert call_kwargs.get("device") == "cpu"


def test_remote_success_skips_local(segment_service: MagicMock, tmp_path: Path):
    image_abs = tmp_path / "img.png"
    image_abs.write_bytes(b"png")
    remote_ok = RemoteSegmentOutcome(
        ok=True,
        results=[
            SegmentResult(
                model_id="sam2d",
                source_image="data/pull/x.png",
                overlay_path="data/pull/x_overlay.png",
            )
        ],
        memory_peak_mb=512.0,
        job_id="job1",
    )

    with patch("src.imaging.segment_orchestrator.remote_segment_configured", return_value=True):
        with patch("src.imaging.segment_orchestrator.run_remote_segment", return_value=remote_ok):
            results, peak, mode, message, fallback = run_segment_with_fallback(
                segment_service=segment_service,
                visual="datasets/demo/x.png",
                model_ids=["sam2d"],
                image_abs=image_abs,
                volume_abs=None,
                kwargs={"organ": "brain"},
                organ="brain",
                slice_axis="axial",
                slice_index=0,
            )

    assert mode == "remote"
    assert fallback is False
    assert "云端 GPU" in message
    assert peak == 512.0
    segment_service.segment_serial.assert_not_called()


def test_remote_fail_without_fallback_raises(segment_service: MagicMock, tmp_path: Path):
    from fastapi import HTTPException

    image_abs = tmp_path / "img.png"
    image_abs.write_bytes(b"png")
    remote_fail = RemoteSegmentOutcome(ok=False, error="timeout")

    with patch("src.imaging.segment_orchestrator.remote_segment_configured", return_value=True):
        with patch("src.imaging.segment_orchestrator.run_remote_segment", return_value=remote_fail):
            with patch(
                "src.imaging.segment_orchestrator.get_remote_segment_config",
                return_value={"fallback_to_local": False},
            ):
                with pytest.raises(HTTPException) as exc:
                    run_segment_with_fallback(
                        segment_service=segment_service,
                        visual="x.png",
                        model_ids=["sam2d"],
                        image_abs=image_abs,
                        volume_abs=None,
                        kwargs={},
                        organ="brain",
                        slice_axis="axial",
                        slice_index=0,
                    )
    assert exc.value.status_code == 503
