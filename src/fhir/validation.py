"""FHIR Bundle validation for medication review requests."""

from __future__ import annotations

from typing import Any

from fhir.resources.R4B.bundle import Bundle as FhirBundle

from src.fhir.models import FhirValidationIssue, FhirValidationResult


def _bundle_as_dict(bundle_data: dict[str, Any] | str | Any) -> dict[str, Any]:
    if isinstance(bundle_data, str):
        import json

        bundle_data = json.loads(bundle_data)
    if hasattr(bundle_data, "model_dump"):
        return bundle_data.model_dump(mode="json", exclude_none=True)
    if not isinstance(bundle_data, dict):
        raise TypeError("Expected FHIR Bundle as dict, JSON string, or fhir.resources Bundle")
    return bundle_data


def _parse_bundle(bundle_data: dict[str, Any]) -> tuple[dict[str, Any], FhirValidationResult]:
    issues: list[FhirValidationIssue] = []
    if bundle_data.get("resourceType") != "Bundle":
        issues.append(
            FhirValidationIssue(
                severity="fatal",
                code="invalid",
                diagnostics="resourceType must be Bundle",
            )
        )
        return bundle_data, FhirValidationResult(valid=False, issues=issues)

    bundle_type = bundle_data.get("type")
    if bundle_type and bundle_type not in {"collection", "document", "transaction", "batch"}:
        issues.append(
            FhirValidationIssue(
                severity="warning",
                code="not-supported",
                diagnostics=f"Unexpected Bundle.type '{bundle_type}'; expected collection",
                expression="Bundle.type",
            )
        )

    FhirBundle.model_validate(bundle_data)

    return bundle_data, FhirValidationResult(valid=not any(i.severity == "fatal" for i in issues), issues=issues)


def _entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for entry in bundle.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        resource = entry.get("resource")
        if isinstance(resource, dict):
            entries.append(resource)
    return entries


def validate_fhir_bundle(bundle_data: dict[str, Any] | str | Any) -> FhirValidationResult:
    """Validate inbound Bundle for medication review."""
    raw = _bundle_as_dict(bundle_data)
    _, parse_result = _parse_bundle(raw)
    issues = list(parse_result.issues)

    if any(i.severity == "fatal" for i in issues):
        return FhirValidationResult(valid=False, issues=issues)

    resources = _entries(raw)
    patients = [r for r in resources if r.get("resourceType") == "Patient"]
    med_requests = [r for r in resources if r.get("resourceType") == "MedicationRequest"]

    if not patients:
        issues.append(
            FhirValidationIssue(
                severity="error",
                code="required",
                diagnostics="Bundle must contain at least one Patient resource",
                expression="Bundle.entry.resource.where(resourceType='Patient')",
            )
        )

    if not med_requests:
        issues.append(
            FhirValidationIssue(
                severity="error",
                code="required",
                diagnostics="Bundle must contain at least one MedicationRequest",
                expression="Bundle.entry.resource.where(resourceType='MedicationRequest')",
            )
        )

    patient_ids = {p.get("id") for p in patients if p.get("id")}
    for idx, mr in enumerate(med_requests):
        subject = (mr.get("subject") or {}).get("reference") or ""
        if not subject:
            issues.append(
                FhirValidationIssue(
                    severity="error",
                    code="required",
                    diagnostics=f"MedicationRequest[{idx}] missing subject.reference",
                    expression=f"Bundle.entry[{idx}].resource.subject",
                )
            )
            continue
        ref_id = subject.split("/")[-1] if "/" in subject else subject.lstrip("#")
        if patient_ids and ref_id not in patient_ids and not subject.startswith("#"):
            issues.append(
                FhirValidationIssue(
                    severity="warning",
                    code="not-found",
                    diagnostics=f"MedicationRequest subject '{subject}' not found among Bundle Patients",
                    expression=f"Bundle.entry[{idx}].resource.subject",
                )
            )

        has_med = bool(mr.get("medicationCodeableConcept") or mr.get("medicationReference"))
        if not has_med:
            issues.append(
                FhirValidationIssue(
                    severity="error",
                    code="required",
                    diagnostics=f"MedicationRequest[{idx}] requires medicationCodeableConcept or medicationReference",
                    expression=f"Bundle.entry[{idx}].resource.medication",
                )
            )

    valid = not any(i.severity in {"fatal", "error"} for i in issues)
    return FhirValidationResult(valid=valid, issues=issues)
