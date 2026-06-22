"""Pharmacy workbench Pydantic models."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.schemas import CpoeMedicationReviewResponse

ReviewStatus = Literal["pending", "reviewed", "expired"]
AlertAction = Literal["acknowledge", "override", "escalate", "hold"]
RiskAcceptance = Literal["low", "medium", "high"]


class AlertDecision(BaseModel):
    alert_id: str
    action: AlertAction
    override_reason: str | None = None
    override_risk_acceptance: RiskAcceptance | None = None
    pharmacist_notes: str | None = None
    decided_at: datetime
    pharmacist_id: str = Field(default="")


class PharmacistReview(BaseModel):
    review_id: str
    encounter_id: str = Field(default="")
    patient_id: str = Field(default="")
    pharmacist_id: str | None = None
    department: str = Field(default="")
    ordering_user_id: str = Field(default="")
    created_at: datetime
    reviewed_at: datetime | None = None
    status: ReviewStatus = "pending"
    cpoe_response: CpoeMedicationReviewResponse
    alert_decisions: list[AlertDecision] = Field(default_factory=list)
    max_alert_level: str = Field(default="info")


class OverrideAuditLog(BaseModel):
    log_id: str
    review_id: str
    alert_id: str
    order_id: str = Field(default="")
    drug_name: str = Field(default="")
    alert_level: str = Field(default="")
    alert_summary: str = Field(default="")
    pharmacist_id: str
    pharmacist_name: str = Field(default="")
    department: str = Field(default="")
    action: str
    override_reason: str = Field(default="")
    risk_acceptance: str = Field(default="")
    timestamp: datetime
    patient_outcome: str | None = None
    supervisor_reviewed: bool = False
    supervisor_id: str | None = None


class QueueItem(BaseModel):
    review_id: str
    encounter_id: str = Field(default="")
    patient_id: str = Field(default="")
    department: str = Field(default="")
    created_at: datetime
    status: ReviewStatus = "pending"
    max_alert_level: str = Field(default="info")
    alert_count: int = 0
    wait_minutes: float = 0.0


class DecideAlertRequest(BaseModel):
    alert_id: str = Field(min_length=1)
    action: AlertAction
    override_reason: str | None = None
    override_risk_acceptance: RiskAcceptance | None = None
    pharmacist_notes: str | None = None

    @model_validator(mode="after")
    def validate_override_fields(self) -> DecideAlertRequest:
        if self.action == "override":
            if not (self.override_reason or "").strip():
                raise ValueError("override_reason is required when action is override")
            if self.override_risk_acceptance is None:
                raise ValueError("override_risk_acceptance is required when action is override")
        return self


class SubmitReviewRequest(BaseModel):
    notes: str | None = None


class QueueListResponse(BaseModel):
    items: list[QueueItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class AuditQueryParams(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    pharmacist_id: str | None = None
    drug_name: str | None = None
    alert_level: str | None = None
    action: str | None = None
    page: int = 1
    page_size: int = 50


class AuditListResponse(BaseModel):
    items: list[OverrideAuditLog] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50


class PharmacyStatsResponse(BaseModel):
    pending_count: int = 0
    reviewed_today: int = 0
    reviewed_week: int = 0
    override_rate: float = 0.0
    high_risk_override_rate: float = 0.0
    top_override_drugs: list[dict] = Field(default_factory=list)
    by_pharmacist: list[dict] = Field(default_factory=list)
