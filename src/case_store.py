from __future__ import annotations

from pathlib import Path

from src.auth.ownership import CaseAccessError, assert_case_owner
from src.schemas import CaseEvent, CaseLog
from src.utils import ensure_dir, load_json, make_case_id, save_json, to_jsonable, utc_now_iso


DEFAULT_CASE_DIR = Path(__file__).resolve().parent.parent / "datasets" / "cases"


class CaseStore:
    def __init__(self, case_dir: str | Path = DEFAULT_CASE_DIR) -> None:
        self.case_dir = Path(case_dir)
        ensure_dir(self.case_dir)

    def _case_path(self, case_id: str) -> Path:
        return self.case_dir / f"{case_id}.json"

    def exists(self, case_id: str) -> bool:
        return self._case_path(case_id).exists()

    def create_case(self, case_id: str | None = None, raw_input_text: str = "", user_id: str | None = None) -> CaseLog:
        timestamp = utc_now_iso()
        case = CaseLog(
            case_id=case_id or make_case_id(),
            user_id=user_id,
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

    def upsert_case(
        self,
        case_id: str | None = None,
        patch: dict | None = None,
        stage: str | None = None,
        payload: object | None = None,
        user_id: str | None = None,
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
            case = self.create_case(case_id=case_id, raw_input_text=raw_input_text, user_id=user_id)

        data = case.model_dump()
        if patch:
            data.update(to_jsonable(patch))

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
