"""Load clinical case templates from data/case_templates/ (single source of truth)."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src.config import load_config, resolve_path
from src.schemas import CandidateDrug, PatientContext
from src.utils import load_json

_SKIP_FILES = frozenset({"complete_case_log.json", "index.json"})


class CaseTemplate(BaseModel):
    id: str
    title: str
    description: str = ""
    category: str = ""
    input_mode: Literal["text", "context"] = "context"
    text: str = ""
    patient_context: PatientContext | None = None
    candidate_drugs: list[CandidateDrug] = Field(default_factory=list)


class CaseTemplateListResponse(BaseModel):
    templates: list[CaseTemplate]


def templates_dir() -> Path:
    cfg = load_config()
    data = cfg.get("data", {})
    rel = data.get("case_templates_dir") or data.get("demo_dir", "datasets/case_templates")
    return resolve_path(rel)


def _from_request_block(
    template_id: str,
    title: str,
    request: dict,
    *,
    description: str = "",
    category: str = "",
) -> CaseTemplate | None:
    text = str(request.get("text") or "").strip()
    patient_raw = request.get("patient_context")
    candidates_raw = request.get("candidate_drugs") or []
    if not text and not patient_raw and not candidates_raw:
        return None

    candidate_drugs = [CandidateDrug.model_validate(item) for item in candidates_raw]
    patient_context: PatientContext | None = None
    input_mode: Literal["text", "context"] = "context"

    if text:
        input_mode = "text"
    elif patient_raw:
        patient_context = PatientContext.model_validate(patient_raw)
        input_mode = "context"

    return CaseTemplate(
        id=template_id,
        title=title,
        description=description,
        category=category,
        input_mode=input_mode,
        text=text,
        patient_context=patient_context,
        candidate_drugs=candidate_drugs,
    )


def _parse_file(path: Path) -> list[CaseTemplate]:
    data = load_json(path)
    if not isinstance(data, dict):
        return []

    if isinstance(data.get("cases"), list):
        out: list[CaseTemplate] = []
        for item in data["cases"]:
            if not isinstance(item, dict):
                continue
            req = item.get("request") or item
            template_id = str(item.get("id") or item.get("case_id") or path.stem)
            title = str(item.get("title") or template_id)
            tpl = _from_request_block(
                template_id,
                title,
                req,
                description=str(data.get("description") or item.get("description") or ""),
                category=str(item.get("category") or ""),
            )
            if tpl:
                out.append(tpl)
        return out

    request = data.get("request")
    if not isinstance(request, dict):
        return []

    template_id = str(data.get("case_id") or data.get("id") or path.stem)
    title = str(data.get("title") or data.get("description") or template_id)
    tpl = _from_request_block(
        template_id,
        title,
        request,
        description=str(data.get("description") or ""),
        category=str(data.get("category") or ""),
    )
    return [tpl] if tpl else []


def list_case_templates() -> list[CaseTemplate]:
    root = templates_dir()
    if not root.is_dir():
        return []

    templates: list[CaseTemplate] = []
    seen: set[str] = set()
    for path in sorted(root.glob("*.json")):
        if path.name in _SKIP_FILES:
            continue
        for tpl in _parse_file(path):
            if tpl.id in seen:
                continue
            seen.add(tpl.id)
            templates.append(tpl)
    return templates


def get_case_template(template_id: str) -> CaseTemplate | None:
    for tpl in list_case_templates():
        if tpl.id == template_id:
            return tpl
    return None
