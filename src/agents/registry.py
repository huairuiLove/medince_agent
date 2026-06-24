"""Pluggable agent registry — loads datasets/agents/registry.yaml and instantiates agents with skills."""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from src.agents.base import BaseAgent
from src.agents.skill_loader import SkillSpec, compose_system_prompt, load_skill_body, skills_root
from src.config import datasets_path, resolve_path
from src.department.context import DepartmentContext
from src.llm.client import LLMClient
from src.schemas import CandidateDrug, PatientContext


@dataclass
class AgentSpec:
    agent_id: str
    agent_name: str
    role: str
    module: str
    class_name: str
    debate: bool = True
    default_enabled: bool = True
    default_skills: list[str] = field(default_factory=lambda: ["base"])
    skills: list[SkillSpec] = field(default_factory=list)
    activate_when: dict[str, Any] = field(default_factory=dict)
    is_department_agent: bool = False


class AgentRegistry:
    def __init__(self, registry_path: Path | None = None) -> None:
        path = registry_path or datasets_path("agents/registry.yaml")
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        self._specs: dict[str, AgentSpec] = {}
        for _key, item in (raw.get("agents") or {}).items():
            self._register_item(item, is_department_agent=False)
        for _key, item in (raw.get("department_agents") or {}).items():
            self._register_item(item, is_department_agent=True)

    def _parse_skills(self, item: dict[str, Any]) -> tuple[list[str], list[SkillSpec]]:
        raw_skills = item.get("skills") or []
        default_skills = list(item.get("default_skills") or [])
        specs: list[SkillSpec] = []
        if raw_skills and isinstance(raw_skills[0], str):
            skill_ids = [str(s) for s in raw_skills]
            specs = [SkillSpec(skill_id=s, title=s, description="", filename=f"{s}.md") for s in skill_ids]
            if not default_skills:
                default_skills = skill_ids
        else:
            for s in raw_skills:
                specs.append(
                    SkillSpec(
                        skill_id=s["id"],
                        title=s.get("title", s["id"]),
                        description=s.get("description", ""),
                        filename=s.get("file", f"{s['id']}.md"),
                    )
                )
            if not default_skills and specs:
                default_skills = [sk.skill_id for sk in specs]
        if not default_skills:
            default_skills = ["base"]
        return default_skills, specs

    def _register_item(self, item: dict[str, Any], *, is_department_agent: bool) -> None:
        default_skills, skill_specs = self._parse_skills(item)
        spec = AgentSpec(
            agent_id=item["agent_id"],
            agent_name=item["agent_name"],
            role=item["role"],
            module=item.get("module", "src.agents.department_specialist"),
            class_name=item.get("class", "DepartmentSpecialistAgent"),
            debate=bool(item.get("debate", True)),
            default_enabled=bool(item.get("default_enabled", False if is_department_agent else True)),
            default_skills=default_skills,
            skills=skill_specs,
            activate_when=dict(item.get("activate_when") or {}),
            is_department_agent=is_department_agent,
        )
        self._specs[spec.agent_id] = spec

    def list_specs(self) -> list[AgentSpec]:
        return list(self._specs.values())

    def get_spec(self, agent_id: str) -> AgentSpec | None:
        return self._specs.get(agent_id)

    def list_skills(self, agent_id: str) -> list[SkillSpec]:
        spec = self._specs.get(agent_id)
        return list(spec.skills) if spec else []

    def list_department_agent_specs(self) -> list[AgentSpec]:
        return [s for s in self._specs.values() if s.is_department_agent]

    def get_department_agent_spec(self, agent_id: str) -> AgentSpec | None:
        spec = self._specs.get(agent_id)
        return spec if spec and spec.is_department_agent else None

    def should_activate_department_agent(
        self,
        spec: AgentSpec,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        department_context: DepartmentContext | None = None,
    ) -> bool:
        cfg = spec.activate_when
        if cfg.get("always"):
            return True

        dept_ids = [d.lower() for d in cfg.get("departments", [])]
        patient_dept = (patient_context.department or "").lower()
        context_dept = (department_context.dept_id if department_context else "").lower()
        if dept_ids and (patient_dept in dept_ids or context_dept in dept_ids):
            return True

        drug_text = " ".join(
            f"{d.name} {d.ingredient}".lower() for d in candidate_drugs
        )
        for keyword in cfg.get("drug_keywords", []):
            if str(keyword).lower() in drug_text:
                return True

        for drug_class in cfg.get("drug_classes", []):
            if str(drug_class).lower() in drug_text:
                return True

        if cfg.get("age_lt") is not None and patient_context.age is not None:
            if patient_context.age < int(cfg["age_lt"]):
                return True

        pregnancy = (patient_context.pregnancy_status or "").lower()
        if cfg.get("pregnancy_active") and pregnancy not in {"", "unknown", "not_applicable", "none"}:
            return True

        return False

    def should_activate_specialist(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
    ) -> bool:
        spec = self._specs.get("specialist")
        if not spec:
            return False
        cfg = spec.activate_when
        drug_names = " ".join(d.name.lower() for d in candidate_drugs)
        keywords = [k.lower() for k in cfg.get("drug_keywords", [])]
        if keywords and any(k in drug_names for k in keywords):
            return True
        if cfg.get("female_reproductive_age") and str(patient_context.gender).upper() in {"F", "FEMALE"}:
            if patient_context.age is None or 12 <= patient_context.age <= 55:
                return True
        age_gte = cfg.get("age_gte")
        if age_gte is not None and patient_context.age and patient_context.age >= int(age_gte):
            return True
        return False

    def _import_class(self, spec: AgentSpec) -> type:
        mod = importlib.import_module(spec.module)
        return getattr(mod, spec.class_name)

    def create_agent(
        self,
        agent_id: str,
        llm: LLMClient,
        enabled_skills: list[str] | None = None,
        custom_skill_bodies: list[str] | None = None,
        rule_strict: bool = True,
    ) -> Any:
        spec = self._specs[agent_id]
        cls = self._import_class(spec)
        skill_ids = enabled_skills if enabled_skills is not None else list(spec.default_skills)

        if agent_id == "chief_reviewer":
            return cls(llm, rule_strict=rule_strict)
        if agent_id == "coordinator":
            return cls(llm)

        prompt = compose_system_prompt(agent_id, skill_ids, custom_skill_bodies)
        if spec.is_department_agent:
            return cls(
                llm,
                agent_id=spec.agent_id,
                agent_name=spec.agent_name,
                role=spec.role,
                system_prompt=prompt,
            )
        return cls(llm, system_prompt=prompt)

    def create_department_agent(
        self,
        agent_id: str,
        llm: LLMClient,
        department_context: DepartmentContext | None = None,
        enabled_skills: list[str] | None = None,
        custom_skill_bodies: list[str] | None = None,
    ) -> Any | None:
        spec = self.get_department_agent_spec(agent_id)
        if not spec:
            return None
        variables = {}
        if department_context:
            variables = {
                "department": department_context.name_cn or department_context.dept_id,
                "dept_id": department_context.dept_id,
                "priority_categories": ", ".join(department_context.priority_categories),
                "lab_context_defaults": ", ".join(department_context.lab_context_defaults),
                "common_indications": ", ".join(department_context.common_indications),
            }
        skill_ids = enabled_skills if enabled_skills is not None else list(spec.default_skills)
        prompt = compose_system_prompt(
            agent_id,
            skill_ids,
            custom_skill_bodies=custom_skill_bodies,
            template_variables=variables,
        )
        cls = self._import_class(spec)
        return cls(
            llm,
            agent_id=spec.agent_id,
            agent_name=spec.agent_name,
            role=spec.role,
            system_prompt=prompt,
            department=variables.get("department", ""),
            common_indications=list(department_context.common_indications) if department_context else [],
            priority_categories=list(department_context.priority_categories) if department_context else [],
        )

    def create_debate_agents(
        self,
        llm: LLMClient,
        agent_enabled: dict[str, bool] | None = None,
        skills_enabled: dict[str, list[str]] | None = None,
        custom_skills: list[dict] | None = None,
    ) -> list[BaseAgent]:
        enabled_map = agent_enabled or {}
        skills_map = skills_enabled or {}
        custom = custom_skills or []
        agents: list[BaseAgent] = []
        for spec in self._specs.values():
            if not spec.debate or spec.is_department_agent:
                continue
            if not enabled_map.get(spec.agent_id, spec.default_enabled):
                continue
            bodies = [c["content_md"] for c in custom if c.get("agent_id") == spec.agent_id]
            skill_ids = skills_map.get(spec.agent_id, list(spec.default_skills))
            agent = self.create_agent(spec.agent_id, llm, enabled_skills=skill_ids, custom_skill_bodies=bodies)
            agents.append(agent)
        agents.sort(key=lambda a: a.agent_id)
        return agents

    def list_agent_info(self) -> list[dict]:
        return [
            {
                "agent_id": s.agent_id,
                "agent_name": s.agent_name,
                "role": s.role,
                "debate": s.debate,
                "default_enabled": s.default_enabled,
                "is_department_agent": s.is_department_agent,
                "skills": [{"skill_id": sk.skill_id, "title": sk.title} for sk in s.skills],
            }
            for s in self._specs.values()
        ]


_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
