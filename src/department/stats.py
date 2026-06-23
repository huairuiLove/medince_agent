"""In-memory department review statistics (per-server process)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass
class _DeptCounters:
    reviews_today: int = 0
    alerts_today: int = 0
    alert_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    day_key: str = ""


class DepartmentStatsTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._by_dept: dict[str, _DeptCounters] = {}

    def _today_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _counters(self, dept_id: str) -> _DeptCounters:
        dept_id = dept_id or "unknown"
        today = self._today_key()
        counters = self._by_dept.setdefault(dept_id, _DeptCounters(day_key=today))
        if counters.day_key != today:
            counters.reviews_today = 0
            counters.alerts_today = 0
            counters.alert_counts = defaultdict(int)
            counters.day_key = today
        return counters

    def record_review(self, dept_id: str, alert_count: int, alert_summaries: list[str]) -> None:
        with self._lock:
            c = self._counters(dept_id)
            c.reviews_today += 1
            c.alerts_today += alert_count
            for summary in alert_summaries[:20]:
                key = summary[:80] if summary else "unknown"
                c.alert_counts[key] += 1

    def snapshot(self, dept_id: str, pending_queue: int = 0, overrides_today: int = 0) -> dict[str, Any]:
        with self._lock:
            c = self._counters(dept_id)
            top = sorted(c.alert_counts.items(), key=lambda x: -x[1])[:5]
            return {
                "dept_id": dept_id,
                "reviews_today": c.reviews_today,
                "alerts_today": c.alerts_today,
                "overrides_today": overrides_today,
                "pending_queue": pending_queue,
                "top_alerts": [{"summary": k, "count": v} for k, v in top],
            }


_tracker: DepartmentStatsTracker | None = None


def get_department_stats_tracker() -> DepartmentStatsTracker:
    global _tracker
    if _tracker is None:
        _tracker = DepartmentStatsTracker()
    return _tracker
