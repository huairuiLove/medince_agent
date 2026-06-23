"""Case replay listing and department scoping."""

from __future__ import annotations

import json
from pathlib import Path

from src.case_store import (
    CaseStore,
    case_visible_to_user,
    infer_case_kind,
    is_replayable_case,
)


def test_is_replayable_case_accepts_imaging_and_multi_agent() -> None:
    assert is_replayable_case({"case_kind": "imaging_vlm"})
    assert is_replayable_case({"vlm_analysis": {"clinical_analysis": "x"}})
    assert is_replayable_case({"agent_opinions": [{"agent_id": "a"}]})
    assert not is_replayable_case({"review_output": {"alerts": []}})


def test_case_visible_to_user_matches_department_or_legacy_owner(tmp_path: Path) -> None:
    data = {"department": "respiratory", "user_id": "u1"}
    assert case_visible_to_user(data, department="respiratory", user_id="u1")
    assert not case_visible_to_user(data, department="neurology", user_id="u1")

    legacy = {"user_id": "u1", "agent_opinions": [{}]}
    assert case_visible_to_user(legacy, department="respiratory", user_id="u1")
    assert not case_visible_to_user(legacy, department="respiratory", user_id="u2")


def test_list_case_summaries_includes_legacy_user_cases(tmp_path: Path) -> None:
    store = CaseStore(case_dir=tmp_path)
    legacy_path = tmp_path / "case_legacy.json"
    legacy_path.write_text(
        json.dumps(
            {
                "case_id": "case_legacy",
                "user_id": "usr_a",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "agent_opinions": [{"agent_id": "clinical_pharmacist"}],
                "final_recommendation": "legacy consult",
            }
        ),
        encoding="utf-8",
    )
    imaging_path = tmp_path / "case_img.json"
    imaging_path.write_text(
        json.dumps(
            {
                "case_id": "case_img",
                "department": "respiratory",
                "case_kind": "imaging_vlm",
                "created_at": "2026-01-02T00:00:00+00:00",
                "updated_at": "2026-01-02T00:00:00+00:00",
                "vlm_analysis": {"clinical_analysis": "nodule"},
                "final_recommendation": "影像 VLM 查阅完成",
            }
        ),
        encoding="utf-8",
    )

    summaries = store.list_case_summaries(department="respiratory", user_id="usr_a", limit=10)
    ids = {s.case_id for s in summaries}
    assert "case_legacy" in ids
    assert "case_img" in ids
    assert infer_case_kind({"case_kind": "imaging_vlm"}) == "imaging_vlm"
