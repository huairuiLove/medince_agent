"""Department-specific specialist agents activated by dept context and drug patterns."""

from __future__ import annotations

from src.agents.base import LLMAgent
from src.agents.registry import get_agent_registry
from src.department.context import DepartmentContext
from src.llm.client import LLMClient
from src.schemas import CandidateDrug, PatientContext
from src.utils import normalize_text


class DepartmentSpecialistAgent(LLMAgent):
    """Configurable department agent — agent_id set at construction from registry."""

    def __init__(
        self,
        llm: LLMClient,
        agent_id: str,
        agent_name: str,
        role: str,
        system_prompt: str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.role = role
        self.system_prompt = system_prompt or ""
        super().__init__(llm, system_prompt=system_prompt)

    @staticmethod
    def should_activate(
        agent_id: str,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        department_context: DepartmentContext | None = None,
    ) -> bool:
        registry = get_agent_registry()
        spec = registry.get_department_agent_spec(agent_id)
        if not spec:
            return False
        return registry.should_activate_department_agent(
            spec,
            patient_context,
            candidate_drugs,
            department_context,
        )
