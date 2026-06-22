"""Tertiary-hospital department catalog with imaging / vision model recommendations."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.config import resolve_path
from src.utils import load_json


@dataclass(frozen=True)
class DepartmentSpec:
    dept_id: str
    name_cn: str
    name_en: str
    imaging_sources: tuple[str, ...]
    default_models: tuple[str, ...]
    recommended_datasets: tuple[dict, ...]
    vision_models: tuple[dict, ...]
    nav_routes: tuple[str, ...]
    description: str
    sort_order: int = 0

    def to_dict(self) -> dict:
        return {
            "dept_id": self.dept_id,
            "name_cn": self.name_cn,
            "name_en": self.name_en,
            "imaging_sources": list(self.imaging_sources),
            "default_models": list(self.default_models),
            "recommended_datasets": list(self.recommended_datasets),
            "vision_models": list(self.vision_models),
            "nav_routes": list(self.nav_routes),
            "description": self.description,
            "sort_order": self.sort_order,
        }


CATALOG_PATH = resolve_path("data/departments/catalog.json")


def _parse_dept(raw: dict) -> DepartmentSpec:
    return DepartmentSpec(
        dept_id=raw["dept_id"],
        name_cn=raw["name_cn"],
        name_en=raw.get("name_en", ""),
        imaging_sources=tuple(raw.get("imaging_sources", [])),
        default_models=tuple(raw.get("default_models", [])),
        recommended_datasets=tuple(raw.get("recommended_datasets", [])),
        vision_models=tuple(raw.get("vision_models", [])),
        nav_routes=tuple(raw.get("nav_routes", ["/imaging", "/consult", "/chat", "/rule-review", "/drugs", "/cases", "/agents", "/settings"])),
        description=raw.get("description", ""),
        sort_order=int(raw.get("sort_order", 0)),
    )


def load_department_catalog(path: Path | None = None) -> dict[str, DepartmentSpec]:
    data = load_json(path or CATALOG_PATH)
    return {_parse_dept(item).dept_id: _parse_dept(item) for item in data.get("departments", [])}


def department_rows_for_db(catalog: dict[str, DepartmentSpec]) -> list[dict]:
    rows = []
    for spec in sorted(catalog.values(), key=lambda d: d.sort_order):
        rows.append(
            {
                "dept_id": spec.dept_id,
                "name_cn": spec.name_cn,
                "name_en": spec.name_en,
                "imaging_sources_json": json.dumps(list(spec.imaging_sources), ensure_ascii=False),
                "default_models_json": json.dumps(list(spec.default_models), ensure_ascii=False),
                "recommended_datasets_json": json.dumps(list(spec.recommended_datasets), ensure_ascii=False),
                "vision_models_json": json.dumps(list(spec.vision_models), ensure_ascii=False),
                "nav_routes_json": json.dumps(list(spec.nav_routes), ensure_ascii=False),
                "description": spec.description,
                "sort_order": spec.sort_order,
            }
        )
    return rows
