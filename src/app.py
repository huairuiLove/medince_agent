"""MedSafe API Server — Multi-agent drug safety review via LLM API."""
from __future__ import annotations

import glob
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from src.agents.extract_agent import ExtractAgent
from src.case_store import CaseStore
from src.clarify_engine import ClarifyEngine
from src.config import load_config
from src.llm.client import get_llm_client
from src.logging_config import get_logger, setup_logging
from src.orchestrator import MultiAgentOrchestrator
from src.review_engine import ReviewEngine
from src.schemas import (
    CandidateDrug,
    ClarifyRequest,
    ClarifyResponse,
    ClinicalReport,
    ConsultRequest,
    ConsultResponse,
    DiagnosisItem,
    DrugItem,
    ExtractRequest,
    ExtractResponse,
    ExtractionOutput,
    GenerateReportRequest,
    MultiConsultRequest,
    MultiConsultResponse,
    MultiReviewRequest,
    MultiReviewResponse,
    PatientContext,
    ReportAskRequest,
    ReportAskResponse,
    ReviewRequest,
    ReviewResponse,
    SaveScreenshotRequest,
    SegmentRequest,
    SegmentResponse,
)
from src.imaging.catalog import ImagingCatalog
from src.imaging.memory_monitor import rss_mb
from src.imaging.segment_service import SegmentService
from src.imaging.volume_io import decode_base64_image, export_volume_slice, get_volume_meta, is_nifti
from src.reports.report_generator import ReportGenerator
from src.reports.report_qa import ReportQAService
from src.reports.report_store import ReportStore
from src.config import resolve_path
from src.react.chat_service import chat_event_stream, init_chat_services, shutdown_chat_services
from src.react.schemas import ChatRequest, SystemState
from src.react.state_machine import state_machine
from src.react.tool_registry import tool_registry

VERSION = "3.0.0"

