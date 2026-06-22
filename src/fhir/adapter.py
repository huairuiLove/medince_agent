"""FHIR R4 ↔ CPOE adapter: Bundle parsing, review orchestration, response serialization."""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

from fhir.resources.R4B.bundle import Bundle as FhirBundle

from src.drug_catalog.catalog_service import DrugCatalogService, get_drug_catalog_service
from src.drug_catalog.review_facade import CpoeReviewFacade
from src.fhir.coding import (
    ALERT_LEVEL_TO_FHIR_SEVERITY,
    LOINC_PATIENT_FIELD,
    OVERALL_STATUS_TO_OUTCOME,
    SYSTEM_ATC,
    SYSTEM_ICD10,
    SYSTEM_RXNORM,
    SYSTEM_SNOMED,
    act_code_for_category,
    extract_coding_code,
    extract_coding_display,
    resolve_drug_by_atc,
    resolve_drug_by_rxnorm,
    snomed_to_condition_term,
)
from src.fhir.models import FhirAdapterOutput, FhirBundleParseContext, FhirValidationResult
from src.fhir.validation import validate_fhir_bundle
from src.schemas import (
    CpoeMedicationOrder,
    CpoeMedicationReviewRequest,
    CpoeMedicationReviewResponse,
    CpoePatientSnapshot,
    CpoeReviewAlert,
    DrugItem,
)

FHIR_JSON = "application/fhir+json"


