"""Shared MONAI bundle inference runner for VISTA3D / BraTS backends."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from src.logging_config import get_logger

logger = get_logger("imaging.monai_bundle")


def run_monai_bundle_inference(
    bundle_root: Path,
    *,
    device: str,
    overrides: dict[str, Any],
    config_name: str = "inference.json",
) -> None:
    """Run a MONAI bundle config with initialize + run/evaluator."""
    bundle_root = bundle_root.resolve()
    config_path = bundle_root / "configs" / config_name
    if not config_path.is_file():
        raise FileNotFoundError(f"MONAI bundle config missing: {config_path}")

    try:
        import torch
        from monai.bundle import run as monai_bundle_run
    except ImportError as exc:
        raise RuntimeError("monai required for bundle inference") from exc

    prev_cwd = os.getcwd()
    inserted = str(bundle_root)
    if inserted not in sys.path:
        sys.path.insert(0, inserted)
    try:
        os.chdir(bundle_root)
        payload = {
            "config_file": str(config_path),
            "init_id": "initialize",
            "run_id": "run",
            "device": str(torch.device(device)),
            **overrides,
        }
        logger.info("monai_bundle_run_start", extra={"bundle": bundle_root.name, "device": device})
        monai_bundle_run(**payload)
    except Exception as primary_exc:
        logger.warning("monai_bundle_run_failed", extra={"error": str(primary_exc)})
        _run_monai_bundle_legacy(bundle_root, config_path, device=device, overrides=overrides)
    finally:
        os.chdir(prev_cwd)


def _run_monai_bundle_legacy(
    bundle_root: Path,
    config_path: Path,
    *,
    device: str,
    overrides: dict[str, Any],
) -> None:
    """Fallback for older MONAI versions or bundles without a top-level run block."""
    import torch
    from monai.bundle import ConfigParser

    parser = ConfigParser()
    parser.read_config(str(config_path))
    parser["device"] = torch.device(device)
    for key, value in overrides.items():
        parser[key] = value

    parser.parse(True)

    init_fn = parser.get_parsed_content("initialize", eval=True)
    if init_fn is not None:
        if not callable(init_fn):
            raise RuntimeError(
                f"MONAI bundle initialize is not callable ({type(init_fn).__name__}). "
                "Check monai / pytorch-ignite versions and bundle weights under models/."
            )
        init_fn()

    evaluator = parser.get_parsed_content("evaluator", instantiate=True)
    if evaluator is None:
        run_block = parser.get_parsed_content("run", eval=True)
        if run_block is None:
            raise RuntimeError(
                "MONAI bundle evaluator/run is None. "
                "Verify models/ bundle files and run: pip install 'monai>=1.4.0' 'pytorch-ignite>=0.5.0'"
            )
        if callable(run_block):
            run_block()
            return
        raise RuntimeError(f"MONAI bundle run block invalid: {type(run_block).__name__}")

    if not hasattr(evaluator, "run"):
        raise RuntimeError(f"MONAI bundle evaluator invalid: {type(evaluator).__name__}")
    evaluator.run()
