"""Pydantic models for FHIR adapter I/O (not FHIR resource types themselves)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.schemas import CpoeMedicationReviewRequest, CpoeMedicationReviewResponse


class FhirValidationIssue(BaseModel):
    severity: Literal["fatal", "error", "warning", "information"] = "error"
    code: str = Field(default="structure")
    diagnostics: str
    expression: str = Field(default="")


class FhirValidationResult(BaseModel):
    valid: bool = True
    issues: list[FhirValidationIssue] = Field(default_factory=list)


class FhirBundleParseContext(BaseModel):
    """Intermediate state while parsing an inbound review Bundle."""

    patient_id: str = Field(default="")
    patient_ref: str = Field(default="")
    encounter_id: str = Field(default="")
    bundle_id: str = Field(default="")
    medication_request_refs: dict[str, str] = Field(
        default_factory=dict,
        description="MedicationRequest.id → full reference (e.g. MedicationRequest/mr-1)",
    )
    raw_entries: list[dict[str, Any]] = Field(default_factory=list)


class FhirAdapterInput(BaseModel):
    bundle: dict[str, Any]
    content_type: str = Field(default="application/fhir+json")


class FhirAdapterOutput(BaseModel):
    bundle: dict[str, Any]
    cpoe_request: CpoeMedicationReviewRequest | None = None
    cpoe_response: CpoeMedicationReviewResponse | None = None
    validation: FhirValidationResult = Field(default_factory=FhirValidationResult)


class InteractionTypeConcept(BaseModel):
    code: str
    display: str
    system: str = Field(default="http://terminology.hl7.org/CodeSystem/v3-ActCode")


class InteractionTypeValueSet(BaseModel):
    resource_type: Literal["ValueSet"] = "ValueSet"
    id: str = Field(default="interaction-types")
    url: str = Field(default="http://medsafe.local/fhir/ValueSet/interaction-types")
    name: str = Field(default="MedSafeInteractionTypes")
    title: str = Field(default="MedSafe DDI / safety alert categories")
    status: Literal["active"] = "active"
    compose: dict[str, Any] = Field(default_factory=dict)
