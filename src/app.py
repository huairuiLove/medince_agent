"""MedSafe API Server — Multi-agent drug safety review via LLM API."""
from __future__ import annotations

import asyncio
import glob
import os
import time
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from src.agents.extract_agent import ExtractAgent
from src.case_store import CaseStore
from src.case_templates import CaseTemplateListResponse, get_case_template, list_case_templates
from src.mimic_store import get_mimic_store
from src.clarify_engine import ClarifyEngine
from src.config import load_config
from src.llm.client import get_llm_client, is_llm_configured
from src.llm.embedding_client import embedding_status
from src.llm.errors import LLMNotConfiguredError, VisionLLMError
from src.logging_config import get_logger, setup_logging
from src.orchestrator import MultiAgentOrchestrator
from src.drug_catalog.catalog_service import (
    bootstrap_catalog_from_config,
    ensure_semantic_index_if_needed,
    get_drug_catalog_service,
)
from src.department.context import get_department_context
from src.department.stats import get_department_stats_tracker
from src.drug_catalog.review_facade import CpoeReviewFacade
from src.auth.dependencies import get_current_user, get_optional_user
from src.auth.models import (
    CreateCustomSkillRequest,
    DepartmentsListResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UpdateAgentPrefsRequest,
    UpdateSkillPrefsRequest,
    UserProfile,
)
from src.auth.service import get_auth_service
from src.auth.imaging_scope import (
    allowed_model_ids,
    filter_models,
    filter_studies,
    imaging_sources_for_user,
    path_allowed_for_sources,
    study_allowed_for_sources,
)
from src.fhir.routes import create_fhir_router
from src.pharmacy import PHARMACY_QUEUE
from src.pharmacy.routes import router as pharmacy_router
from src.schemas import (
    CandidateDrug,
    ClarifyRequest,
    ClarifyResponse,
    ClinicalReport,
    ConsultRequest,
    ConsultResponse,
    CpoeMedicationReviewRequest,
    CpoeMedicationReviewResponse,
    DepartmentContextResponse,
    DepartmentStatsResponse,
    FormularySyncRequest,
    FormularySyncResponse,
    DiagnosisItem,
    DrugItem,
    ExtractRequest,
    ExtractResponse,
    ExtractionOutput,
    GenerateReportRequest,
    ListSegmentRunsResponse,
    MultiConsultRequest,
    MultiConsultResponse,
    MultiReviewRequest,
    MultiReviewResponse,
    MimicDataStatsResponse,
    MimicPatientListResponse,
    PatientContext,
    ReportAskRequest,
    ReportAskResponse,
    ReviewRequest,
    ReviewResponse,
    SaveScreenshotRequest,
    SegmentRequest,
    SegmentResponse,
    VlmAnalyzeRequest,
    VlmAnalyzeResponse,
)
from src.imaging.catalog import ImagingCatalog
from src.imaging.memory_monitor import rss_mb
from src.imaging.segment_service import SegmentService
from src.imaging.segment_store import SegmentStore, make_image_key
from src.imaging.volume_io import decode_base64_image, export_volume_slice, get_volume_meta, is_nifti
from src.llm.vision_client import (
    BAILIAN_CONSOLE_URL,
    get_qwen_vlm_client,
    get_vision_llm_settings,
    is_vision_llm_configured,
)
from src.reports.report_generator import ReportGenerator, dedupe_paths
from src.reports.report_qa import ReportQAService
from src.reports.report_store import ReportStore
from src.config import resolve_path
from src.react.chat_service import chat_event_stream, init_chat_services, shutdown_chat_services
from src.react.schemas import ChatRequest, SystemState
from src.react.state_machine import state_machine
from src.react.tool_registry import tool_registry
from src.safety_models.ddi_classifier import get_ddi_classifier
from src.safety_models.med7_extractor import get_med7_extractor

VERSION = "3.0.0"

DESCRIPTION = """
MedSafe — 基于 MIMIC-III 场景的多智能体用药安全审查系统。

## 核心流程
- **Extract** — LLM API 从病历文本抽取结构化信息
- **Rule Gate** — 确定性规则库预筛（硬安全底线）
- **Multi-Agent Review** — 临床药师 / 内科主治 / 过敏专员 / 药房库管 / 专科医生
- **Arbitration** — 会诊主席汇总仲裁
- **Clarify** — 信息协调员追问补全
"""

logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    log_cfg = cfg.get("logging", {})
    setup_logging(
        level=log_cfg.get("level", "INFO"),
        log_format=log_cfg.get("format", "console"),
        log_dir=log_cfg.get("log_dir"),
        log_file=log_cfg.get("log_file", "medsafe.log"),
    )
    try:
        if is_llm_configured():
            llm = get_llm_client()
            logger.info("MedSafe API ready", extra={"version": VERSION, "llm": type(llm).__name__})
        else:
            logger.warning(
                "MedSafe API ready — LLM not configured (rule/CPOE/imaging-segment only)",
                extra={"version": VERSION},
            )
    except LLMNotConfiguredError as exc:
        logger.warning("MedSafe API ready — LLM unavailable", extra={"error": str(exc)})
    await init_chat_services()
    try:
        sync_result = bootstrap_catalog_from_config()
        if sync_result:
            logger.info(
                "Drug catalog bootstrapped from CSV",
                extra={"rows": sync_result.get("rows_upserted"), "version": sync_result.get("sync_version")},
            )
    except Exception as exc:
        logger.warning("Drug catalog bootstrap skipped", extra={"error": str(exc)})

    async def _build_semantic_index() -> None:
        try:
            index_status = ensure_semantic_index_if_needed()
            if index_status and index_status.get("index_built"):
                logger.info(
                    "Drug semantic index ready",
                    extra={"indexed_drugs": index_status.get("indexed_drugs")},
                )
        except Exception as exc:
            logger.warning("Drug semantic index skipped", extra={"error": str(exc)})

    semantic_task = asyncio.create_task(_build_semantic_index())
    yield
    semantic_task.cancel()
    with suppress(asyncio.CancelledError):
        await semantic_task
    await shutdown_chat_services()
    logger.info("MedSafe API shutdown")


