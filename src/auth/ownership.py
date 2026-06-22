from __future__ import annotations

from src.schemas import CaseLog


class CaseAccessError(PermissionError):
    """Raised when a user attempts to access another user's case."""


class ReportAccessError(PermissionError):
    """Raised when a user attempts to access another user's report."""


def assert_case_owner(case: CaseLog, user_id: str) -> None:
    if not case.user_id:
        raise CaseAccessError(f"Case {case.case_id} has no owner and is not accessible.")
    if case.user_id != user_id:
        raise CaseAccessError(f"Case {case.case_id} belongs to another user.")
