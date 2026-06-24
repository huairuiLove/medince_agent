"""Imaging full report cache store tests."""

from __future__ import annotations

from pathlib import Path

from src.imaging.report_cache import ImagingReportCacheStore
from src.schemas import ClinicalReport, ReportParagraph


def test_report_cache_roundtrip(tmp_path: Path) -> None:
    store = ImagingReportCacheStore(base_dir=tmp_path)
    report = ClinicalReport(
        report_id="rpt_test",
        user_id="imaging_warm_cache",
        patient_id="p1",
        imaging_session_id="sess_ct_abc",
        modalities=["CT"],
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        paragraphs=[
            ReportParagraph(
                paragraph_id="para1",
                section="clinical_analysis",
                title="临床分析",
                content="test",
                order=1,
            )
        ],
        metadata={"medication_review_ran": True, "final_recommendation": "ok"},
    )
    store.save(report, "mimic_cxr", "s1")
    loaded = store.get("mimic_cxr", "p1", "s1")
    assert loaded is not None
    assert loaded.report_id == "rpt_test"
    assert loaded.metadata.get("medication_review_ran") is True