class FhirAdapter:
    """Bidirectional adapter between FHIR R4 Bundles and CPOE review models."""

    def __init__(self, catalog: DrugCatalogService | None = None) -> None:
        self.catalog = catalog or get_drug_catalog_service()

    # ── Public API ────────────────────────────────────────────────────────

    def review(self, bundle_data: dict[str, Any] | str, review_facade: CpoeReviewFacade) -> FhirAdapterOutput:
        validation = validate_fhir_bundle(bundle_data)
        if not validation.valid:
            return FhirAdapterOutput(
                bundle=self._validation_error_bundle(validation),
                validation=validation,
            )

        cpoe_request = self.from_fhir_bundle(bundle_data)
        cpoe_response = review_facade.review(cpoe_request)
        bundle = self.to_fhir_bundle(cpoe_response, source_bundle=self._as_dict(bundle_data))
        return FhirAdapterOutput(
            bundle=bundle,
            cpoe_request=cpoe_request,
            cpoe_response=cpoe_response,
            validation=validation,
        )

    def from_fhir_bundle(self, bundle_data: dict[str, Any] | str) -> CpoeMedicationReviewRequest:
        bundle = self._parse_bundle(bundle_data)
        ctx = self._index_bundle(bundle)
        patient = self._find_resource(bundle, "Patient")
        if patient is None:
            raise ValueError("Bundle must contain a Patient resource")

        snapshot = self._patient_to_snapshot(patient, bundle, ctx)
        orders = self._medication_requests_to_orders(bundle, ctx)
        existing = self._existing_medications(bundle, ctx)

        return CpoeMedicationReviewRequest(
            encounter_id=ctx.encounter_id,
            patient=snapshot,
            orders=orders,
            existing_medications=existing,
            review_mode="pre_save",
        )

    def to_fhir_bundle(
        self,
        response: CpoeMedicationReviewResponse,
        *,
        source_bundle: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = self._index_bundle(source_bundle) if source_bundle else FhirBundleParseContext()
        patient_ref = ctx.patient_ref or "Patient/patient"

        entries: list[dict[str, Any]] = []
        for alert in response.alerts:
            entries.append({"resource": self._alert_to_detected_issue(alert, patient_ref, ctx)})

        entries.append({"resource": self._response_to_operation_outcome(response)})

        bundle_id = ctx.bundle_id or f"medsafe-review-{uuid.uuid4().hex[:8]}"
        return {
            "resourceType": "Bundle",
            "id": bundle_id,
            "type": "collection",
            "timestamp": _iso_now(),
            "entry": entries,
        }

    # ── Parsing helpers ─────────────────────────────────────────────────────

    def _parse_bundle(self, bundle_data: dict[str, Any] | str) -> dict[str, Any]:
        raw = self._as_dict(bundle_data)
        return FhirBundle.model_validate(raw).model_dump(mode="json", exclude_none=True)

    def _as_dict(self, bundle_data: dict[str, Any] | str) -> dict[str, Any]:
        if isinstance(bundle_data, str):
            return json.loads(bundle_data)
        if hasattr(bundle_data, "model_dump"):
            return bundle_data.model_dump(mode="json", exclude_none=True)
        return bundle_data

    def _index_bundle(self, bundle: dict[str, Any] | None) -> FhirBundleParseContext:
        if not bundle:
            return FhirBundleParseContext()
        ctx = FhirBundleParseContext(
            bundle_id=str(bundle.get("id") or ""),
            raw_entries=self._entries(bundle),
        )
        patient = self._find_resource(bundle, "Patient")
        if patient and patient.get("id"):
            ctx.patient_id = str(patient["id"])
            ctx.patient_ref = f"Patient/{patient['id']}"
        encounter = self._find_resource(bundle, "Encounter")
        if encounter:
            ctx.encounter_id = str(encounter.get("id") or "")
        for resource in ctx.raw_entries:
            if resource.get("resourceType") == "MedicationRequest" and resource.get("id"):
                ctx.medication_request_refs[str(resource["id"])] = f"MedicationRequest/{resource['id']}"
        return ctx

    def _entries(self, bundle: dict[str, Any]) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        for entry in bundle.get("entry") or []:
            if isinstance(entry, dict) and isinstance(entry.get("resource"), dict):
                resources.append(entry["resource"])
        return resources

    def _find_resource(self, bundle: dict[str, Any], resource_type: str) -> dict[str, Any] | None:
        for resource in self._entries(bundle):
            if resource.get("resourceType") == resource_type:
                return resource
        return None

    def _patient_to_snapshot(
        self,
        patient: dict[str, Any],
        bundle: dict[str, Any],
        ctx: FhirBundleParseContext,
    ) -> CpoePatientSnapshot:
        patient_id = str(patient.get("id") or ctx.patient_id or "")
        gender_map = {"male": "male", "female": "female", "other": "other", "unknown": "unknown"}
        gender = gender_map.get(str(patient.get("gender") or "unknown"), "unknown")

        age = _age_from_birth_date(patient.get("birthDate"))
        allergies = self._allergies_from_bundle(bundle)
        conditions = self._conditions_from_bundle(bundle)
        labs = self._labs_from_bundle(bundle)

        pregnancy = "unknown"
        for ext in patient.get("extension") or []:
            url = str(ext.get("url") or "")
            if "pregnancy" in url.lower():
                val = ext.get("valueCode") or ext.get("valueString")
                if val:
                    pregnancy = str(val)

        return CpoePatientSnapshot(
            patient_id=patient_id,
            age=age,
            gender=gender,
            weight_kg=labs.get("weight_kg"),
            egfr=labs.get("egfr"),
            allergies=allergies,
            conditions=conditions,
            pregnancy_status=pregnancy,
        )

    def _allergies_from_bundle(self, bundle: dict[str, Any]) -> list[str]:
        terms: list[str] = []
        for resource in self._entries(bundle):
            if resource.get("resourceType") != "AllergyIntolerance":
                continue
            code = resource.get("code") or {}
            term = extract_coding_display(code) or snomed_to_condition_term(code)
            if term:
                terms.append(term)
        return terms

    def _conditions_from_bundle(self, bundle: dict[str, Any]) -> list[str]:
        terms: list[str] = []
        for resource in self._entries(bundle):
            if resource.get("resourceType") != "Condition":
                continue
            code = resource.get("code") or {}
            term = extract_coding_display(code)
            if not term:
                term = extract_coding_code(code, SYSTEM_SNOMED) or extract_coding_code(code, SYSTEM_ICD10)
            if term:
                terms.append(term)
        return terms

    def _labs_from_bundle(self, bundle: dict[str, Any]) -> dict[str, float]:
        values: dict[str, float] = {}
        for resource in self._entries(bundle):
            if resource.get("resourceType") != "Observation":
                continue
            loinc = extract_coding_code(resource.get("code"), "http://loinc.org")
            field = LOINC_PATIENT_FIELD.get(loinc)
            if not field:
                continue
            quantity = resource.get("valueQuantity") or {}
            val = quantity.get("value")
            if val is None:
                continue
            try:
                values[field] = float(val)
            except (TypeError, ValueError):
                continue
        return values

    def _medication_requests_to_orders(
        self,
        bundle: dict[str, Any],
        ctx: FhirBundleParseContext,
    ) -> list[CpoeMedicationOrder]:
        orders: list[CpoeMedicationOrder] = []
        for resource in self._entries(bundle):
            if resource.get("resourceType") != "MedicationRequest":
                continue
            order_id = str(resource.get("id") or f"mr-{len(orders) + 1}")
            hospital_id, display = self._resolve_medication(resource, bundle)
            dose, route, frequency = _dosage_from_request(resource)
            orders.append(
                CpoeMedicationOrder(
                    order_id=order_id,
                    hospital_drug_id=hospital_id,
                    display_name=display,
                    dose=dose,
                    route=route,
                    frequency=frequency,
                    status=str(resource.get("status") or "new"),
                )
            )
        return orders

    def _existing_medications(
        self,
        bundle: dict[str, Any],
        ctx: FhirBundleParseContext,
    ) -> list[DrugItem]:
        meds: list[DrugItem] = []
        for resource in self._entries(bundle):
            if resource.get("resourceType") not in {"MedicationStatement", "MedicationAdministration"}:
                continue
            med_concept = resource.get("medicationCodeableConcept") or {}
            if not med_concept and resource.get("medicationReference"):
                med_concept = self._dereference_medication(bundle, resource["medicationReference"])
            hospital_id, display = self._resolve_medication_codeable(med_concept)
            dose, route, frequency = _dosage_from_request(resource)
            meds.append(
                DrugItem(
                    name=display,
                    ingredient="",
                    dose=dose,
                    route=route,
                    frequency=frequency,
                    hospital_drug_id=hospital_id,
                )
            )
        return meds

    def _resolve_medication(
        self,
        request: dict[str, Any],
        bundle: dict[str, Any],
    ) -> tuple[str, str]:
        if request.get("medicationCodeableConcept"):
            return self._resolve_medication_codeable(request["medicationCodeableConcept"])
        if request.get("medicationReference"):
            med = self._dereference_medication(bundle, request["medicationReference"])
            if med:
                return self._resolve_medication_codeable(med.get("code") or med)
        return "", extract_coding_display(request.get("medicationCodeableConcept"))

    def _resolve_medication_codeable(self, codeable: dict[str, Any]) -> tuple[str, str]:
        rxcui = extract_coding_code(codeable, SYSTEM_RXNORM)
        atc = extract_coding_code(codeable, SYSTEM_ATC)
        hospital_id = ""
        display = extract_coding_display(codeable)

        record = None
        if rxcui:
            record = resolve_drug_by_rxnorm(self.catalog, rxcui)
        if record is None and atc:
            record = resolve_drug_by_atc(self.catalog, atc)
        if record is None and display:
            record = self.catalog.resolve_by_name(display)

        if record:
            hospital_id = record.hospital_drug_id
            display = display or record.display_name
        return hospital_id, display

    def _dereference_medication(
        self,
        bundle: dict[str, Any],
        reference: dict[str, Any] | str,
    ) -> dict[str, Any]:
        ref = reference if isinstance(reference, str) else (reference.get("reference") or "")
        ref_id = ref.split("/")[-1] if ref else ""
        for resource in self._entries(bundle):
            if resource.get("resourceType") == "Medication" and resource.get("id") == ref_id:
                return resource
        return {}

    # ── Response serialization ──────────────────────────────────────────────

    def _alert_to_detected_issue(
        self,
        alert: CpoeReviewAlert,
        patient_ref: str,
        ctx: FhirBundleParseContext,
    ) -> dict[str, Any]:
        act_code, act_display = act_code_for_category(alert.category)
        implicated: list[dict[str, str]] = []
        if alert.order_id and alert.order_id in ctx.medication_request_refs:
            implicated.append({"reference": ctx.medication_request_refs[alert.order_id]})
        elif alert.order_id:
            implicated.append({"reference": f"MedicationRequest/{alert.order_id}"})

        issue: dict[str, Any] = {
            "resourceType": "DetectedIssue",
            "id": alert.alert_id or f"di-{uuid.uuid4().hex[:8]}",
            "status": "final",
            "code": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                        "code": act_code,
                        "display": act_display,
                    }
                ],
                "text": alert.category or act_display,
            },
            "severity": ALERT_LEVEL_TO_FHIR_SEVERITY.get(alert.alert_level, "moderate"),
            "patient": {"reference": patient_ref},
            "identified": _iso_now(),
            "detail": alert.summary,
            "extension": [
                {
                    "url": "http://medsafe.local/fhir/StructureDefinition/alert-level",
                    "valueCode": alert.alert_level,
                },
                {
                    "url": "http://medsafe.local/fhir/StructureDefinition/rule-id",
                    "valueString": alert.rule_id,
                },
            ],
        }
        if alert.recommendation:
            issue["mitigation"] = [{"action": {"text": alert.recommendation}}]
        if implicated:
            issue["implicated"] = implicated
        if alert.implicated_drugs:
            issue["evidence"] = [{"detail": [{"display": drug} for drug in alert.implicated_drugs]}]
        return issue

    def _response_to_operation_outcome(self, response: CpoeMedicationReviewResponse) -> dict[str, Any]:
        severity = OVERALL_STATUS_TO_OUTCOME.get(response.overall_status, "information")
        diagnostics = (
            f"overall_status={response.overall_status}; "
            f"alerts={len(response.alerts)}; "
            f"requires_pharmacist_review={response.requires_pharmacist_review}"
        )
        issues: list[dict[str, Any]] = [
            {
                "severity": severity,
                "code": "informational" if severity == "information" else "processing",
                "diagnostics": diagnostics,
            }
        ]
        for drug in response.unresolved_drugs:
            issues.append(
                {
                    "severity": "warning",
                    "code": "not-found",
                    "diagnostics": f"Unresolved drug: {drug}",
                }
            )
        return {
            "resourceType": "OperationOutcome",
            "id": f"oo-{uuid.uuid4().hex[:8]}",
            "issue": issues,
        }

    def _validation_error_bundle(self, validation: FhirValidationResult) -> dict[str, Any]:
        return {
            "resourceType": "Bundle",
            "type": "collection",
            "timestamp": _iso_now(),
            "entry": [
                {
                    "resource": {
                        "resourceType": "OperationOutcome",
                        "issue": [
                            {
                                "severity": issue.severity,
                                "code": issue.code,
                                "diagnostics": issue.diagnostics,
                                **({"expression": [issue.expression]} if issue.expression else {}),
                            }
                            for issue in validation.issues
                        ],
                    }
                }
            ],
        }


def _dosage_from_request(resource: dict[str, Any]) -> tuple[str, str, str]:
    instructions = resource.get("dosageInstruction") or []
    if not instructions:
        return "", "", ""
    inst = instructions[0] if isinstance(instructions[0], dict) else {}
    dose = ""
    dose_rate = (inst.get("doseAndRate") or [{}])[0]
    if isinstance(dose_rate, dict):
        dq = dose_rate.get("doseQuantity") or {}
        if dq.get("value") is not None:
            unit = dq.get("unit") or dq.get("code") or ""
            dose = f"{dq['value']}{unit}"
    if not dose and inst.get("text"):
        dose = str(inst["text"])
    route = ""
    if inst.get("route"):
        route = extract_coding_display(inst["route"])
    frequency = str(inst.get("timing", {}).get("code", {}).get("text") or "")
    return dose, route, frequency


def _age_from_birth_date(birth_date: Any) -> int | None:
    if not birth_date:
        return None
    try:
        parts = str(birth_date).split("-")
        born = date(int(parts[0]), int(parts[1]), int(parts[2][:2]))
        today = date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        return max(age, 0)
    except (ValueError, IndexError):
        return None


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
