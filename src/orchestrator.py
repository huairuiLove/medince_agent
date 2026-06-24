"""Multi-agent drug safety review orchestrator."""
from __future__ import annotations

from typing import Any

from src.agents.chief_reviewer import ChiefReviewerAgent
from src.agents.coordinator import CoordinatorAgent
from src.agents.department_specialist import DepartmentSpecialistAgent
from src.agents.registry import get_agent_registry
from src.agents.specialist_router import SpecialistAgent
from src.config import get_config
from src.department.context import DepartmentContext, get_department_context
from src.debate.debate_engine import DebateEngine
from src.debate.safety_panel import SafetyPanel
from src.drug_catalog.catalog_service import get_drug_catalog_service
from src.drug_catalog.terminology import CatalogAwareKnowledgeBase
from src.llm.client import get_llm_client
from src.review_engine import ReviewEngine
from src.schemas import (
    ArbitrationResult,
    CandidateDrug,
    ClarifyOutput,
    DebateResult,
    MultiReviewResponse,
    PatientContext,
    ReviewOutput,
    SafetyPanelResult,
)


class MultiAgentOrchestrator:
    def __init__(self) -> None:
        cfg = get_config()
        self._llm = None
        self.rule_strict = cfg.get("agents", {}).get("rule_strict", True)
        catalog = get_drug_catalog_service()
        kb = CatalogAwareKnowledgeBase(catalog=catalog) if catalog.is_loaded() else None
        self.review_engine = ReviewEngine(kb=kb) if kb else ReviewEngine()
        self.chief = None
        self.coordinator = None
        self.debate_engine = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    def _ensure_core(self) -> None:
        if self.chief is not None:
            return
        self.chief = ChiefReviewerAgent(self.llm, rule_strict=self.rule_strict)
        self.coordinator = CoordinatorAgent(self.llm)
        self.debate_engine = DebateEngine(
            self.llm,
            agents=[],
            safety_panel=SafetyPanel(self.review_engine),
        )

    def _default_runtime_config(self) -> dict[str, Any]:
        registry = get_agent_registry()
        agent_enabled: dict[str, bool] = {}
        skills_enabled: dict[str, list[str]] = {}
        for spec in registry.list_specs():
            if not spec.debate or spec.is_department_agent:
                continue
            agent_enabled[spec.agent_id] = spec.default_enabled
            skills_enabled[spec.agent_id] = list(spec.default_skills)
        for spec in registry.list_department_agent_specs():
            agent_enabled[spec.agent_id] = spec.default_enabled
            skills_enabled[spec.agent_id] = list(spec.default_skills)
        return {
            "agent_enabled": agent_enabled,
            "skills_enabled": skills_enabled,
            "custom_skill_bodies": [],
        }

    def _resolve_department_context(self, patient_context: PatientContext) -> DepartmentContext | None:
        dept_id = (patient_context.department or "").strip()
        return get_department_context(dept_id) if dept_id else None

    def _agent_enabled(self, runtime_config: dict[str, Any], agent_id: str, default: bool) -> bool:
        return bool(runtime_config.get("agent_enabled", {}).get(agent_id, default))

    def _enabled_skills(self, runtime_config: dict[str, Any], agent_id: str, default: list[str]) -> list[str]:
        return list(runtime_config.get("skills_enabled", {}).get(agent_id, default))

    def _custom_bodies_for(self, runtime_config: dict[str, Any], agent_id: str) -> list[str]:
        custom = runtime_config.get("custom_skill_bodies") or []
        return [c["content_md"] for c in custom if c.get("agent_id") == agent_id and c.get("content_md")]

    def _active_agents(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        department_context: DepartmentContext | None = None,
        runtime_config: dict[str, Any] | None = None,
    ) -> list:
        self._ensure_core()
        registry = get_agent_registry()
        cfg = runtime_config or self._default_runtime_config()
        dept_ctx = department_context or self._resolve_department_context(patient_context)

        agents = registry.create_debate_agents(
            self.llm,
            agent_enabled=cfg.get("agent_enabled"),
            skills_enabled=cfg.get("skills_enabled"),
            custom_skills=cfg.get("custom_skill_bodies"),
        )

        specialist_spec = registry.get_spec("specialist")
        if (
            specialist_spec
            and SpecialistAgent.should_activate(patient_context, candidate_drugs)
            and self._agent_enabled(cfg, "specialist", specialist_spec.default_enabled)
        ):
            skill_ids = self._enabled_skills(cfg, "specialist", list(specialist_spec.default_skills))
            agents.append(
                registry.create_agent(
                    "specialist",
                    self.llm,
                    enabled_skills=skill_ids,
                    custom_skill_bodies=self._custom_bodies_for(cfg, "specialist"),
                )
            )

        for spec in registry.list_department_agent_specs():
            if not DepartmentSpecialistAgent.should_activate(
                spec.agent_id,
                patient_context,
                candidate_drugs,
                dept_ctx,
            ):
                continue
            if not self._agent_enabled(cfg, spec.agent_id, spec.default_enabled):
                continue
            skill_ids = self._enabled_skills(cfg, spec.agent_id, list(spec.default_skills))
            agent = registry.create_department_agent(
                spec.agent_id,
                self.llm,
                dept_ctx,
                enabled_skills=skill_ids,
                custom_skill_bodies=self._custom_bodies_for(cfg, spec.agent_id),
            )
            if agent:
                agents.append(agent)

        agents.sort(key=lambda a: a.agent_id)
        return agents

    def run(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        unable_to_answer: bool = False,
        skip_clarify: bool = False,
        rule_output: ReviewOutput | None = None,
        runtime_config: dict[str, Any] | None = None,
    ) -> MultiReviewResponse:
        self._ensure_core()
        dept_ctx = self._resolve_department_context(patient_context)
        if rule_output is None:
            rule_output = self.review_engine.review(
                patient_context,
                candidate_drugs,
                department=patient_context.department or None,
                priority_categories=dept_ctx.priority_categories if dept_ctx else None,
            )
        agents = self._active_agents(
            patient_context,
            candidate_drugs,
            department_context=dept_ctx,
            runtime_config=runtime_config,
        )

        self.debate_engine.agents = agents
        agent_opinions, debate, safety_panel = self.debate_engine.run(
            patient_context, candidate_drugs, rule_output.evidence
        )

        arbitration = self.chief.arbitrate(
            agent_opinions,
            rule_output,
            debate=debate,
            safety_panel=safety_panel,
        )

        if safety_panel.block_recommended and self.rule_strict:
            arbitration.consensus_block_decision = True
            if rule_output.risk_level in {"high", "unknown"}:
                arbitration.consensus_risk_level = rule_output.risk_level

        if debate.flagged_for_human:
            arbitration.arbitration_notes += "；辩论未达共识，已标记人工复核。"
            arbitration.need_clarification = True

        clarify_output: ClarifyOutput | None = None
        final_recommendation = arbitration.final_recommendation

        review_for_clarify = ReviewOutput(
            risk_level=arbitration.consensus_risk_level,
            block_decision=arbitration.consensus_block_decision,
            risk_reasons=arbitration.final_recommendation.split("。")[:3],
            need_clarification=arbitration.need_clarification,
            clarification_targets=arbitration.clarification_targets,
            evidence=rule_output.evidence,
            final_recommendation=arbitration.final_recommendation,
        )

        if not skip_clarify and (arbitration.need_clarification or unable_to_answer or debate.flagged_for_human):
            clarify_output = self.coordinator.clarify(
                patient_context, candidate_drugs, review_for_clarify, unable_to_answer=unable_to_answer
            )
            if clarify_output.status == "need_user_input" and clarify_output.final_message:
                final_recommendation = clarify_output.final_message
            elif unable_to_answer and clarify_output.final_message:
                final_recommendation = clarify_output.final_message

        return MultiReviewResponse(
            rule_output=rule_output,
            agent_opinions=agent_opinions,
            debate=debate,
            safety_panel=safety_panel,
            arbitration=arbitration,
            clarify_output=clarify_output,
            final_recommendation=final_recommendation,
        )

    def list_agents(self) -> list[dict]:
        registry = get_agent_registry()
        return [
            {
                "agent_id": spec.agent_id,
                "agent_name": spec.agent_name,
                "role": spec.role,
                "is_department_agent": spec.is_department_agent,
            }
            for spec in registry.list_specs()
            if spec.debate
        ]
