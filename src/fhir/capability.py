"""CapabilityStatement generation for MedSafe FHIR endpoints."""

from __future__ import annotations

from typing import Any


def build_capability_statement(*, base_url: str, version: str = "3.0.0", fhir_version: str = "4.0.1") -> dict[str, Any]:
    """Build a FHIR R4 CapabilityStatement describing supported operations."""
    base = base_url.rstrip("/")
    return {
        "resourceType": "CapabilityStatement",
        "status": "active",
        "date": _iso_now(),
        "publisher": "MedSafe",
        "kind": "instance",
        "software": {
            "name": "MedSafe Drug Safety API",
            "version": version,
        },
        "implementation": {
            "description": "MedSafe hospital medication safety review (CPOE integration)",
            "url": base,
        },
        "fhirVersion": fhir_version,
        "format": ["json", "application/fhir+json"],
        "rest": [
            {
                "mode": "server",
                "documentation": "Medication review via FHIR Bundle adapter",
                "security": {
                    "cors": True,
                    "description": "Configure MEDSAFE_CORS_ORIGINS for production",
                },
                "resource": [
                    {
                        "type": "Bundle",
                        "interaction": [{"code": "search-type"}],
                        "operation": [
                            {
                                "name": "medication-review",
                                "definition": f"{base}/api/v1/fhir/medication-review",
                            }
                        ],
                    },
                    {
                        "type": "DetectedIssue",
                        "interaction": [{"code": "read"}],
                    },
                    {
                        "type": "OperationOutcome",
                        "interaction": [{"code": "read"}],
                    },
                    {
                        "type": "ValueSet",
                        "interaction": [{"code": "read"}],
                    },
                ],
                "interaction": [
                    {"code": "transaction"},
                ],
                "operation": [
                    {
                        "name": "medication-review",
                        "definition": f"{base}/OperationDefinition/medsafe-medication-review",
                    }
                ],
            }
        ],
    }


def build_interaction_types_valueset() -> dict[str, Any]:
    from src.fhir.coding import INTERACTION_TYPE_CONCEPTS, SYSTEM_ACT_CODE

    return {
        "resourceType": "ValueSet",
        "id": "interaction-types",
        "url": "http://medsafe.local/fhir/ValueSet/interaction-types",
        "version": "1.0.0",
        "name": "MedSafeInteractionTypes",
        "title": "MedSafe safety alert categories (ActCode)",
        "status": "active",
        "compose": {
            "include": [
                {
                    "system": SYSTEM_ACT_CODE,
                    "concept": [{"code": c["code"], "display": c["display"]} for c in INTERACTION_TYPE_CONCEPTS],
                }
            ]
        },
    }


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
