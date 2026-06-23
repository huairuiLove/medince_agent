"""Centralized configuration loader for MedSafe.

Loads config.yaml and overlays environment variables (MEDSAFE_* prefix).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
_CONFIG: dict[str, Any] | None = None


def _load_raw_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _env_override(config: dict[str, Any], prefix: str = "MEDSAFE_") -> dict[str, Any]:
    """Override config values from environment variables.

    Environment variables use double-underscore as nested separator:
      MEDSAFE_SERVER__PORT=8080  ->  config["server"]["port"] = 8080
      MEDSAFE_MODEL__BASE_MODEL=...  ->  config["model"]["base_model"] = ...
    """
    import copy
    result = copy.deepcopy(config)

    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        trimmed = key[len(prefix):].lower()
        parts = trimmed.split("__")
        if len(parts) < 1:
            continue

        # navigate to the nested dict
        node = result
        for part in parts[:-1]:
            if part not in node:
                node[part] = {}
            node = node[part]

        # coerce types
        leaf_key = parts[-1]
        if isinstance(value, str):
            if value.lower() in {"true", "yes", "1"}:
                value = True  # type: ignore[assignment]
            elif value.lower() in {"false", "no", "0"}:
                value = False  # type: ignore[assignment]
            else:
                try:
                    value = int(value)  # type: ignore[assignment]
                except ValueError:
                    try:
                        value = float(value)  # type: ignore[assignment]
                    except ValueError:
                        pass
        node[leaf_key] = value

    return result


def load_config(config_path: str | Path | None = None, reload: bool = False) -> dict[str, Any]:
    """Load (and cache) the project configuration."""
    global _CONFIG
    if _CONFIG is not None and not reload:
        return _CONFIG
    try:
        from dotenv import load_dotenv
        load_dotenv(_DEFAULT_CONFIG_PATH.parent / ".env")
    except ImportError:
        pass
    _CONFIG = _env_override(_load_raw_config(config_path))
    return _CONFIG


def get_config() -> dict[str, Any]:
    """Get the current config (must call load_config first)."""
    if _CONFIG is None:
        return load_config()
    return _CONFIG


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def datasets_dir_name() -> str:
    return str(get_config().get("paths", {}).get("datasets_dir", "datasets"))


def datasets_path(relative: str = "") -> Path:
    """Resolve a path under the datasets root (static / reference data)."""
    base = project_root() / datasets_dir_name()
    return base / relative if relative else base


def data_path(relative: str = "") -> Path:
    """Resolve a path under data/ (runtime DBs, cache, processing scripts)."""
    base = project_root() / "data"
    return base / relative if relative else base


def resolve_path(relative: str) -> Path:
    """Resolve a path relative to the project root."""
    return project_root() / relative
