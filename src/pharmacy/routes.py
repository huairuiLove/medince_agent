"""FastAPI routes for the pharmacy workbench."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from src.auth.dependencies import get_current_user
from src.auth.models import UserProfile
from src.pharmacy.models import (
    AlertDecision,
    AuditListResponse,
    DecideAlertRequest,
    PharmacistReview,
    PharmacyStatsResponse,
    QueueListResponse,
    SubmitReviewRequest,
)
from src.pharmacy.override_audit import OverrideAuditStore, make_audit_log
from src.pharmacy.queue import PHARMACY_QUEUE
from src.pharmacy.stats import PharmacyStatsService

router = APIRouter(tags=["Pharmacy"])

_audit_store = OverrideAuditStore()
_stats_service = PharmacyStatsService()


def require_pharmacy_user(
    user: Annotated[UserProfile, Depends(get_current_user)],
) -> UserProfile:
    if user.role not in {"admin", "pharmacist"}:
        raise HTTPException(status_code=403, detail="需要药师或管理员权限")
    return user


PharmacyUser = Annotated[UserProfile, Depends(require_pharmacy_user)]


@router.get("/queue", response_model=QueueListResponse)
def list_queue(
    user: PharmacyUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query("pending"),
) -> QueueListResponse:
    del user
    return PHARMACY_QUEUE.list_queue(page=page, page_size=page_size, status=status)


@router.get("/review/{review_id}", response_model=PharmacistReview)
def get_review(review_id: str, user: PharmacyUser) -> PharmacistReview:
    del user
    review = PHARMACY_QUEUE.get_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail=f"Review not found: {review_id}")
    return review


@router.post("/review/{review_id}/decide", response_model=PharmacistReview)
def decide_alert(
    review_id: str,
    body: DecideAlertRequest,
    user: PharmacyUser,
) -> PharmacistReview:
    review = PHARMACY_QUEUE.get_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail=f"Review not found: {review_id}")
    if review.status != "pending":
        raise HTTPException(status_code=409, detail="Review is no longer pending")

    alert_ids = {a.alert_id for a in review.cpoe_response.alerts}
    if body.alert_id not in alert_ids:
        raise HTTPException(status_code=400, detail=f"Unknown alert_id: {body.alert_id}")

    now = datetime.now(timezone.utc)
    decision = AlertDecision(
        alert_id=body.alert_id,
        action=body.action,
        override_reason=body.override_reason,
        override_risk_acceptance=body.override_risk_acceptance,
        pharmacist_notes=body.pharmacist_notes,
        decided_at=now,
        pharmacist_id=user.user_id,
    )
    PHARMACY_QUEUE.store.upsert_decision(review_id, decision)

    if body.action in {"override", "escalate"}:
        alert = next(a for a in review.cpoe_response.alerts if a.alert_id == body.alert_id)
        drug_name = alert.display_name or (alert.implicated_drugs[0] if alert.implicated_drugs else "")
        _audit_store.append_log(
            make_audit_log(
                review_id=review_id,
                alert_id=body.alert_id,
                order_id=alert.order_id,
                drug_name=drug_name,
                alert_level=alert.alert_level,
                alert_summary=alert.summary,
                pharmacist_id=user.user_id,
                pharmacist_name=user.display_name or user.username,
                department=user.dept_id,
                action=body.action,
                override_reason=body.override_reason or "",
                risk_acceptance=body.override_risk_acceptance or "",
                timestamp=now,
                supervisor_reviewed=alert.alert_level == "hard_stop" and body.action == "override",
            )
        )
        _stats_service.bump_pharmacist_stats(
            user.user_id,
            override=body.action == "override",
            escalation=body.action == "escalate",
        )

    updated = PHARMACY_QUEUE.get_review(review_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to reload review")
    return updated


@router.post("/review/{review_id}/submit", response_model=PharmacistReview)
def submit_review(
    review_id: str,
    body: SubmitReviewRequest,
    user: PharmacyUser,
) -> PharmacistReview:
    review = PHARMACY_QUEUE.get_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail=f"Review not found: {review_id}")
    if review.status != "pending":
        raise HTTPException(status_code=409, detail="Review is no longer pending")

    required_alert_ids = {a.alert_id for a in review.cpoe_response.alerts}
    decided_ids = {d.alert_id for d in review.alert_decisions}
    missing = required_alert_ids - decided_ids
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"All alerts must have a decision before submit; missing: {sorted(missing)}",
        )

    if body.notes:
        for decision in review.alert_decisions:
            if not decision.pharmacist_notes:
                decision.pharmacist_notes = body.notes
                PHARMACY_QUEUE.store.upsert_decision(review_id, decision)

    updated = PHARMACY_QUEUE.store.mark_reviewed(review_id, user.user_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to finalize review")

    _stats_service.bump_pharmacist_stats(user.user_id, review_completed=True)
    return updated


@router.get("/audit", response_model=AuditListResponse)
def list_audit_logs(
    user: PharmacyUser,
    start_date: str | None = None,
    end_date: str | None = None,
    pharmacist_id: str | None = None,
    drug_name: str | None = None,
    alert_level: str | None = None,
    action: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> AuditListResponse:
    del user
    return _audit_store.query_logs(
        start_date=start_date,
        end_date=end_date,
        pharmacist_id=pharmacist_id,
        drug_name=drug_name,
        alert_level=alert_level,
        action=action,
        page=page,
        page_size=page_size,
    )


@router.get("/audit/export")
def export_audit_logs(
    user: PharmacyUser,
    start_date: str | None = None,
    end_date: str | None = None,
    pharmacist_id: str | None = None,
    drug_name: str | None = None,
    alert_level: str | None = None,
    action: str | None = None,
) -> PlainTextResponse:
    del user
    csv_text = _audit_store.export_csv(
        start_date=start_date,
        end_date=end_date,
        pharmacist_id=pharmacist_id,
        drug_name=drug_name,
        alert_level=alert_level,
        action=action,
    )
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="override_audit.csv"'},
    )


@router.get("/stats", response_model=PharmacyStatsResponse)
def pharmacy_stats(user: PharmacyUser) -> PharmacyStatsResponse:
    del user
    return _stats_service.overview()
