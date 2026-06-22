"""Auth Pydantic schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=4, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(default="", max_length=128)
    dept_id: str = Field(min_length=2, max_length=64)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_hours: int


class DepartmentInfo(BaseModel):
    dept_id: str
    name_cn: str
    name_en: str = ""
    imaging_sources: list[str] = []
    default_models: list[str] = []
    recommended_datasets: list[dict] = []
    vision_models: list[dict] = []
    nav_routes: list[str] = []
    description: str = ""


class UserProfile(BaseModel):
    user_id: str
    username: str
    display_name: str
    role: str
    dept_id: str
    department: DepartmentInfo | None = None


class AgentSkillInfo(BaseModel):
    skill_id: str
    title: str
    description: str = ""
    builtin: bool = True
    enabled: bool = True


class AgentConfigInfo(BaseModel):
    agent_id: str
    agent_name: str
    role: str
    debate: bool = True
    enabled: bool = True
    available_skills: list[AgentSkillInfo] = []
    enabled_skills: list[str] = []


class DoctorWorkspaceResponse(BaseModel):
    profile: UserProfile
    agents: list[AgentConfigInfo] = []
    custom_skills: list[dict] = []


class UpdateAgentPrefsRequest(BaseModel):
    agents: list[dict]  # [{agent_id, enabled}]


class UpdateSkillPrefsRequest(BaseModel):
    skills: list[dict]  # [{agent_id, skill_id, enabled}]


class CreateCustomSkillRequest(BaseModel):
    agent_id: str
    title: str = Field(min_length=1, max_length=128)
    content_md: str = Field(min_length=1, max_length=8000)
