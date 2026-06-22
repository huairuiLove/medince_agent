"""FastAPI routes for FHIR R4 medication review integration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from src.drug_catalog.review_facade import CpoeReviewFacade
from src.fhir.adapter import FHIR_JSON, FhirAdapter
from src.fhir.capability import build_capability_statement, build_interaction_types_valueset
from src.logging_config import get_logger

logger = get_logger("fhir")

router = APIRouter(prefix="/api/v1/fhir", tags=["FHIR"])

_adapter: FhirAdapter | None = None
_review_facade: CpoeReviewFacade | None = None
_app_version: str = "3.0.0"


def configure_fhir_routes(
    *,
    review_facade: CpoeReviewFacade,
    adapter: FhirAdapter | None = None,
    version: str = "3.0.0",
) -> None:
    """Bind shared services before mounting the router on the FastAPI app."""
    global _adapter, _review_facade, _app_version
    _review_facade = review_facade
    _adapter = adapter or FhirAdapter(catalog=review_facade.catalog)
    _app_version = version


def create_fhir_router(
    review_facade: CpoeReviewFacade,
    *,
    version: str = "3.0.0",
    adapter: FhirAdapter | None = None,
) -> APIRouter:
    """Return a configured FHIR router (same routes as module-level `router`)."""
    configure_fhir_routes(review_facade=review_facade, adapter=adapter, version=version)
    return router


def _get_adapter() -> FhirAdapter:
    if _adapter is None:
        raise HTTPException(
            status_code=503,
            detail="FHIR routes not configured; call create_fhir_router() or configure_fhir_routes()",
        )
    return _adapter


def _get_review_facade() -> CpoeReviewFacade:
    if _review_facade is None:
        raise HTTPException(status_code=503, detail="CPOE review facade not configured for FHIR routes")
    return _review_facade


def _fhir_response(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=payload, status_code=status_code, media_type=FHIR_JSON)


@router.post(
    "/medication-review",
    summary="FHIR medication review",
    response_class=JSONResponse,
    responses={
        200: {"content": {FHIR_JSON: {}}},
        422: {"content": {FHIR_JSON: {}}},
    },
)
async def fhir_medication_review(request: Request) -> JSONResponse:
    """
    Accept a FHIR R4 Bundle (Patient + MedicationRequest[]) and return
    DetectedIssue resources plus an OperationOutcome summary.
    """
    content_type = request.headers.get("content-type", "")
    if content_type and FHIR_JSON not in content_type and "json" not in content_type:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported Content-Type; expected {FHIR_JSON}",
        )

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc

    adapter = _get_adapter()
    facade = _get_review_facade()
    result = adapter.review(body, facade)

    status = 200 if result.validation.valid else 422
    logger.info(
        "FHIR medication review",
        extra={
            "valid": result.validation.valid,
            "alerts": len(result.cpoe_response.alerts) if result.cpoe_response else 0,
            "status": result.cpoe_response.overall_status if result.cpoe_response else None,
        },
    )
    return _fhir_response(result.bundle, status_code=status)


@router.get(
    "/metadata",
    summary="FHIR CapabilityStatement",
    response_class=JSONResponse,
)
def fhir_metadata(request: Request) -> JSONResponse:
    base_url = str(request.base_url).rstrip("/")
    payload = build_capability_statement(base_url=base_url, version=_app_version)
    return _fhir_response(payload)


@router.get(
    "/ValueSet/interaction-types",
    summary="MedSafe interaction type ValueSet",
    response_class=JSONResponse,
)
def fhir_interaction_types_valueset() -> JSONResponse:
    return _fhir_response(build_interaction_types_valueset())
