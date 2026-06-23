"""Department specialist agent registry coverage."""

from __future__ import annotations

from src.agents.registry import get_agent_registry
from src.config import datasets_path
from src.utils import load_json


def test_all_catalog_departments_have_department_agent() -> None:
    catalog = load_json(datasets_path("departments/catalog.json"))
    dept_ids = {item["dept_id"] for item in catalog.get("departments", []) if item.get("dept_id")}

    covered: set[str] = set()
    for spec in get_agent_registry().list_department_agent_specs():
        for dept in spec.activate_when.get("departments", []):
            covered.add(str(dept).lower())

    missing = sorted(dept_ids - covered)
    assert not missing, f"Departments without department_agents: {missing}"


def test_department_agent_skill_files_exist() -> None:
    registry = get_agent_registry()
    for spec in registry.list_department_agent_specs():
        for skill_id in spec.default_skills:
            path = datasets_path("agents") / spec.agent_id / f"{skill_id}.md"
            assert path.exists(), f"Missing skill file: {path}"
