"""Clinical report persistence — scoped per doctor (user_id)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from src.auth.ownership import ReportAccessError
from src.config import resolve_path
from src.schemas import ClinicalReport, ReportParagraph, ReportSupplement
from src.utils import ensure_dir, load_json, make_case_id, save_json, utc_now_iso


class ReportStore:
    def __init__(self, report_dir: str | Path | None = None) -> None:
        self.report_dir = Path(report_dir) if report_dir else resolve_path("data/reports")
        ensure_dir(self.report_dir)

    def _user_patient_dir(self, user_id: str, patient_id: str) -> Path:
        d = self.report_dir / user_id / patient_id
        ensure_dir(d)
        return d

    def _report_path(self, user_id: str, patient_id: str, report_id: str) -> Path:
        return self._user_patient_dir(user_id, patient_id) / f"{report_id}.json"

    @staticmethod
    def make_imaging_session_id(modality: str, image_paths: list[str], label: str = "") -> str:
        blob = "|".join(sorted(image_paths)) + f"|{modality}|{label}"
        digest = hashlib.sha256(blob.encode()).hexdigest()[:16]
        return f"sess_{modality.lower()}_{digest}"

    def _assert_owner(self, report: ClinicalReport, user_id: str) -> None:
        if not report.user_id:
            raise ReportAccessError(f"Report {report.report_id} has no owner and is not accessible.")
        if report.user_id != user_id:
            raise ReportAccessError(f"Report {report.report_id} belongs to another user.")

    def find_report_by_session(self, user_id: str, patient_id: str, imaging_session_id: str) -> ClinicalReport | None:
        pdir = self._user_patient_dir(user_id, patient_id)
        for fp in pdir.glob("*.json"):
            report = ClinicalReport.model_validate(load_json(fp))
            if report.imaging_session_id == imaging_session_id and report.status != "superseded":
                return report
        return None

    def save_report(self, report: ClinicalReport) -> ClinicalReport:
        if not report.user_id:
            raise ValueError("ClinicalReport.user_id is required")
        path = self._report_path(report.user_id, report.patient_id, report.report_id)
        save_json(report.model_dump(), path)
        return report

    def get_report(self, user_id: str, patient_id: str, report_id: str) -> ClinicalReport:
        path = self._report_path(user_id, patient_id, report_id)
        if not path.exists():
            raise FileNotFoundError(f"Report {report_id} not found for patient {patient_id}")
        report = ClinicalReport.model_validate(load_json(path))
        self._assert_owner(report, user_id)
        return report

    def list_patient_reports(self, user_id: str, patient_id: str) -> list[ClinicalReport]:
        pdir = self._user_patient_dir(user_id, patient_id)
        if not pdir.exists():
            return []
        reports: list[ClinicalReport] = []
        for fp in sorted(pdir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            report = ClinicalReport.model_validate(load_json(fp))
            if report.user_id == user_id and report.status != "superseded":
                reports.append(report)
        return reports

    def create_or_replace_session_report(
        self,
        user_id: str,
        patient_id: str,
        imaging_session_id: str,
        modalities: list[str],
        paragraphs: list[ReportParagraph],
        chain_of_thought: str,
        image_paths: list[str],
        overlay_paths: list[str],
        screenshot_paths: list[str],
        metadata: dict | None = None,
    ) -> ClinicalReport:
        """Same imaging session → update in place. New session → new report file."""
        existing = self.find_report_by_session(user_id, patient_id, imaging_session_id)
        now = utc_now_iso()

        if existing:
            existing.paragraphs = paragraphs
            existing.chain_of_thought = chain_of_thought
            existing.image_paths = image_paths
            existing.overlay_paths = overlay_paths
            existing.screenshot_paths = screenshot_paths
            existing.modalities = modalities
            existing.updated_at = now
            existing.metadata = {**(existing.metadata or {}), **(metadata or {})}
            return self.save_report(existing)

        report = ClinicalReport(
            report_id=make_case_id("rpt"),
            user_id=user_id,
            patient_id=patient_id,
            imaging_session_id=imaging_session_id,
            modalities=modalities,
            created_at=now,
            updated_at=now,
            paragraphs=paragraphs,
            chain_of_thought=chain_of_thought,
            image_paths=image_paths,
            overlay_paths=overlay_paths,
            screenshot_paths=screenshot_paths,
            metadata=metadata or {},
        )
        return self.save_report(report)

    def append_supplement(
        self,
        user_id: str,
        patient_id: str,
        report_id: str,
        question: str,
        answer: str,
        related_paragraph_ids: list[str] | None = None,
    ) -> ClinicalReport:
        report = self.get_report(user_id, patient_id, report_id)
        report.supplements.append(
            ReportSupplement(
                supplement_id=make_case_id("sup"),
                timestamp=utc_now_iso(),
                question=question,
                answer=answer,
                related_paragraph_ids=related_paragraph_ids or [],
            )
        )
        report.updated_at = utc_now_iso()
        return self.save_report(report)