app = FastAPI(
    title="MedSafe - Multi-Agent Drug Safety Assistant",
    description=DESCRIPTION,
    version=VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "Health", "description": "Health check and metrics"},
        {"name": "Extract", "description": "LLM structured extraction"},
        {"name": "Review", "description": "Rule-based drug safety review"},
        {"name": "Clarify", "description": "Clarification and missing-field follow-up"},
        {"name": "Multi-Agent", "description": "Multi-agent consult pipeline"},
        {"name": "Consult", "description": "Legacy rule-only consult pipeline"},
        {"name": "Cases", "description": "Case log management and replay"},
        {"name": "Imaging", "description": "Segmentation, screenshots, clinical reports"},
        {"name": "Chat", "description": "ReAct SSE chat with role-based prompts (doctor/patient)"},
        {"name": "CPOE", "description": "Hospital formulary sync and CPOE medication review"},
        {"name": "FHIR", "description": "FHIR R4 medication review adapter (Bundle ↔ CPOE)"},
        {"name": "Auth", "description": "Login, registration, and user profile"},
        {"name": "Pharmacy", "description": "Pharmacist workbench queue, override audit, stats"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("MEDSAFE_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CASE_STORE = CaseStore()
MIMIC_STORE = get_mimic_store()
DRUG_CATALOG = get_drug_catalog_service()
CPOE_REVIEW = CpoeReviewFacade(catalog=DRUG_CATALOG)
REVIEW_ENGINE = CPOE_REVIEW.review_engine
CLARIFY_ENGINE = ClarifyEngine()
ORCHESTRATOR = MultiAgentOrchestrator()
_extract_agent: ExtractAgent | None = None
IMAGING_CATALOG = ImagingCatalog()
SEGMENT_SERVICE = SegmentService()
SEGMENT_STORE = SegmentStore()
REPORT_GENERATOR = ReportGenerator()
REPORT_STORE = ReportStore()
REPORT_QA = ReportQAService()

_SERVER_START = time.time()
_REQUEST_COUNTS: dict[str, int] = {
    "extract": 0, "review": 0, "clarify": 0, "consult": 0,
    "multi_review": 0, "multi_consult": 0, "case_get": 0,
    "imaging_segment": 0, "imaging_vlm": 0, "report_generate": 0, "report_ask": 0, "chat_stream": 0,
    "cpoe_review": 0, "formulary_sync": 0, "fhir_review": 0, "department_context": 0,
}
DEPT_STATS = get_department_stats_tracker()

app.include_router(create_fhir_router(CPOE_REVIEW, version=VERSION))
app.include_router(pharmacy_router, prefix="/api/v1/pharmacy")


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(duration_ms, 2),
        },
    )
    return response


def build_patient_context_from_extraction(text: str, extraction: ExtractionOutput) -> PatientContext:
    return PatientContext(
        source_text=text,
        gender=extraction.gender,
        age=extraction.age,
        symptoms_or_complaints=list(extraction.symptoms_or_complaints),
        chief_complaint=extraction.symptoms_or_complaints[0] if extraction.symptoms_or_complaints else "",
        diagnoses=[DiagnosisItem(name=d) for d in extraction.diagnoses],
        current_medications=[DrugItem(name=m) for m in extraction.current_medications],
        allergies=list(extraction.allergies),
        pregnancy_status=extraction.pregnancy_status,
        missing_fields=list(extraction.missing_fields),
    )


def get_extract_agent() -> ExtractAgent:
    global _extract_agent
    if _extract_agent is None:
        _extract_agent = ExtractAgent(get_llm_client())
    return _extract_agent


def run_extract(text: str) -> tuple[str, ExtractionOutput | None]:
    return get_extract_agent().extract(text)


