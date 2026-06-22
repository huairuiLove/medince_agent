"""FHIR R4 adapter layer for MedSafe CPOE medication review."""

from src.fhir.adapter import FhirAdapter
from src.fhir.capability import build_capability_statement
from src.fhir.models import FhirValidationResult
from src.fhir.routes import create_fhir_router, router

__all__ = [
    "FhirAdapter",
    "FhirValidationResult",
    "build_capability_statement",
    "create_fhir_router",
    "router",
]