DESCRIPTION = """
MedSafe — 基于 MIMIC-III 场景的多智能体用药安全审查系统。

## 架构（四阶段）
1. **Stage 1** — 总体方案设计
2. **Stage 2** — LLM API 结构化抽取
3. **Stage 3** — 规则引擎 review / clarify
4. **Stage 4** — 多智能体会诊 + 工程部署

## 核心流程
- **Extract** — LLM API 从病历文本抽取结构化信息
- **Rule Gate** — 确定性规则库预筛（硬安全底线）
- **Multi-Agent Review** — 临床药师 / 内科主治 / 过敏专员 / 药房库管 / 专科医生
- **Arbitration** — 会诊主席汇总仲裁
- **Clarify** — 信息协调员追问或保守降级
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
    llm = get_llm_client()
    logger.info("MedSafe API ready", extra={"version": VERSION, "llm": type(llm).__name__})
    await init_chat_services()
    yield
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
        {"name": "Clarify", "description": "Clarification and conservative fallback"},
        {"name": "Multi-Agent", "description": "Multi-agent consult pipeline (Stage 4)"},
        {"name": "Consult", "description": "Legacy rule-only consult pipeline"},
        {"name": "Cases", "description": "Case log management and replay"},
        {"name": "Imaging", "description": "Segmentation, screenshots, clinical reports"},
        {"name": "Chat", "description": "ReAct SSE chat with role-based prompts (doctor/patient)"},
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
REVIEW_ENGINE = ReviewEngine()
CLARIFY_ENGINE = ClarifyEngine()
ORCHESTRATOR = MultiAgentOrchestrator()
EXTRACT_AGENT = ExtractAgent(get_llm_client())
IMAGING_CATALOG = ImagingCatalog()
SEGMENT_SERVICE = SegmentService()
REPORT_GENERATOR = ReportGenerator()
REPORT_STORE = ReportStore()
REPORT_QA = ReportQAService()

_SERVER_START = time.time()
_REQUEST_COUNTS: dict[str, int] = {
    "extract": 0, "review": 0, "clarify": 0, "consult": 0,
    "multi_review": 0, "multi_consult": 0, "case_get": 0,
    "imaging_segment": 0, "report_generate": 0, "report_ask": 0, "chat_stream": 0,
}


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


def run_extract(text: str) -> tuple[str, ExtractionOutput | None]:
    return EXTRACT_AGENT.extract(text)


# ── Health ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
def health() -> dict:
    llm = get_llm_client()
    return {
        "status": "ok",
        "version": VERSION,
        "uptime_seconds": round(time.time() - _SERVER_START, 1),
        "llm_provider": type(llm).__name__,
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


# ── Rule Review (Stage 3) ──────────────────────────────────────────────

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


# ── Multi-Agent (Stage 4) ──────────────────────────────────────────────

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


# ── Legacy Consult (Stage 3 rule-only) ─────────────────────────────────

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
    if clarify_output.conservative_advice:
        final = clarify_output.conservative_advice.summary
    elif clarify_output.status == "need_user_input":
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


# ── Imaging & Reports (Stage 5) ────────────────────────────────────────

@app.get("/api/v1/imaging/studies", tags=["Imaging"])
def list_imaging_studies():
    studies = IMAGING_CATALOG.list_studies()
    return {"count": len(studies), "studies": [s.model_dump() for s in studies]}


@app.get("/api/v1/imaging/models", tags=["Imaging"])
def list_segment_models():
    return {"models": SEGMENT_SERVICE.list_models()}


@app.get("/api/v1/imaging/file", tags=["Imaging"])
def serve_imaging_file(path: str):
    root = resolve_path(".")
    target = (root / path).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise HTTPException(status_code=403, detail="Invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)


@app.get("/api/v1/imaging/volume/meta", tags=["Imaging"])
def imaging_volume_meta(volume_path: str):
    root = resolve_path(".")
    target = (root / volume_path).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise HTTPException(status_code=403, detail="Invalid path")
    if not target.exists() or not is_nifti(target):
        raise HTTPException(status_code=404, detail="NIfTI volume not found")
    meta = get_volume_meta(target)
    return {"volume_path": volume_path, **meta}


@app.get("/api/v1/imaging/volume/slice", tags=["Imaging"])
def imaging_volume_slice(
    volume_path: str,
    axis: str = "axial",
    index: int = 0,
    overlay_path: str | None = None,
):
    root = resolve_path(".")
    target = (root / volume_path).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise HTTPException(status_code=403, detail="Invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Volume not found")
    mask = None
    if overlay_path:
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
def run_segmentation(req: SegmentRequest, request: Request) -> SegmentResponse:
    _REQUEST_COUNTS["imaging_segment"] += 1
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

    peak_before = rss_mb()
    results = SEGMENT_SERVICE.segment_serial(visual, req.model_ids, **kwargs)
    peak_after = rss_mb()

    return SegmentResponse(
        results=[{
            "model_id": r.model_id,
            "source_image": r.source_image,
            "overlay_path": r.overlay_path,
            "labels": r.labels,
            "stats": r.stats,
            "memory_mb": r.memory_mb,
            "duration_ms": r.duration_ms,
            "notes": r.notes,
        } for r in results],
        memory_peak_mb=max(peak_before, peak_after),
    )


@app.post("/api/v1/imaging/screenshot", tags=["Imaging"])
def save_screenshot(req: SaveScreenshotRequest):
    out_dir = resolve_path(f"data/imaging_cache/screenshots/{req.patient_id}/{req.study_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    from uuid import uuid4
    out_path = out_dir / f"cap_{uuid4().hex[:10]}.png"
    decode_base64_image(req.image_data, out_path)
    return {"path": str(out_path.relative_to(resolve_path("."))), "caption": req.caption}


@app.post("/api/v1/imaging/report/generate", response_model=ClinicalReport, tags=["Imaging"])
def generate_clinical_report(req: GenerateReportRequest, request: Request) -> ClinicalReport:
    _REQUEST_COUNTS["report_generate"] += 1
    return REPORT_GENERATOR.generate(req)


@app.get("/api/v1/imaging/report/{patient_id}", tags=["Imaging"])
def list_patient_reports(patient_id: str):
    reports = REPORT_STORE.list_patient_reports(patient_id)
    return {"patient_id": patient_id, "count": len(reports), "reports": [r.model_dump() for r in reports]}


@app.get("/api/v1/imaging/report/{patient_id}/{report_id}", tags=["Imaging"])
def get_clinical_report(patient_id: str, report_id: str) -> ClinicalReport:
    return REPORT_STORE.get_report(patient_id, report_id)


@app.post("/api/v1/imaging/report/ask", response_model=ReportAskResponse, tags=["Imaging"])
def ask_report(req: ReportAskRequest, request: Request) -> ReportAskResponse:
    _REQUEST_COUNTS["report_ask"] += 1
    return REPORT_QA.ask(req)


@app.post("/api/v1/imaging/report/ask", response_model=ReportAskResponse, tags=["Imaging"])
def ask_report(req: ReportAskRequest, request: Request) -> ReportAskResponse:
    _REQUEST_COUNTS["report_ask"] += 1
    return REPORT_QA.ask(req)


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