@app.exception_handler(LLMNotConfiguredError)
async def llm_not_configured_handler(_request: Request, exc: LLMNotConfiguredError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(VisionLLMError)
async def vision_llm_error_handler(_request: Request, exc: VisionLLMError):
    status = exc.status_code if exc.status_code in {401, 403, 429} else 502
    return JSONResponse(status_code=status, content={"detail": str(exc)})


# ── Health ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
def health() -> dict:
    catalog_stats = DRUG_CATALOG.stats()
    cfg = load_config()
    llm_cfg = cfg.get("llm", {})
    llm_provider = str(llm_cfg.get("provider", "") or "").strip()
    if not llm_provider:
        llm_provider = "configured" if is_llm_configured() else "未配置"
    return {
        "status": "ok",
        "version": VERSION,
        "uptime_seconds": round(time.time() - _SERVER_START, 1),
        "llm_configured": is_llm_configured(),
        "llm_provider": llm_provider,
        "vision_llm_configured": is_vision_llm_configured(),
        "drug_catalog": {
            "loaded": DRUG_CATALOG.is_loaded(),
            "total_drugs": catalog_stats.get("total_drugs", 0),
        },
        "safety_models": {
            "med7": get_med7_extractor().status(),
            "ddi_bert": get_ddi_classifier().status(),
        },
        "embedding": embedding_status(),
    }


@app.get("/metrics", tags=["Health"])
def metrics() -> dict:
    return {
        "uptime_seconds": round(time.time() - _SERVER_START, 1),
        "requests": _REQUEST_COUNTS,
        "total_requests": sum(_REQUEST_COUNTS.values()),
    }


@app.get("/api/v1/agents", tags=["Multi-Agent"])
def list_agents() -> dict:
    return {"agents": ORCHESTRATOR.list_agents()}


@app.get("/api/v1/case-templates", response_model=CaseTemplateListResponse, tags=["Cases"])
def api_list_case_templates(
    department: str = "",
    user: UserProfile | None = Depends(get_optional_user),
) -> CaseTemplateListResponse:
    dept = department.strip() or (user.dept_id if user else "")
    if not dept:
        return CaseTemplateListResponse(templates=[])
    return CaseTemplateListResponse(templates=list_case_templates(dept))


@app.get("/api/v1/case-templates/{template_id}", tags=["Cases"])
def api_get_case_template(template_id: str) -> dict:
    tpl = get_case_template(template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"Case template {template_id} not found.")
    return tpl.model_dump()


@app.get("/api/v1/mimic/stats", response_model=MimicDataStatsResponse, tags=["MIMIC"])
def api_mimic_stats() -> MimicDataStatsResponse:
    return MIMIC_STORE.stats()


@app.get("/api/v1/mimic/patients", response_model=MimicPatientListResponse, tags=["MIMIC"])
def api_mimic_patients(
    offset: int = 0,
    limit: int = 25,
    gender: Optional[str] = None,
    min_medications: int = 0,
) -> MimicPatientListResponse:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")
    if not MIMIC_STORE.is_processed_available():
        raise HTTPException(
            status_code=503,
            detail="MIMIC-III patient contexts not built. Run: python -m src.cli build-mimic",
        )
    return MIMIC_STORE.list_patients(
        offset=offset,
        limit=limit,
        gender=gender,
        min_medications=min_medications,
    )


@app.get("/api/v1/mimic/patients/{subject_id}/{hadm_id}", response_model=PatientContext, tags=["MIMIC"])
def api_mimic_patient(subject_id: int, hadm_id: int) -> PatientContext:
    if not MIMIC_STORE.is_processed_available():
        raise HTTPException(
            status_code=503,
            detail="MIMIC-III patient contexts not built. Run: python -m src.cli build-mimic",
        )
    ctx = MIMIC_STORE.get_patient(subject_id, hadm_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Admission {subject_id}/{hadm_id} not in processed index.")
    return ctx


# ── Extract ────────────────────────────────────────────────────────────

@app.post("/api/v1/extract", response_model=ExtractResponse, tags=["Extract"])
@app.post("/api/extract", response_model=ExtractResponse, tags=["Extract"], include_in_schema=False)
def extract_info(req: ExtractRequest, request: Request) -> ExtractResponse:
    _REQUEST_COUNTS["extract"] += 1
    raw_output, extraction = run_extract(req.text)
    parsed = extraction.model_dump() if extraction else None
    case_id = req.case_id
    if req.persist and extraction:
        case = CASE_STORE.upsert_case(
            case_id=case_id,
            patch={
                "raw_input_text": req.text,
                "extract_output": extraction.model_dump(),
                "patient_context": build_patient_context_from_extraction(req.text, extraction).model_dump(),
            },
            stage="extract",
            payload={"raw_output": raw_output, "parsed": parsed},
        )
        case_id = case.case_id
    return ExtractResponse(case_id=case_id, raw_output=raw_output, parsed_output=parsed)


# ── Rule Review ──────────────────────────────────────────────────────────

@app.post("/api/v1/review", response_model=ReviewResponse, tags=["Review"])
@app.post("/api/review", response_model=ReviewResponse, tags=["Review"], include_in_schema=False)
def review_case(req: ReviewRequest, request: Request) -> ReviewResponse:
    _REQUEST_COUNTS["review"] += 1
    review_output = REVIEW_ENGINE.review(req.patient_context, req.candidate_drugs, req.retrieved_evidence)
    response = ReviewResponse(
        case_id=req.case_id,
        retrieved_evidence=review_output.evidence,
        review_output=review_output,
    )
    if req.persist:
        case = CASE_STORE.upsert_case(
            case_id=req.case_id,
            patch={
                "patient_context": req.patient_context.model_dump(),
                "candidate_drugs": [d.model_dump() for d in req.candidate_drugs],
                "review_output": review_output.model_dump(),
                "final_recommendation": review_output.final_recommendation,
            },
            stage="rule_gate",
            payload=review_output.model_dump(),
        )
        response.case_id = case.case_id
    return response


# ── CPOE / Hospital Formulary ────────────────────────────────────────────

@app.get("/api/v1/auth/departments", response_model=DepartmentsListResponse, tags=["Auth"])
def auth_list_departments() -> DepartmentsListResponse:
    return DepartmentsListResponse(departments=get_auth_service().list_departments())


@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["Auth"])
def auth_login(body: LoginRequest) -> TokenResponse:
    result = get_auth_service().login(body.username, body.password)
    if result is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return result


@app.post("/api/v1/auth/register", tags=["Auth"])
def auth_register(body: RegisterRequest) -> dict:
    svc = get_auth_service()
    profile = svc.register(body.username, body.password, body.display_name, body.dept_id)
    if profile is None:
        raise HTTPException(status_code=400, detail="注册失败：用户名已存在或科室无效")
    token = svc.login(body.username, body.password)
    if token is None:
        raise HTTPException(status_code=500, detail="注册成功但登录失败")
    workspace = svc.get_workspace(profile.user_id)
    if workspace is None:
        raise HTTPException(status_code=500, detail="注册成功但工作区初始化失败")
    return {
        "access_token": token.access_token,
        "token_type": "bearer",
        "expires_in_hours": token.expires_in_hours,
        "profile": workspace.profile,
        "agents": workspace.agents,
        "custom_skills": workspace.custom_skills,
    }


@app.get("/api/v1/auth/me", tags=["Auth"])
def auth_me(user: Annotated[UserProfile, Depends(get_current_user)]) -> dict:
    workspace = get_auth_service().get_workspace(user.user_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return workspace.model_dump()


@app.put("/api/v1/auth/agent-prefs", tags=["Auth"])
def auth_update_agent_prefs(
    body: UpdateAgentPrefsRequest,
    user: Annotated[UserProfile, Depends(get_current_user)],
) -> dict:
    svc = get_auth_service()
    svc.update_agent_prefs(user.user_id, body.agents)
    workspace = svc.get_workspace(user.user_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return workspace.model_dump()


@app.put("/api/v1/auth/skill-prefs", tags=["Auth"])
def auth_update_skill_prefs(
    body: UpdateSkillPrefsRequest,
    user: Annotated[UserProfile, Depends(get_current_user)],
) -> dict:
    svc = get_auth_service()
    svc.update_skill_prefs(user.user_id, body.skills)
    workspace = svc.get_workspace(user.user_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return workspace.model_dump()


@app.post("/api/v1/auth/custom-skills", tags=["Auth"])
def auth_add_custom_skill(
    body: CreateCustomSkillRequest,
    user: Annotated[UserProfile, Depends(get_current_user)],
) -> dict:
    return get_auth_service().add_custom_skill(user.user_id, body)


@app.get("/api/v1/department/context", response_model=DepartmentContextResponse, tags=["Department"])
def department_context(
    dept_id: str = "",
    user: Annotated[UserProfile | None, Depends(get_optional_user)] = None,
) -> DepartmentContextResponse:
    """Return review_config and core_formulary for a department."""
    _REQUEST_COUNTS["department_context"] += 1
    resolved = dept_id.strip() or (user.dept_id if user else "")
    ctx = get_department_context(resolved)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Unknown department: {resolved}")
    data = ctx.to_dict()
    return DepartmentContextResponse(**data)


@app.get("/api/v1/department/stats", response_model=DepartmentStatsResponse, tags=["Department"])
def department_stats(
    dept_id: str = "",
    user: Annotated[UserProfile | None, Depends(get_optional_user)] = None,
) -> DepartmentStatsResponse:
    resolved = dept_id.strip() or (user.dept_id if user else "unknown")
    pending = 0
    try:
        pending_row = PHARMACY_QUEUE.store.conn.execute(
            "SELECT COUNT(*) AS c FROM pharmacist_reviews WHERE status = 'pending' AND department = ?",
            (resolved,),
        ).fetchone()
        pending = int(pending_row["c"]) if pending_row else 0
    except Exception:
        pending = 0
    snap = DEPT_STATS.snapshot(resolved, pending_queue=pending)
    return DepartmentStatsResponse(**snap)


@app.post("/api/v1/cpoe/medication-review", response_model=CpoeMedicationReviewResponse, tags=["CPOE"])
def cpoe_medication_review(
    req: CpoeMedicationReviewRequest,
    request: Request,
    user: Annotated[UserProfile | None, Depends(get_optional_user)] = None,
) -> CpoeMedicationReviewResponse:
    """Real-time medication review for CPOE — resolves hospital drug IDs via formulary CSV."""
    _REQUEST_COUNTS["cpoe_review"] += 1
    if not req.department.strip() and user:
        req = req.model_copy(update={"department": user.dept_id})
    response = CPOE_REVIEW.review(req)
    dept_id = req.department or (user.dept_id if user else "unknown")
    DEPT_STATS.record_review(
        dept_id,
        alert_count=len(response.alerts),
        alert_summaries=[a.summary for a in response.alerts],
    )
    if response.requires_pharmacist_review:
        PHARMACY_QUEUE.enqueue(
            encounter_id=req.encounter_id,
            patient_id=req.patient.patient_id,
            cpoe_response=response,
            department=user.dept_id if user else "unknown",
            ordering_user_id=user.user_id if user else "",
        )
    return response


@app.get("/api/v1/drug-catalog/stats", tags=["CPOE"])
def drug_catalog_stats() -> dict:
    return DRUG_CATALOG.stats()


@app.get("/api/v1/drug-catalog/drugs/{hospital_drug_id}", tags=["CPOE"])
def drug_catalog_lookup(hospital_drug_id: str) -> dict:
    record = DRUG_CATALOG.get_by_id(hospital_drug_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Drug not found: {hospital_drug_id}")
    return record.to_dict()


@app.get("/api/v1/drug-catalog/drugs/{hospital_drug_id}/alternatives", tags=["CPOE"])
def drug_catalog_alternatives(hospital_drug_id: str) -> dict:
    alts = DRUG_CATALOG.list_alternatives(hospital_drug_id)
    return {
        "hospital_drug_id": hospital_drug_id,
        "count": len(alts),
        "alternatives": [a.to_dict() for a in alts],
    }


@app.get("/api/v1/drug-catalog/browse", tags=["CPOE"])
def drug_catalog_browse(
    atc_prefix: str = "",
    filter_id: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return DRUG_CATALOG.browse(
        atc_prefix=atc_prefix,
        filter_id=filter_id,
        limit=min(limit, 200),
        offset=offset,
    )


@app.get("/api/v1/drug-catalog/classification", tags=["CPOE"])
def drug_catalog_classification(max_level: int = 4) -> dict:
    return DRUG_CATALOG.classification_tree(max_level=max_level)


@app.get("/api/v1/drug-catalog/search-model/status", tags=["CPOE"])
def drug_catalog_search_model_status() -> dict:
    return DRUG_CATALOG.search_model_status()


@app.post("/api/v1/drug-catalog/search-model/rebuild", tags=["CPOE"])
def drug_catalog_search_model_rebuild() -> dict:
    from src.llm.errors import DrugSearchModelNotReadyError

    try:
        DRUG_CATALOG._ensure_semantic_index()
        return DRUG_CATALOG.search_model_status()
    except DrugSearchModelNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/drug-catalog/search", tags=["CPOE"])
def drug_catalog_search(q: str, limit: int = 20, mode: str = "semantic") -> dict:
    results, effective_mode = DRUG_CATALOG.search(q, limit=min(limit, 100), mode=mode)
    return {
        "query": q,
        "mode": effective_mode,
        "count": len(results),
        "results": [r.to_dict() for r in results],
    }


@app.post("/api/v1/drug-catalog/sync", response_model=FormularySyncResponse, tags=["CPOE"])
def drug_catalog_sync(req: FormularySyncRequest, request: Request) -> FormularySyncResponse:
    """Import/replace formulary from PIS CSV export."""
    _REQUEST_COUNTS["formulary_sync"] += 1
    from src.drug_catalog.csv_import import FormularyCsvImporter

    cfg = load_config()
    csv_rel = req.csv_path or cfg.get("drug_catalog", {}).get("formulary_path", "datasets/hospital/formulary_sample.csv")
    csv_path = resolve_path(csv_rel)
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"CSV not found: {csv_rel}")

    global DRUG_CATALOG, CPOE_REVIEW, REVIEW_ENGINE
    try:
        result = FormularyCsvImporter(DRUG_CATALOG.db_path).import_csv(
            csv_path,
            sync_version=req.sync_version or None,
        )
        DRUG_CATALOG = get_drug_catalog_service(reload=True)
        CPOE_REVIEW = CpoeReviewFacade(catalog=DRUG_CATALOG)
        REVIEW_ENGINE = CPOE_REVIEW.review_engine
        return FormularySyncResponse(
            status=result["status"],
            sync_version=result["sync_version"],
            rows_total=result["rows_total"],
            rows_upserted=result["rows_upserted"],
            source_path=result["source_path"],
            catalog_stats=DRUG_CATALOG.stats(),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/clarify", response_model=ClarifyResponse, tags=["Clarify"])
@app.post("/api/clarify", response_model=ClarifyResponse, tags=["Clarify"], include_in_schema=False)
def clarify_case(req: ClarifyRequest, request: Request) -> ClarifyResponse:
    _REQUEST_COUNTS["clarify"] += 1
    clarify_output = CLARIFY_ENGINE.clarify(
        patient_context=req.patient_context,
        candidate_drugs=req.candidate_drugs,
        review_output=req.review_output,
        user_answers=req.user_answers,
        unable_to_answer=req.unable_to_answer,
    )
    response = ClarifyResponse(case_id=req.case_id, clarify_output=clarify_output)
    if req.persist:
        case = CASE_STORE.upsert_case(
            case_id=req.case_id,
            patch={"clarify_output": clarify_output.model_dump()},
            stage="clarify",
            payload=clarify_output.model_dump(),
        )
        response.case_id = case.case_id
    return response


# ── Multi-Agent ──────────────────────────────────────────────────────────

@app.post("/api/v1/multi-review", response_model=MultiReviewResponse, tags=["Multi-Agent"])
def multi_review(req: MultiReviewRequest, request: Request) -> MultiReviewResponse:
    _REQUEST_COUNTS["multi_review"] += 1
    result = ORCHESTRATOR.run(
        req.patient_context, req.candidate_drugs, unable_to_answer=req.unable_to_answer
    )
    if req.persist:
        case = CASE_STORE.upsert_case(
            case_id=req.case_id,
            patch={
                "patient_context": req.patient_context.model_dump(),
                "candidate_drugs": [d.model_dump() for d in req.candidate_drugs],
                "review_output": result.rule_output.model_dump(),
                "agent_opinions": [o.model_dump() for o in result.agent_opinions],
                "debate": result.debate.model_dump() if result.debate else None,
                "safety_panel": result.safety_panel.model_dump() if result.safety_panel else None,
                "arbitration": result.arbitration.model_dump(),
                "clarify_output": result.clarify_output.model_dump() if result.clarify_output else None,
                "final_recommendation": result.final_recommendation,
                "status": "complete",
            },
            stage="agent_review",
            payload={"agent_count": len(result.agent_opinions)},
        )
        if result.debate:
            CASE_STORE.upsert_case(
                case_id=case.case_id,
                stage="debate",
                payload=result.debate.model_dump(),
            )
        if result.safety_panel:
            CASE_STORE.upsert_case(
                case_id=case.case_id,
                stage="safety_panel",
                payload=result.safety_panel.model_dump(),
            )
        CASE_STORE.upsert_case(case_id=case.case_id, stage="arbitration", payload=result.arbitration.model_dump())
        if result.clarify_output:
            CASE_STORE.upsert_case(case_id=case.case_id, stage="clarify", payload=result.clarify_output.model_dump())
        CASE_STORE.upsert_case(case_id=case.case_id, stage="final", payload={"final_recommendation": result.final_recommendation})
        result.case_id = case.case_id
    return result


@app.post("/api/v1/multi-consult", response_model=MultiConsultResponse, tags=["Multi-Agent"])
def multi_consult(req: MultiConsultRequest, request: Request) -> MultiConsultResponse:
    _REQUEST_COUNTS["multi_consult"] += 1
    patient_context = req.patient_context
    extraction = None
    case_id = req.case_id

    if patient_context is None:
        if not req.text:
            raise HTTPException(status_code=400, detail="Either text or patient_context must be provided.")
        raw_output, extraction = run_extract(req.text)
        if extraction is None:
            raise HTTPException(status_code=422, detail="Failed to parse LLM extract output.")
        patient_context = build_patient_context_from_extraction(req.text, extraction)
        if req.persist:
            case = CASE_STORE.upsert_case(
                case_id=case_id,
                patch={
                    "raw_input_text": req.text,
                    "extract_output": extraction.model_dump(),
                    "patient_context": patient_context.model_dump(),
                },
                stage="extract",
                payload={"raw_output": raw_output},
            )
            case_id = case.case_id

    result = ORCHESTRATOR.run(patient_context, req.candidate_drugs, unable_to_answer=req.unable_to_answer)

    if req.persist:
        case = CASE_STORE.upsert_case(
            case_id=case_id,
            patch={
                "patient_context": patient_context.model_dump(),
                "candidate_drugs": [d.model_dump() for d in req.candidate_drugs],
                "review_output": result.rule_output.model_dump(),
                "agent_opinions": [o.model_dump() for o in result.agent_opinions],
                "debate": result.debate.model_dump() if result.debate else None,
                "safety_panel": result.safety_panel.model_dump() if result.safety_panel else None,
                "arbitration": result.arbitration.model_dump(),
                "clarify_output": result.clarify_output.model_dump() if result.clarify_output else None,
                "final_recommendation": result.final_recommendation,
                "status": "complete",
            },
            stage="rule_gate",
            payload=result.rule_output.model_dump(),
        )
        CASE_STORE.upsert_case(case_id=case.case_id, stage="agent_review", payload={"agents": len(result.agent_opinions)})
        if result.debate:
            CASE_STORE.upsert_case(case_id=case.case_id, stage="debate", payload=result.debate.model_dump())
        if result.safety_panel:
            CASE_STORE.upsert_case(case_id=case.case_id, stage="safety_panel", payload=result.safety_panel.model_dump())
        CASE_STORE.upsert_case(case_id=case.case_id, stage="arbitration", payload=result.arbitration.model_dump())
        if result.clarify_output:
            CASE_STORE.upsert_case(case_id=case.case_id, stage="clarify", payload=result.clarify_output.model_dump())
        CASE_STORE.upsert_case(case_id=case.case_id, stage="final", payload={"final_recommendation": result.final_recommendation})
        case_id = case.case_id

    return MultiConsultResponse(
        case_id=case_id,
        extract_output=extraction,
        rule_output=result.rule_output,
        agent_opinions=result.agent_opinions,
        debate=result.debate,
        safety_panel=result.safety_panel,
        arbitration=result.arbitration,
        clarify_output=result.clarify_output,
        final_recommendation=result.final_recommendation,
    )


# ── Legacy Consult (rule-only) ───────────────────────────────────────────

@app.post("/api/v1/consult", response_model=ConsultResponse, tags=["Consult"])
@app.post("/api/consult", response_model=ConsultResponse, tags=["Consult"], include_in_schema=False)
def consult(req: ConsultRequest, request: Request) -> ConsultResponse:
    _REQUEST_COUNTS["consult"] += 1
    patient_context = req.patient_context
    extraction = None
    case_id = req.case_id

    if patient_context is None:
        if not req.text:
            raise HTTPException(status_code=400, detail="Either text or patient_context must be provided.")
        _, extraction = run_extract(req.text)
        if extraction is None:
            raise HTTPException(status_code=422, detail="Failed to parse extract output.")
        patient_context = build_patient_context_from_extraction(req.text, extraction)

    review_output = REVIEW_ENGINE.review(patient_context, req.candidate_drugs)
    clarify_output = CLARIFY_ENGINE.clarify(
        patient_context, req.candidate_drugs, review_output, unable_to_answer=req.unable_to_answer
    )
    final = review_output.final_recommendation
    if clarify_output.status == "need_user_input" and clarify_output.final_message:
        final = clarify_output.final_message
    elif req.unable_to_answer and clarify_output.final_message:
        final = clarify_output.final_message

    if req.persist:
        case = CASE_STORE.upsert_case(
            case_id=case_id,
            patch={
                "raw_input_text": req.text,
                "patient_context": patient_context.model_dump(),
                "candidate_drugs": [d.model_dump() for d in req.candidate_drugs],
                "extract_output": extraction.model_dump() if extraction else None,
                "review_output": review_output.model_dump(),
                "clarify_output": clarify_output.model_dump(),
                "final_recommendation": final,
                "status": "complete",
            },
            stage="review",
            payload=review_output.model_dump(),
        )
        case_id = case.case_id

    return ConsultResponse(
        case_id=case_id,
        extract_output=extraction,
        review_output=review_output,
        clarify_output=clarify_output,
        final_recommendation=final,
    )


# ── Cases ──────────────────────────────────────────────────────────────

@app.get("/api/v1/case/{case_id}", tags=["Cases"])
@app.get("/api/case/{case_id}", tags=["Cases"], include_in_schema=False)
def get_case(case_id: str, request: Request):
    _REQUEST_COUNTS["case_get"] += 1
    try:
        return CASE_STORE.get_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/cases", tags=["Cases"])
def list_cases(limit: int = 20):
    case_files = sorted(
        glob.glob(str(CASE_STORE.case_dir / "*.json")),
        key=os.path.getmtime,
        reverse=True,
    )
    case_ids = [os.path.splitext(os.path.basename(f))[0] for f in case_files[:limit]]
    return {"count": len(case_ids), "cases": case_ids}


# ── Imaging & Reports ────────────────────────────────────────────────────

def _project_rel_path(path: str | Path) -> str:
    root = resolve_path(".")
    target = Path(path)
    if not target.is_absolute():
        target = (root / path).resolve()
    else:
        target = target.resolve()
    try:
        return target.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _require_imaging_path(path: str, user: UserProfile) -> None:
    sources = imaging_sources_for_user(user)
    if not path_allowed_for_sources(path, sources):
        raise HTTPException(status_code=403, detail="无权访问该影像路径")


def _require_imaging_paths(paths: list[str], user: UserProfile) -> None:
    for path in paths:
        if path:
            _require_imaging_path(path, user)


def _require_study_access(patient_id: str, study_id: str, user: UserProfile) -> None:
    sources = imaging_sources_for_user(user)
    if not study_allowed_for_sources(patient_id, study_id, sources):
        raise HTTPException(status_code=403, detail="无权访问该病例影像")


@app.get("/api/v1/imaging/studies", tags=["Imaging"])
def list_imaging_studies(
    user: Annotated[UserProfile, Depends(get_current_user)],
    source: Optional[str] = None,
):
    sources = imaging_sources_for_user(user)
    if source and source not in sources:
        return {"count": 0, "studies": []}
    studies = IMAGING_CATALOG.list_studies(source=source or None)
    studies = filter_studies(studies, sources)
    return {"count": len(studies), "studies": [s.model_dump() for s in studies]}


@app.get("/api/v1/imaging/models", tags=["Imaging"])
def list_segment_models(user: Annotated[UserProfile, Depends(get_current_user)]):
    sources = imaging_sources_for_user(user)
    dept = user.department
    default_models = dept.default_models if dept else []
    models = filter_models(SEGMENT_SERVICE.list_models(), default_models, sources)
    return {"models": models}


@app.get("/api/v1/imaging/file", tags=["Imaging"])
def serve_imaging_file(path: str, user: Annotated[UserProfile, Depends(get_current_user)]):
    root = resolve_path(".")
    target = Path(path)
    if not target.is_absolute():
        target = (root / path).resolve()
    else:
        target = target.resolve()
    if not str(target).startswith(str(root.resolve())):
        raise HTTPException(status_code=403, detail="Invalid path")
    _require_imaging_path(path, user)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)


@app.get("/api/v1/imaging/volume/meta", tags=["Imaging"])
def imaging_volume_meta(volume_path: str, user: Annotated[UserProfile, Depends(get_current_user)]):
    root = resolve_path(".")
    target = (root / volume_path).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise HTTPException(status_code=403, detail="Invalid path")
    _require_imaging_path(volume_path, user)
    if not target.exists() or not is_nifti(target):
        raise HTTPException(status_code=404, detail="NIfTI volume not found")
    meta = get_volume_meta(target)
    return {"volume_path": volume_path, **meta}


@app.get("/api/v1/imaging/volume/slice", tags=["Imaging"])
def imaging_volume_slice(
    user: Annotated[UserProfile, Depends(get_current_user)],
    volume_path: str,
    axis: str = "axial",
    index: int = 0,
    overlay_path: str | None = None,
):
    root = resolve_path(".")
    target = (root / volume_path).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise HTTPException(status_code=403, detail="Invalid path")
    _require_imaging_path(volume_path, user)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Volume not found")
    mask = None
    if overlay_path:
        _require_imaging_path(overlay_path, user)
        mask_target = (root / overlay_path).resolve()
        if str(mask_target).startswith(str(root.resolve())) and mask_target.exists():
            mask = str(mask_target)
    png = export_volume_slice(
        target,
        axis=axis if axis in {"axial", "coronal", "sagittal"} else "axial",
        slice_index=index,
        mask_path=mask,
    )
    return FileResponse(png)


@app.post("/api/v1/imaging/segment", response_model=SegmentResponse, tags=["Imaging"])
def run_segmentation(
    req: SegmentRequest,
    request: Request,
    user: Annotated[UserProfile, Depends(get_current_user)],
) -> SegmentResponse:
    _REQUEST_COUNTS["imaging_segment"] += 1
    sources = imaging_sources_for_user(user)
    dept = user.department
    default_models = dept.default_models if dept else []
    allowed_ids = allowed_model_ids(SEGMENT_SERVICE.list_models(), default_models, sources)
    if not allowed_ids:
        raise HTTPException(status_code=403, detail="本科室未配置可用分割模型")
    blocked = [m for m in req.model_ids if m not in allowed_ids]
    if blocked:
        raise HTTPException(status_code=403, detail=f"无权使用模型: {', '.join(blocked)}")
    _require_imaging_path(req.image_path, user)
    if req.volume_path:
        _require_imaging_path(req.volume_path, user)
    visual = IMAGING_CATALOG.resolve_visual_only(req.image_path)
    kwargs: dict = {"organ": req.organ}
    if req.volume_path:
        kwargs["volume_path"] = req.volume_path
    if req.slice_axis:
        kwargs["slice_axis"] = req.slice_axis
    if req.slice_index is not None:
        kwargs["slice_index"] = req.slice_index
    if req.point and len(req.point) >= 2:
        kwargs["point"] = (req.point[0], req.point[1])
    if req.bbox and len(req.bbox) >= 4:
        kwargs["bbox"] = tuple(req.bbox[:4])

    image_key = make_image_key(req.image_path, req.volume_path, req.slice_axis, req.slice_index)
    peak_before = rss_mb()
    results = SEGMENT_SERVICE.segment_serial(visual, req.model_ids, **kwargs)
    peak_after = rss_mb()
    memory_peak = max(peak_before, peak_after)

    result_payload = [{
        "model_id": r.model_id,
        "source_image": _project_rel_path(r.source_image),
        "overlay_path": _project_rel_path(r.overlay_path),
        "labels": r.labels,
        "stats": r.stats,
        "memory_mb": r.memory_mb,
        "duration_ms": r.duration_ms,
        "notes": r.notes,
    } for r in results]

    run_id: str | None = None
    if req.persist and req.patient_id and req.study_id:
        record = SEGMENT_STORE.save_run(
            patient_id=req.patient_id,
            study_id=req.study_id,
            image_key=image_key,
            source_image=str(visual),
            volume_path=req.volume_path,
            slice_axis=req.slice_axis,
            slice_index=req.slice_index,
            organ=req.organ,
            model_ids=req.model_ids,
            results=result_payload,
            memory_peak_mb=memory_peak,
        )
        run_id = record.run_id
        result_payload = [r.model_dump() for r in record.results]

    return SegmentResponse(
        results=result_payload,
        memory_peak_mb=memory_peak,
        run_id=run_id,
        image_key=image_key,
    )


@app.get("/api/v1/imaging/segments", response_model=ListSegmentRunsResponse, tags=["Imaging"])
def list_segment_runs(
    user: Annotated[UserProfile, Depends(get_current_user)],
    patient_id: str,
    study_id: str,
    image_path: str = "",
    volume_path: str | None = None,
    slice_axis: str = "axial",
    slice_index: int | None = None,
):
    _require_study_access(patient_id, study_id, user)
    if image_path:
        _require_imaging_path(image_path, user)
    if volume_path:
        _require_imaging_path(volume_path, user)
    image_key = make_image_key(image_path or volume_path or "", volume_path, slice_axis, slice_index)
    runs = SEGMENT_STORE.list_runs(patient_id, study_id, image_key=image_key)
    return ListSegmentRunsResponse(
        patient_id=patient_id,
        study_id=study_id,
        image_key=image_key,
        count=len(runs),
        runs=runs,
    )


def _resolve_existing_visual_paths(paths: list[str]) -> list[str]:
    root = resolve_path(".")
    resolved: list[str] = []
    for raw in paths:
        if not raw:
            continue
        target = Path(raw) if Path(raw).is_absolute() else (root / raw).resolve()
        if target.exists():
            resolved.append(str(target))
    return dedupe_paths(resolved)


@app.get("/api/v1/imaging/vlm/config", tags=["Imaging"])
def imaging_vlm_config():
    try:
        settings = get_vision_llm_settings()
    except LLMNotConfiguredError:
        settings = None
    if not settings or not settings.get("api_key"):
        return {
            "configured": False,
            "model": "",
            "hint": f"未配置百炼 Qwen VLM API Key。请在 {BAILIAN_CONSOLE_URL} 创建 Key 并写入 .env。",
        }
    try:
        client = get_qwen_vlm_client()
    except LLMNotConfiguredError as exc:
        return {
            "configured": False,
            "model": settings.get("model", ""),
            "base_url": settings.get("base_url", ""),
            "hint": str(exc),
        }
    return {
        "configured": True,
        "model": client.model_name,
        "base_url": settings["base_url"],
        "region": settings.get("region"),
        "workspace_id": settings.get("workspace_id") or None,
        "hint": f"已连接百炼 Qwen VLM（{settings['base_url']}）。",
    }


@app.post("/api/v1/imaging/vlm/analyze", response_model=VlmAnalyzeResponse, tags=["Imaging"])
def analyze_with_vlm(
    req: VlmAnalyzeRequest,
    request: Request,
    user: Annotated[UserProfile, Depends(get_current_user)],
) -> VlmAnalyzeResponse:
    _REQUEST_COUNTS["imaging_vlm"] += 1
    _require_imaging_paths(req.image_paths + req.overlay_paths, user)
    root = resolve_path(".")
    source_paths = _resolve_existing_visual_paths(req.image_paths)
    overlay_paths = _resolve_existing_visual_paths(req.overlay_paths)

    if overlay_paths:
        all_visual = overlay_paths
        if req.include_source_image:
            all_visual = dedupe_paths(source_paths + overlay_paths)
    else:
        all_visual = source_paths

    if not all_visual:
        raise HTTPException(status_code=400, detail="No valid image or overlay paths provided.")

    client = get_qwen_vlm_client()
    summary = req.clinical_text
    if req.segmentation_summary:
        summary = f"{summary}\n\n分割摘要：{req.segmentation_summary}".strip()

    t0 = time.perf_counter()
    analysis = client.analyze_images(
        images=all_visual[:12],
        patient_summary=summary,
        modality=req.primary_modality,
        task="clinical_and_medication",
    )
    duration_ms = (time.perf_counter() - t0) * 1000

    rel_paths = []
    for p in all_visual[:12]:
        try:
            rel_paths.append(str(Path(p).resolve().relative_to(root.resolve())))
        except ValueError:
            rel_paths.append(p)

    source_used = [p for p in all_visual if p in source_paths]
    overlay_used = [p for p in all_visual if p in overlay_paths]

    return VlmAnalyzeResponse(
        analysis=analysis,
        images_used=rel_paths,
        model=client.model_name,
        configured=True,
        overlay_count=len(overlay_used),
        source_count=len(source_used),
        duration_ms=round(duration_ms, 1),
    )


@app.post("/api/v1/imaging/screenshot", tags=["Imaging"])
def save_screenshot(
    req: SaveScreenshotRequest,
    user: Annotated[UserProfile, Depends(get_current_user)],
):
    _require_study_access(req.patient_id, req.study_id, user)
    out_dir = resolve_path(f"data/imaging_cache/screenshots/{req.patient_id}/{req.study_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    from uuid import uuid4
    out_path = out_dir / f"cap_{uuid4().hex[:10]}.png"
    decode_base64_image(req.image_data, out_path)
    return {"path": str(out_path.relative_to(resolve_path("."))), "caption": req.caption}


@app.post("/api/v1/imaging/report/generate", response_model=ClinicalReport, tags=["Imaging"])
def generate_clinical_report(
    req: GenerateReportRequest,
    user: Annotated[UserProfile, Depends(get_current_user)],
) -> ClinicalReport:
    _REQUEST_COUNTS["report_generate"] += 1
    _require_imaging_paths(
        req.image_paths + req.overlay_paths + req.screenshot_paths,
        user,
    )
    return REPORT_GENERATOR.generate(req, user_id=user.user_id)


@app.get("/api/v1/imaging/report/{patient_id}", tags=["Imaging"])
def list_patient_reports(
    patient_id: str,
    user: Annotated[UserProfile, Depends(get_current_user)],
):
    reports = REPORT_STORE.list_patient_reports(user.user_id, patient_id)
    return {"patient_id": patient_id, "count": len(reports), "reports": [r.model_dump() for r in reports]}


@app.get("/api/v1/imaging/report/{patient_id}/{report_id}", tags=["Imaging"])
def get_clinical_report(
    patient_id: str,
    report_id: str,
    user: Annotated[UserProfile, Depends(get_current_user)],
) -> ClinicalReport:
    return REPORT_STORE.get_report(user.user_id, patient_id, report_id)


@app.post("/api/v1/imaging/report/ask", response_model=ReportAskResponse, tags=["Imaging"])
def ask_report(
    req: ReportAskRequest,
    user: Annotated[UserProfile, Depends(get_current_user)],
) -> ReportAskResponse:
    _REQUEST_COUNTS["report_ask"] += 1
    return REPORT_QA.ask(req, user_id=user.user_id)


# ── Chat (ReAct + Graph RAG, role-based) ─────────────────────────────────

@app.get("/api/v1/chat/system-state", response_model=SystemState, tags=["Chat"])
async def get_chat_system_state() -> SystemState:
    await state_machine.evaluate()
    return state_machine.state


@app.post("/api/v1/chat/stream", tags=["Chat"])
async def chat_stream(req: ChatRequest, request: Request):
    """SSE streaming chat — doctor (professional) vs patient (lay language)."""
    _REQUEST_COUNTS["chat_stream"] += 1
    return StreamingResponse(
        chat_event_stream(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# Legacy yuan-agent paths (frontend proxy compat)
@app.post("/api/chat/stream", tags=["Chat"], include_in_schema=False)
async def chat_stream_legacy(req: ChatRequest, request: Request):
    return await chat_stream(req, request)


@app.get("/api/system/state", tags=["Chat"], include_in_schema=False)
async def get_system_state_legacy() -> SystemState:
    return await get_chat_system_state()


@app.post("/api/v1/drug/info", tags=["Chat"])
async def get_drug_info(request: Request):
    """Query drug details from knowledge graph for side panel."""
    from src.mcp.tools.drug_query import search_drug_info
    import re
    try:
        body = await request.json()
        drug_name = body.get("drug_name", "")
        if not drug_name:
            return JSONResponse(content={"error": "drug_name required"}, status_code=400)

        result_text = search_drug_info(drug_name)
        data: dict = {"name": drug_name, "interactions": [], "contraindications": [], "food_interactions": []}
        m = re.search(r'\*\*类别\*\*:\s*(.+)', result_text)
        if m:
            data["category"] = m.group(1).strip()
        m = re.search(r'\*\*处方类型\*\*:\s*(.+)', result_text)
        if m:
            data["rx_type"] = m.group(1).strip()
        m = re.search(r'\*\*商品名\*\*:\s*(.+)', result_text)
        if m:
            data["brand_names"] = [b.strip() for b in m.group(1).split("、")]
        m = re.search(r'\*\*简介\*\*:\s*(.+)', result_text)
        if m:
            data["description"] = m.group(1).strip()

        inter_section = re.search(r'### 已知药物相互作用\n(.*?)(?=\n###|\Z)', result_text, re.DOTALL)
        if inter_section:
            for block in inter_section.group(1).strip().split("\n- **"):
                if not block.strip():
                    continue
                nm = re.match(r'(.+?)\*\*\s*\[(.+?)\]', block)
                if nm:
                    inter: dict = {"drug": nm.group(1).strip(), "severity": nm.group(2).strip()}
                    eff = re.search(r'后果:\s*(.+)', block)
                    if eff:
                        inter["effect"] = eff.group(1).strip()
                    rec = re.search(r'建议:\s*(.+)', block)
                    if rec:
                        inter["recommendation"] = rec.group(1).strip()
                    data["interactions"].append(inter)

        return JSONResponse(content=data)
    except Exception as exc:
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error("unhandled", extra={"request_id": request_id, "error": str(exc)}, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request_id})
