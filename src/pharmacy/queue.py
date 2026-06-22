"""Pharmacy review queue — enqueue and list pending reviews."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.pharmacy.models import PharmacistReview, QueueItem, QueueListResponse
from src.pharmacy.review_store import ReviewStore, _parse_dt
from src.schemas import CpoeMedicationReviewResponse


class PharmacyQueue:
    def __init__(self, store: ReviewStore | None = None) -> None:
        self.store = store or ReviewStore()

    def enqueue(
        self,
        *,
        encounter_id: str,
        patient_id: str,
        cpoe_response: CpoeMedicationReviewResponse,
        department: str = "unknown",
        ordering_user_id: str = "",
    ) -> PharmacistReview:
        return self.store.create_review(
            encounter_id=encounter_id,
            patient_id=patient_id,
            department=department,
            cpoe_response=cpoe_response,
            ordering_user_id=ordering_user_id,
        )

    def list_queue(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = "pending",
    ) -> QueueListResponse:
        rows, total = self.store.list_pending(page=page, page_size=page_size, status=status)
        now = datetime.now(timezone.utc)
        items: list[QueueItem] = []
        for row in rows:
            cpoe = CpoeMedicationReviewResponse.model_validate(json.loads(row["cpoe_response_json"]))
            created = _parse_dt(row["created_at"]) or now
            wait_minutes = max((now - created).total_seconds() / 60.0, 0.0)
            items.append(
                QueueItem(
                    review_id=row["review_id"],
                    encounter_id=row["encounter_id"],
                    patient_id=row["patient_id"],
                    department=row["department"],
                    created_at=created,
                    status=row["status"],
                    max_alert_level=row["max_alert_level"],
                    alert_count=len(cpoe.alerts),
                    wait_minutes=round(wait_minutes, 1),
                )
            )
        return QueueListResponse(items=items, total=total, page=page, page_size=page_size)

    def get_review(self, review_id: str) -> PharmacistReview | None:
        return self.store.get_review(review_id)


PHARMACY_QUEUE = PharmacyQueue()
