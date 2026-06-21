"""Vision + multi-agent clinical report generator."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.llm.vision_client import get_deepseek_client, get_qwen_vlm_client
from src.orchestrator import MultiAgentOrchestrator
from src.reports.report_store import ReportStore
from src.schemas import (
    CandidateDrug,
    ClinicalReport,
    GenerateReportRequest,
    PatientContext,
    ReportParagraph,
    ReportSection,
)
from src.utils import extract_json_payload, make_case_id, utc_now_iso


SECTION_ORDER: list[tuple[ReportSection, str]] = [
    ("clinical_analysis", "临床病症分析"),
    ("imaging_findings", "影像学发现"),
    ("medication_recommendation", "用药推荐"),
    ("pharmacy_assessment", "药学专家评估"),
    ("allergy_analysis", "过敏分析"),
    ("anesthesia_surgery", "手术麻醉用药评估"),
    ("risk_summary", "综合风险与结论"),
]


class ReportGenerator:
    def __init__(self) -> None:
        self.qwen_vlm = get_qwen_vlm_client()
        self.deepseek = get_deepseek_client()
        self.orchestrator = MultiAgentOrchestrator()
        self.store = ReportStore()

    def generate(self, req: GenerateReportRequest) -> ClinicalReport:
        image_paths = [str(p) for p in req.image_paths]
        screenshot_paths = [str(p) for p in req.screenshot_paths]
        overlay_paths = [str(p) for p in req.overlay_paths]
        all_visual = dedupe_paths(image_paths + screenshot_paths + overlay_paths)

        session_id = ReportStore.make_imaging_session_id(
            req.primary_modality,
            all_visual,
            req.imaging_session_label,
        )

        vlm_analysis = self.qwen_vlm.analyze_images(
            images=all_visual[:12],
            patient_summary=req.clinical_text,
            modality=req.primary_modality,
            task="clinical_and_medication",
        )

        candidate_drugs = req.candidate_drugs or self._drugs_from_vlm(vlm_analysis)
        from src.schemas import DiagnosisItem

        patient_context = req.patient_context or PatientContext(
            source_text=req.clinical_text,
            chief_complaint=vlm_analysis.get("chief_complaint", ""),
            symptoms_or_complaints=vlm_analysis.get("symptoms", []),
            diagnoses=[DiagnosisItem(name=str(d)) for d in vlm_analysis.get("diagnoses", [])],
            allergies=vlm_analysis.get("allergies", []),
        )

        multi_agent = self.orchestrator.run(patient_context, candidate_drugs, skip_clarify=True)
        deepseek_synthesis = self.deepseek.synthesize_report(
            clinical_text=req.clinical_text,
            vlm_analysis=vlm_analysis,
            agent_opinions=[o.model_dump() for o in multi_agent.agent_opinions],
            arbitration=multi_agent.arbitration.model_dump(),
            rule_output=multi_agent.rule_output.model_dump(),
            chain_hint=vlm_analysis.get("reasoning", ""),
        )

        paragraphs = self._build_paragraphs(vlm_analysis, multi_agent, deepseek_synthesis)
        cot = deepseek_synthesis.get("chain_of_thought") or vlm_analysis.get("reasoning", "")

        return self.store.create_or_replace_session_report(
            patient_id=req.patient_id,
            imaging_session_id=session_id,
            modalities=req.modalities,
            paragraphs=paragraphs,
            chain_of_thought=cot,
            image_paths=image_paths,
            overlay_paths=overlay_paths,
            screenshot_paths=screenshot_paths,
            metadata={
                "models_used": req.models_used,
                "vlm_model": self.qwen_vlm.model_name,
                "deepseek_model": self.deepseek.model_name,
                "segmentation_summary": req.segmentation_summary,
            },
        )

    def _build_paragraphs(self, vlm: dict, multi_agent: Any, synthesis: dict) -> list[ReportParagraph]:
        paragraphs: list[ReportParagraph] = []
        order = 0

        section_content = {
            "clinical_analysis": synthesis.get("clinical_analysis") or vlm.get("clinical_analysis", ""),
            "imaging_findings": synthesis.get("imaging_findings") or vlm.get("imaging_findings", ""),
            "medication_recommendation": synthesis.get("medication_recommendation") or vlm.get("medication_recommendation", ""),
            "pharmacy_assessment": synthesis.get("pharmacy_assessment") or self._pharmacy_block(multi_agent),
            "allergy_analysis": synthesis.get("allergy_analysis") or self._allergy_block(multi_agent),
            "anesthesia_surgery": synthesis.get("anesthesia_surgery") or vlm.get("anesthesia_surgery", "暂无明确手术麻醉场景；如进入围术期需另行评估。"),
            "risk_summary": synthesis.get("risk_summary") or multi_agent.final_recommendation,
        }

        for section, title in SECTION_ORDER:
            content = str(section_content.get(section, "")).strip()
            if not content:
                continue
            order += 1
            paragraphs.append(
                ReportParagraph(
                    paragraph_id=make_case_id("para"),
                    section=section,
                    title=title,
                    content=content,
                    order=order,
                )
            )
        return paragraphs

    @staticmethod
    def _pharmacy_block(multi_agent: Any) -> str:
        lines = []
        for op in multi_agent.agent_opinions:
            if op.agent_id == "clinical_pharmacist":
                lines.append(op.summary)
                lines.extend(op.reasons)
        return "\n".join(lines) or "药学专家尚未给出额外意见。"

    @staticmethod
    def _allergy_block(multi_agent: Any) -> str:
        for op in multi_agent.agent_opinions:
            if op.agent_id == "allergy_specialist":
                return "\n".join([op.summary, *op.reasons, *op.alternatives])
        return "未发现明确过敏禁忌。"

    @staticmethod
    def _drugs_from_vlm(vlm: dict) -> list[CandidateDrug]:
        drugs: list[CandidateDrug] = []
        for item in vlm.get("recommended_drugs", []):
            if isinstance(item, str):
                drugs.append(CandidateDrug(name=item))
            elif isinstance(item, dict):
                drugs.append(CandidateDrug(**{k: v for k, v in item.items() if k in CandidateDrug.model_fields}))
        return drugs


def dedupe_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p and p not in seen and Path(p).exists():
            seen.add(p)
            out.append(p)
    return out
