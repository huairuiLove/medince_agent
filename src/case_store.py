from __future__ import annotations

from pathlib import Path

from src.auth.ownership import CaseAccessError, assert_case_owner
from src.department.context import get_department_context
from src.schemas import CaseEvent, CaseLog, CaseSummary
from src.utils import ensure_dir, load_json, make_case_id, save_json, to_jsonable, utc_now_iso


DEFAULT_CASE_DIR = Path(__file__).resolve().parent.parent / "datasets" / "cases"


def resolve_case_department(data: dict) -> str:
    dept = str(data.get("department") or "").strip()
    if dept:
        return dept
    patient = data.get("patient_context")
    if isinstance(patient, dict):
        return str(patient.get("department") or "").strip()
    return ""


def department_name_cn(dept_id: str) -> str:
    dept_id = (dept_id or "").strip()
    if not dept_id:
        return ""
    ctx = get_department_context(dept_id)
    return ctx.name_cn if ctx else dept_id


class CaseStore:
    def __init__(self, case_dir: str | Path = DEFAULT_CASE_DIR) -> None:
        self.case_dir = Path(case_dir)
        ensure_dir(self.case_dir)

    def _case_path(self, case_id: str) -> Path:
        return self.case_dir / f"{case_id}.json"

    def exists(self, case_id: str) -> bool:
        return self._case_path(case_id).exists()

    def create_case(
        self,
        case_id: str | None = None,
        raw_input_text: str = "",
        user_id: str | None = None,
        department: str = "",
    ) -> CaseLog:
        timestamp = utc_now_iso()
        dept = (department or "").strip()
        case = CaseLog(
            case_id=case_id or make_case_id(),
            user_id=user_id or "",
            department=dept,
            department_name_cn=department_name_cn(dept),
            created_at=timestamp,
            updated_at=timestamp,
            raw_input_text=raw_input_text,
        )
        self.save_case(case)
        return case

    def get_case(self, case_id: str) -> CaseLog:
        path = self._case_path(case_id)
        if not path.exists():
            raise FileNotFoundError(f"Case {case_id} not found.")
        return CaseLog.model_validate(load_json(path))

    def get_case_for_user(self, case_id: str, user_id: str) -> CaseLog:
        case = self.get_case(case_id)
        assert_case_owner(case, user_id)
        return case

    def save_case(self, case: CaseLog) -> None:
        save_json(case.model_dump(), self._case_path(case.case_id))

    def list_case_ids(self, user_id: str, limit: int = 20) -> list[str]:
        files = sorted(self.case_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        ids: list[str] = []
        for path in files:
            if len(ids) >= limit:
                break
            try:
                data = load_json(path)
                if data.get("user_id") == user_id:
                    ids.append(path.stem)
            except (OSError, ValueError, TypeError):
                continue
        return ids

    def list_case_summaries(
        self,
        *,
        department: str,
        limit: int = 50,
        multi_agent_only: bool = True,
    ) -> list[CaseSummary]:
        dept_filter = (department or "").strip()
        if not dept_filter:
            return []

        files = sorted(self.case_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        summaries: list[CaseSummary] = []
        for path in files:
            if len(summaries) >= limit:
                break
            try:
                data = load_json(path)
            except (OSError, ValueError, TypeError):
                continue

            case_dept = resolve_case_department(data)
            if case_dept != dept_filter:
                continue

            agent_opinions = data.get("agent_opinions") or []
            if multi_agent_only and not agent_opinions:
                continue

            summaries.append(
                CaseSummary(
                    case_id=str(data.get("case_id") or path.stem),
                    department=case_dept,
                    department_name_cn=str(data.get("department_name_cn") or "") or department_name_cn(case_dept),
                    status=str(data.get("status") or "in_progress"),
                    created_at=str(data.get("created_at") or ""),
                    updated_at=str(data.get("updated_at") or ""),
                    final_recommendation=str(data.get("final_recommendation") or "")[:160],
                    agent_count=len(agent_opinions),
                )
            )
        return summaries

    def upsert_case(
        self,
        case_id: str | None = None,
        patch: dict | None = None,
        stage: str | None = None,
        payload: object | None = None,
        user_id: str | None = None,
        department: str = "",
    ) -> CaseLog:
        if case_id and self.exists(case_id):
            case = self.get_case(case_id)
            if user_id:
                if case.user_id and case.user_id != user_id:
                    raise CaseAccessError(f"Case {case_id} belongs to another user.")
        else:
            raw_input_text = ""
            if patch and patch.get("raw_input_text"):
                raw_input_text = str(patch["raw_input_text"])
            resolved_dept = (department or "").strip()
            if not resolved_dept and patch:
                resolved_dept = resolve_case_department(patch)
            case = self.create_case(
                case_id=case_id,
                raw_input_text=raw_input_text,
                user_id=user_id,
                department=resolved_dept,
            )

        data = case.model_dump()
        if patch:
            data.update(to_jsonable(patch))

        resolved_dept = resolve_case_department(data)
        if resolved_dept:
            data["department"] = resolved_dept
            data["department_name_cn"] = department_name_cn(resolved_dept)
            patient = data.get("patient_context")
            if isinstance(patient, dict) and not patient.get("department"):
                patient["department"] = resolved_dept
                data["patient_context"] = patient

        if user_id and not data.get("user_id"):
            data["user_id"] = user_id

        if stage and payload is not None:
            events = data.get("events", [])
            events.append(
                CaseEvent(
                    stage=stage,
                    timestamp=utc_now_iso(),
                    payload=to_jsonable(payload),
                ).model_dump()
            )
            data["events"] = events

        data["updated_at"] = utc_now_iso()
        updated_case = CaseLog.model_validate(data)
        self.save_case(updated_case)
        return updated_case
