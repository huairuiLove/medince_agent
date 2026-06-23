"""Case template coverage for all catalog departments."""

from __future__ import annotations

from src.case_templates import (
    departments_missing_primary_templates,
    departments_missing_templates,
    list_case_templates,
)
from src.config import datasets_path
from src.utils import load_json


def test_all_catalog_departments_have_case_template() -> None:
    missing = departments_missing_templates()
    assert not missing, f"Departments without case templates: {missing}"


def test_all_catalog_departments_have_primary_template() -> None:
    missing = departments_missing_primary_templates()
    assert not missing, f"Departments without dept_*_01 primary template: {missing}"


def test_department_templates_are_rule_review_ready() -> None:
    """Each primary template must expose patient_context for RuleReviewView."""
    catalog = load_json(datasets_path("departments/catalog.json"))
    dept_ids = [item["dept_id"] for item in catalog.get("departments", []) if item.get("dept_id")]

    for dept_id in dept_ids:
        tpls = list_case_templates(dept_id)
        primary = next((t for t in tpls if t.id == f"dept_{dept_id}_01"), None)
        assert primary is not None, f"Missing primary template for {dept_id}"
        assert primary.input_mode == "context"
        assert primary.patient_context is not None
        assert primary.patient_context.department == dept_id
