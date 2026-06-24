"""Vision + multi-agent clinical report generator."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.imaging.report_cache import ImagingReportCacheStore
from src.imaging.warm_analysis import find_study, get_or_run_study_analysis, resolve_study_source_images
from src.imaging.volume_io import resolve_vlm_image_paths
from src.llm.vision_client import get_deepseek_client, get_qwen_vlm_client
from src.config import project_root
from src.orchestrator import MultiAgentOrchestrator
from src.reports.report_store import ReportStore
from src.schemas import (
    CandidateDrug,
    ClinicalReport,
    DiagnosisItem,
    GenerateReportRequest,
    PatientContext,
    ReportParagraph,
    ReportSection,
)
from src.utils import make_case_id


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
        self.orchestrator = MultiAgentOrchestrator()
        self.store = ReportStore()

    def generate(self, req: GenerateReportRequest, *, user_id: str) -> ClinicalReport:
        image_paths = [_project_rel_path(p) for p in req.image_paths]
        screenshot_paths = [_project_rel_path(p) for p in req.screenshot_paths]
        overlay_paths: list[str] = []

        study_id = req.imaging_session_label.strip()
        study = find_study(req.patient_id, study_id) if study_id else None

        if req.use_analysis_cache and study and not req.force_refresh:
            cached_report = ImagingReportCacheStore().get(study.source, req.patient_id, study.study_id)
            if cached_report and cached_report.metadata.get("medication_review_ran"):
                return self._adopt_cached_report(cached_report, req, user_id=user_id)

        from_cache = False
        cache_entry = None
        if req.use_analysis_cache and study:
            cache_entry, from_cache = get_or_run_study_analysis(
                study,
                clinical_text=req.clinical_text,
                use_cache=True,
                force_refresh=req.force_refresh,
                include_deepseek=True,
            )

        if cache_entry:
            vlm_analysis = cache_entry.vlm_analysis
            deepseek_synthesis: dict[str, Any] = dict(cache_entry.deepseek_synthesis or {})
            all_visual = list(cache_entry.image_paths)
            image_paths = list(cache_entry.image_paths)
            vlm_model_name = cache_entry.vlm_model
        else:
            all_visual = dedupe_paths(image_paths + screenshot_paths)
            abs_visual = [str((project_root() / p).resolve()) for p in all_visual if p]
            resolved_visual = resolve_vlm_image_paths(abs_visual)
            if not resolved_visual and study:
                resolved_visual = resolve_study_source_images(study)
                all_visual = [_project_rel_path(p) for p in resolved_visual]
                image_paths = list(all_visual)
            if not resolved_visual:
                from src.llm.errors import VisionLLMError

                raise VisionLLMError(
                    "Qwen VLM",
                    "未找到可读取的影像原片",
                    hint="请确认 catalog 有 PNG 预览，或运行 scripts/warm_imaging_analysis_cache.py。",
                )
            qwen_vlm = get_qwen_vlm_client()
            vlm_analysis = qwen_vlm.analyze_images(
                images=resolved_visual[:12],
                patient_summary=self._vlm_summary(req),
                modality=req.primary_modality,
                task="clinical_and_medication",
            )
            vlm_model_name = qwen_vlm.model_name
            deepseek_synthesis = {}

        session_id = ReportStore.make_imaging_session_id(
            req.primary_modality,
            all_visual,
            req.imaging_session_label,
        )

        multi_agent = None
        rule_output = None
        med_review_error: str | None = None
        candidate_drugs = list(req.candidate_drugs)
        if req.run_medication_review and not candidate_drugs:
            candidate_drugs = self._drugs_from_vlm(vlm_analysis)
        run_med_review = req.run_medication_review and bool(candidate_drugs)

        if run_med_review:
            try:
                patient_context = req.patient_context or PatientContext(
                    source_text=req.clinical_text,
                    chief_complaint=str(vlm_analysis.get("chief_complaint", "")),
                    symptoms_or_complaints=list(vlm_analysis.get("symptoms", []) or []),
                    diagnoses=[DiagnosisItem(name=str(d)) for d in vlm_analysis.get("diagnoses", [])],
                    allergies=list(vlm_analysis.get("allergies", []) or []),
                )
                dept_ctx = self.orchestrator._resolve_department_context(patient_context)
                rule_output = self.orchestrator.review_engine.review(
                    patient_context,
                    candidate_drugs,
                    department=patient_context.department or None,
                    priority_categories=dept_ctx.priority_categories if dept_ctx else None,
                )
                multi_agent = self.orchestrator.run(
                    patient_context,
                    candidate_drugs,
                    skip_clarify=True,
                    rule_output=rule_output,
                )
                deepseek = get_deepseek_client()
                deepseek_synthesis = deepseek.synthesize_report(
                    clinical_text=req.clinical_text,
                    vlm_analysis=vlm_analysis,
                    agent_opinions=[o.model_dump() for o in multi_agent.agent_opinions],
                    arbitration=multi_agent.arbitration.model_dump(),
                    rule_output=multi_agent.rule_output.model_dump(),
                    chain_hint=str(vlm_analysis.get("reasoning", "")),
                )
            except Exception as exc:
                med_review_error = str(exc)
                run_med_review = multi_agent is not None
        elif not deepseek_synthesis:
            try:
                deepseek = get_deepseek_client()
                deepseek_synthesis = deepseek.synthesize_report(
                    clinical_text=req.clinical_text,
                    vlm_analysis=vlm_analysis,
                    agent_opinions=[],
                    arbitration={},
                    rule_output={},
                    chain_hint=str(vlm_analysis.get("reasoning", "")),
                )
            except Exception:
                deepseek_synthesis = {}

        paragraphs = self._build_paragraphs(
            req=req,
            vlm=vlm_analysis,
            multi_agent=multi_agent,
            synthesis=deepseek_synthesis,
            run_med_review=run_med_review,
            candidate_drugs=candidate_drugs,
        )
        cot = self._build_chain_of_thought(
            vlm=vlm_analysis,
            multi_agent=multi_agent,
            synthesis=deepseek_synthesis,
            run_med_review=run_med_review,
        )

        metadata: dict[str, Any] = {
            "models_used": req.models_used,
            "vlm_model": vlm_model_name,
            "segmentation_summary": req.segmentation_summary,
            "medication_review_ran": run_med_review,
            "medication_review_error": med_review_error,
            "analysis_from_cache": from_cache,
            "review_pipeline": (
                ["cached_vlm", "cached_deepseek", "rule_layer_0", "multi_agent_review"]
                if from_cache and run_med_review
                else (
                    ["cached_vlm", "cached_deepseek"]
                    if from_cache
                    else (
                        ["vlm_recommendation", "rule_layer_0", "multi_agent_review"]
                        if run_med_review
                        else (["vlm_recommendation"] if req.run_medication_review else ["vlm_only"])
                    )
                )
            ),
            "vlm_analysis": vlm_analysis,
            "candidate_drugs": [d.model_dump() for d in candidate_drugs],
            "rule_output": rule_output.model_dump() if rule_output else None,
            "visual_images_submitted": len(all_visual),
            "overlay_count": len(overlay_paths),
        }
        if multi_agent:
            metadata["agent_opinions"] = [o.model_dump() for o in multi_agent.agent_opinions]
            metadata["arbitration"] = multi_agent.arbitration.model_dump()
            metadata["debate"] = multi_agent.debate.model_dump() if multi_agent.debate else None
            metadata["safety_panel"] = (
                multi_agent.safety_panel.model_dump() if multi_agent.safety_panel else None
            )
            metadata["final_recommendation"] = multi_agent.final_recommendation
        if deepseek_synthesis:
            try:
                metadata["deepseek_model"] = get_deepseek_client().model_name
            except Exception:
                metadata["deepseek_model"] = None

        report = self.store.create_or_replace_session_report(
            user_id=user_id,
            patient_id=req.patient_id,
            imaging_session_id=session_id,
            modalities=req.modalities,
            paragraphs=paragraphs,
            chain_of_thought=cot,
            image_paths=image_paths,
            overlay_paths=overlay_paths,
            screenshot_paths=screenshot_paths,
            metadata=metadata,
        )
        if study and run_med_review and multi_agent is not None and not med_review_error:
            ImagingReportCacheStore().save(report, study.source, study.study_id)
        return report

    def _adopt_cached_report(
        self,
        cached: ClinicalReport,
        req: GenerateReportRequest,
        *,
        user_id: str,
    ) -> ClinicalReport:
        """Serve batch-warmed report to the current user (copy into their ReportStore)."""
        session_id = cached.imaging_session_id or ReportStore.make_imaging_session_id(
            req.primary_modality,
            cached.image_paths,
            req.imaging_session_label,
        )
        if cached.user_id == user_id:
            existing = self.store.find_report_by_session(user_id, req.patient_id, session_id)
            if existing:
                return existing
        adopted = cached.model_copy(update={"user_id": user_id})
        return self.store.create_or_replace_session_report(
            user_id=user_id,
            patient_id=adopted.patient_id,
            imaging_session_id=session_id,
            modalities=adopted.modalities,
            paragraphs=adopted.paragraphs,
            chain_of_thought=adopted.chain_of_thought,
            image_paths=adopted.image_paths,
            overlay_paths=adopted.overlay_paths,
            screenshot_paths=adopted.screenshot_paths,
            metadata=adopted.metadata,
        )

    @staticmethod
    def _vlm_summary(req: GenerateReportRequest) -> str:
        summary = req.clinical_text
        if req.segmentation_summary:
            summary = f"{summary}\n\n分割摘要：{req.segmentation_summary}".strip()
        return summary

    def _build_paragraphs(
        self,
        req: GenerateReportRequest,
        vlm: dict,
        multi_agent: Any | None,
        synthesis: dict,
        run_med_review: bool,
        candidate_drugs: list[CandidateDrug],
    ) -> list[ReportParagraph]:
        section_content: dict[str, str] = {}

        section_content["clinical_analysis"] = str(
            synthesis.get("clinical_analysis") or vlm.get("clinical_analysis", "")
        ).strip()

        imaging_parts = [
            str(synthesis.get("imaging_findings") or vlm.get("imaging_findings", "")).strip(),
        ]
        if req.segmentation_summary:
            imaging_parts.append(f"分割模型运行摘要：{req.segmentation_summary}")
        if req.overlay_paths:
            imaging_parts.append(f"纳入报告的 overlay 数量：{len(req.overlay_paths)}。")
        if req.screenshot_paths:
            imaging_parts.append(f"医生截图数量：{len(req.screenshot_paths)}。")
        section_content["imaging_findings"] = "\n".join(p for p in imaging_parts if p)

        if run_med_review and multi_agent is not None:
            section_content["medication_recommendation"] = self._medication_section(
                vlm, synthesis, multi_agent, candidate_drugs
            )
            section_content["pharmacy_assessment"] = self._agent_panel_section(
                multi_agent, agent_ids={"clinical_pharmacist"}
            )
            section_content["allergy_analysis"] = self._agent_panel_section(
                multi_agent, agent_ids={"allergy_specialist"}
            )
            section_content["risk_summary"] = self._risk_summary_section(multi_agent, synthesis)
        else:
            section_content["medication_recommendation"] = (
                "本次报告以影像会诊为主，未启用用药审查流水线。"
                "完整流程为：VLM 用药推荐 → 规则审查（Layer 0）→ 多智能体用药审查。"
                "如需执行，请勾选「启用用药审查」并填写候选药物（或依赖 VLM 推荐自动带入）。"
            )
            section_content["risk_summary"] = str(
                vlm.get("reasoning") or vlm.get("risk_level") or "影像会诊完成，用药安全审查未执行。"
            )

        section_content["anesthesia_surgery"] = str(
            synthesis.get("anesthesia_surgery")
            or vlm.get("anesthesia_surgery", "暂无明确手术麻醉场景；如进入围术期需另行评估。")
        ).strip()

        paragraphs: list[ReportParagraph] = []
        order = 0
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
    def _medication_section(
        vlm: dict,
        synthesis: dict,
        multi_agent: Any,
        candidate_drugs: list[CandidateDrug],
    ) -> str:
        lines = [
            str(synthesis.get("medication_recommendation") or vlm.get("medication_recommendation", "")).strip(),
            "",
            "候选药物："
            + ("、".join(d.name for d in candidate_drugs) if candidate_drugs else "（无）"),
        ]
        vlm_drugs = vlm.get("recommended_drugs") or []
        if vlm_drugs:
            lines.append("VLM 初步建议：")
            for item in vlm_drugs[:8]:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('name', '')} {item.get('dose', '')} {item.get('route', '')} {item.get('indication', '')}".strip())
                else:
                    lines.append(f"- {item}")
        ro = multi_agent.rule_output
        lines.append(
            f"\n规则审查（Layer 0 前置）：{ro.final_recommendation}"
            + ("【建议阻断】" if ro.block_decision else "")
        )
        if ro.evidence:
            lines.append("\n规则引擎命中：")
            for ev in ro.evidence[:6]:
                lines.append(f"- [{ev.risk_level}] {ev.summary}")
        return "\n".join(line for line in lines if line is not None).strip()

    @staticmethod
    def _agent_panel_section(multi_agent: Any, agent_ids: set[str]) -> str:
        lines: list[str] = []
        for op in multi_agent.agent_opinions:
            if op.agent_id not in agent_ids:
                continue
            lines.extend([
                f"【{op.agent_name}】风险={op.risk_level}，阻断={op.block_decision}，置信度={op.confidence:.2f}",
                f"结论：{op.summary}",
            ])
            if op.reasons:
                lines.append("理由：")
                lines.extend(f"  - {r}" for r in op.reasons)
            if op.alternatives:
                lines.append("替代方案：" + "；".join(op.alternatives))
            if op.evidence_cited:
                lines.append("引用证据：" + "；".join(op.evidence_cited))
            if op.debate_round > 1:
                lines.append(f"（第 {op.debate_round} 轮修订意见）")
            lines.append("")
        return "\n".join(lines).strip() or "该专家未给出额外意见。"

    @staticmethod
    def _risk_summary_section(multi_agent: Any, synthesis: dict) -> str:
        lines: list[str] = []
        arb = multi_agent.arbitration
        lines.append(
            f"共识风险={arb.consensus_risk_level}，共识阻断={arb.consensus_block_decision}，"
            f"冲突检测={arb.conflict_detected}。"
        )
        lines.append(f"主席结论：{synthesis.get('risk_summary') or arb.final_recommendation}")

        if multi_agent.debate:
            debate = multi_agent.debate
            lines.append(f"\n辩论轮次：{len(debate.rounds)} 轮，共识={debate.final_consensus}，人工复核={debate.flagged_for_human}")
            if debate.moderator_synthesis and debate.moderator_synthesis.integration_summary:
                lines.append(f"主持人汇总：{debate.moderator_synthesis.integration_summary}")
            for rnd in debate.rounds:
                critic = rnd.critic_output
                if critic and critic.dissent_log:
                    lines.append(f"第 {rnd.round_number} 轮分歧：" + "；".join(critic.dissent_log))

        if multi_agent.safety_panel:
            sp = multi_agent.safety_panel
            lines.append(f"\n安全面板：通过={sp.passed}，建议阻断={sp.block_recommended}。{sp.summary}")

        if arb.dissenting_opinions:
            lines.append("\n持异议专家：")
            for op in arb.dissenting_opinions:
                lines.append(f"- {op.agent_name}：{op.summary}（risk={op.risk_level}, block={op.block_decision}）")

        if arb.rule_evidence:
            lines.append("\n规则 evidence（不可被 LLM 覆盖）：")
            for ev in arb.rule_evidence[:8]:
                lines.append(f"- [{ev.risk_level}] {ev.rule_id}: {ev.summary}")

        other_agents = [
            op for op in multi_agent.agent_opinions
            if op.agent_id not in {"clinical_pharmacist", "allergy_specialist"}
        ]
        if other_agents:
            lines.append("\n其他专家意见摘要：")
            for op in other_agents:
                lines.append(
                    f"- {op.agent_name}：{op.summary} "
                    f"(risk={op.risk_level}, block={op.block_decision}, conf={op.confidence:.2f})"
                )
                if op.reasons:
                    lines.append("  理由：" + "；".join(op.reasons[:3]))

        return "\n".join(lines).strip()

    @staticmethod
    def _build_chain_of_thought(
        vlm: dict,
        multi_agent: Any | None,
        synthesis: dict,
        run_med_review: bool,
    ) -> str:
        parts: list[str] = ["Step 1 VLM 视觉分析 → 用药推荐。"]
        parts.append(f"VLM 推理：{vlm.get('reasoning', '')}")

        if not run_med_review or multi_agent is None:
            parts.append("Step 2 跳过规则审查与多智能体用药审查（未启用或未指定候选药物）。")
            return "\n".join(p for p in parts if p)

        ro = multi_agent.rule_output
        parts.append("Step 2 规则审查（Layer 0 前置审查，内嵌于所有用药审查）。")
        parts.append(f"规则结论：{ro.final_recommendation}")
        parts.append("Step 3 多智能体用药审查 → Step 4 辩论修订 → Step 5 主席仲裁 → DeepSeek 合成。")
        if synthesis.get("chain_of_thought"):
            parts.append(str(synthesis["chain_of_thought"]))
        elif multi_agent.debate:
            parts.append(multi_agent.debate.moderator_synthesis.integration_summary if multi_agent.debate.moderator_synthesis else "")
        return "\n".join(p for p in parts if p)

    @staticmethod
    def _drugs_from_vlm(vlm: dict) -> list[CandidateDrug]:
        import re

        drugs: list[CandidateDrug] = []
        seen: set[str] = set()

        def add(name: str, **kwargs: object) -> None:
            cleaned = name.strip().strip("，。；;、")
            if not cleaned or len(cleaned) < 2:
                return
            key = cleaned.lower()
            if key in seen:
                return
            seen.add(key)
            drugs.append(CandidateDrug(name=cleaned, **kwargs))  # type: ignore[arg-type]

        for item in vlm.get("recommended_drugs", []):
            if isinstance(item, str):
                add(item)
            elif isinstance(item, dict):
                add(
                    str(item.get("name") or ""),
                    **{k: v for k, v in item.items() if k in CandidateDrug.model_fields and k != "name"},
                )

        if drugs:
            return drugs

        text = "\n".join(
            str(vlm.get(key) or "")
            for key in ("medication_recommendation", "clinical_analysis", "reasoning")
        )
        for m in re.finditer(r"[-•*]\s*([^\n:：,，;；]{2,48})", text):
            add(m.group(1))
        for m in re.finditer(
            r"(?:可选用|推荐使用|建议|加用|给予|选用|调整为|换用|启动)\s*([A-Za-z0-9\u4e00-\u9fff\-/（）()]{2,32})",
            text,
        ):
            add(m.group(1))
        for m in re.finditer(
            r"([A-Za-z][A-Za-z0-9\-]{2,24})\s*(?:\d+\s*mg|\d+\s*g|片|胶囊|注射液)",
            text,
        ):
            add(m.group(1))
        return drugs


def dedupe_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _project_rel_path(path: str | Path) -> str:
    root = project_root().resolve()
    target = Path(path)
    if not target.is_absolute():
        target = (root / path).resolve()
    else:
        target = target.resolve()
    try:
        return target.relative_to(root).as_posix()
    except ValueError:
        return str(path)

