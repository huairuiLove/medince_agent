"""Load agent skill markdown fragments."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.config import datasets_path
from src.prompts import _AGENT_JSON_SCHEMA


@dataclass(frozen=True)
class SkillSpec:
    skill_id: str
    title: str
    description: str
    filename: str


def skills_root() -> Path:
    return datasets_path("agents")


def load_skill_body(agent_id: str, skill_id: str) -> str:
    path = skills_root() / agent_id / f"{skill_id}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def compose_system_prompt(
    agent_id: str,
    enabled_skill_ids: list[str],
    custom_bodies: list[str] | None = None,
) -> str:
    parts: list[str] = []
    for sid in enabled_skill_ids:
        if sid.startswith("csk_"):
            continue
        body = load_skill_body(agent_id, sid)
        if body:
            parts.append(body)
    if custom_bodies:
        for body in custom_bodies:
            if body.strip():
                parts.append(body.strip())
    if not parts:
        fallback = load_skill_body(agent_id, "base")
        if fallback:
            parts.append(fallback)
    parts.append(_AGENT_JSON_SCHEMA)
    return "\n\n".join(parts)
