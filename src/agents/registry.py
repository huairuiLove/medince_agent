"""Pluggable agent registry — loads data/agents/registry.yaml and instantiates agents with skills."""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from src.agents.base import BaseAgent
from src.agents.skill_loader import SkillSpec, compose_system_prompt, load_skill_body, skills_root
from src.config import resolve_path
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


class AgentRegistry:
    def __init__(self, registry_path: Path | None = None) -> None:
        path = registry_path or resolve_path("data/agents/registry.yaml")
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        self._specs: dict[str, AgentSpec] = {}
        for _key, item in (raw.get("agents") or {}).items():
            spec = AgentSpec(
                agent_id=item["agent_id"],
                agent_name=item["agent_name"],
                role=item["role"],
                module=item["module"],
                class_name=item["class"],
                debate=bool(item.get("debate", True)),
                default_enabled=bool(item.get("default_enabled", True)),
                default_skills=list(item.get("default_skills", ["base"])),
                skills=[
                    SkillSpec(
                        skill_id=s["id"],
                        title=s.get("title", s["id"]),
                        description=s.get("description", ""),
                        filename=s.get("file", f"{s['id']}.md"),
                    )
                    for s in item.get("skills", [])
                ],
                activate_when=dict(item.get("activate_when") or {}),
            )
            self._specs[spec.agent_id] = spec

    def list_specs(self) -> list[AgentSpec]:
        return list(self._specs.values())

    def get_spec(self, agent_id: str) -> AgentSpec | None:
        return self._specs.get(agent_id)

    def list_skills(self, agent_id: str) -> list[SkillSpec]:
        spec = self._specs.get(agent_id)
        return list(spec.skills) if spec else []

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
        return cls(llm, system_prompt=prompt)

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
            if not spec.debate:
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
