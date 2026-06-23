"""Auth service — users, departments, doctor agent/skill preferences."""
from __future__ import annotations

import sqlite3
from typing import Any

from src.agents.registry import get_agent_registry
from src.auth.db import (
    _utc_now,
    connect,
    default_db_path,
    init_schema,
    json_loads,
    new_skill_id,
    new_user_id,
    row_to_dict,
)
from src.auth.department_catalog import department_rows_for_db, load_department_catalog
from src.auth.models import (
    AgentConfigInfo,
    AgentSkillInfo,
    CreateCustomSkillRequest,
    DepartmentInfo,
    DoctorWorkspaceResponse,
    TokenResponse,
    UserProfile,
)
from src.auth.password import hash_password, verify_password
from src.auth.tokens import create_access_token, decode_access_token
from src.config import get_config
from src.department.context import get_department_context


class AuthService:
    def __init__(self, db_path=None) -> None:
        self.db_path = db_path or default_db_path()
        self._conn: sqlite3.Connection | None = None
        self._catalog = load_department_catalog()
        self._registry = get_agent_registry()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = connect(self.db_path)
            init_schema(self._conn)
            self._seed_if_empty()
            self._seed_chief_pharm_if_missing()
            self._migrate_department_agent_prefs_v1()
        return self._conn

    def _secret(self) -> str:
        cfg = get_config()
        secret = cfg.get("auth", {}).get("jwt_secret") or ""
        if not secret:
            secret = "medsafe-dev-secret-change-in-production"
        return secret

    def _ttl_hours(self) -> int:
        return int(get_config().get("auth", {}).get("token_ttl_hours", 72))

    def _seed_if_empty(self) -> None:
        row = self.conn.execute("SELECT COUNT(*) AS c FROM departments").fetchone()
        if row and row["c"] == 0:
            for dept in department_rows_for_db(self._catalog):
                self.conn.execute(
                    """
                    INSERT INTO departments (
                        dept_id, name_cn, name_en, imaging_sources_json, default_models_json,
                        recommended_datasets_json, vision_models_json, nav_routes_json,
                        description, sort_order
                    ) VALUES (
                        :dept_id, :name_cn, :name_en, :imaging_sources_json, :default_models_json,
                        :recommended_datasets_json, :vision_models_json, :nav_routes_json,
                        :description, :sort_order
                    )
                    """,
                    dept,
                )
            self.conn.commit()

        user_count = self.conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        if user_count and user_count["c"] == 0:
            demos = [
                ("resp_doc", "呼吸科张医生", "respiratory", "resp123", "doctor"),
                ("neuro_doc", "神内李医生", "neurology", "neuro123", "doctor"),
                ("radio_admin", "放射科管理员", "radiology", "admin123", "admin"),
                ("pharm_doc", "临床药师王", "pharmacy", "pharm123", "pharmacist"),
                ("chief_pharm", "主管药师陈", "pharmacy", "chief123", "pharmacist"),
            ]
            now = _utc_now()
            for username, display, dept_id, password, role in demos:
                uid = new_user_id()
                self.conn.execute(
                    """
                    INSERT INTO users (user_id, username, password_hash, display_name, role, dept_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (uid, username, hash_password(password), display, role, dept_id, now),
                )
                self._init_default_agent_prefs(uid, dept_id)
            self.conn.commit()

    def _seed_chief_pharm_if_missing(self) -> None:
        self.conn.execute(
            "UPDATE users SET role = 'pharmacist' WHERE username = 'pharm_doc' AND role = 'doctor'"
        )
        row = self.conn.execute(
            "SELECT user_id FROM users WHERE username = ?",
            ("chief_pharm",),
        ).fetchone()
        if row:
            return
        uid = new_user_id()
        now = _utc_now()
        self.conn.execute(
            """
            INSERT INTO users (user_id, username, password_hash, display_name, role, dept_id, created_at)
            VALUES (?, ?, ?, ?, 'pharmacist', 'pharmacy', ?)
            """,
            (uid, "chief_pharm", hash_password("chief123"), "主管药师陈", now),
        )
        self._init_default_agent_prefs(uid, "pharmacy")
        self.conn.commit()

    @staticmethod
    def is_pharmacy_role(role: str) -> bool:
        return role in {"admin", "pharmacist"}

    def _department_auto_enable_agent_ids(self, dept_id: str) -> set[str]:
        """Department specialist agents that should default to enabled for this dept."""
        dept_id = (dept_id or "").strip()
        if not dept_id:
            return set()

        auto: set[str] = set()
        ctx = get_department_context(dept_id)
        if ctx:
            conditional = ctx.review_config.get("conditional_agents") or {}
            for agent_id, cfg in conditional.items():
                if cfg is True or (isinstance(cfg, dict) and cfg.get("always")):
                    auto.add(str(agent_id))

        dept_lower = dept_id.lower()
        for spec in self._registry.list_department_agent_specs():
            dept_ids = [str(d).lower() for d in spec.activate_when.get("departments", [])]
            if dept_lower in dept_ids:
                auto.add(spec.agent_id)
        return auto

    def _init_default_agent_prefs(self, user_id: str, dept_id: str = "") -> None:
        auto_ids = self._department_auto_enable_agent_ids(dept_id)
        for spec in self._registry.list_specs():
            if not spec.debate:
                continue
            enabled = spec.default_enabled or spec.agent_id in auto_ids
            self.conn.execute(
                "INSERT OR IGNORE INTO doctor_agent_prefs (user_id, agent_id, enabled) VALUES (?, ?, ?)",
                (user_id, spec.agent_id, 1 if enabled else 0),
            )
            for skill in self._registry.list_skills(spec.agent_id):
                default_on = skill.skill_id in spec.default_skills or skill.skill_id == "base"
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO doctor_skill_prefs (user_id, agent_id, skill_id, enabled)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, spec.agent_id, skill.skill_id, 1 if default_on else 0),
                )

    def _migrate_department_agent_prefs_v1(self) -> None:
        """One-time: enable department specialist agents for existing users by dept."""
        row = self.conn.execute(
            "SELECT value FROM auth_meta WHERE key = 'dept_agent_prefs_v1'",
        ).fetchone()
        if row:
            return
        for user in self.conn.execute("SELECT user_id, dept_id FROM users").fetchall():
            for agent_id in self._department_auto_enable_agent_ids(user["dept_id"]):
                self.conn.execute(
                    """
                    UPDATE doctor_agent_prefs SET enabled = 1
                    WHERE user_id = ? AND agent_id = ?
                    """,
                    (user["user_id"], agent_id),
                )
        self.conn.execute(
            "INSERT INTO auth_meta (key, value) VALUES ('dept_agent_prefs_v1', 'done')",
        )
        self.conn.commit()

    def login(self, username: str, password: str) -> TokenResponse | None:
        row = self.conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1",
            (username.strip(),),
        ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        token = create_access_token(row["user_id"], self._secret(), self._ttl_hours())
        return TokenResponse(access_token=token, expires_in_hours=self._ttl_hours())

    def register(self, username: str, password: str, display_name: str, dept_id: str) -> UserProfile | None:
        if self.get_department(dept_id) is None:
            return None
        uid = new_user_id()
        now = _utc_now()
        try:
            self.conn.execute(
                """
                INSERT INTO users (user_id, username, password_hash, display_name, role, dept_id, created_at)
                VALUES (?, ?, ?, ?, 'doctor', ?, ?)
                """,
                (uid, username.strip(), hash_password(password), display_name or username, dept_id, now),
            )
            self._init_default_agent_prefs(uid, dept_id)
            self.conn.commit()
        except sqlite3.IntegrityError:
            return None
        return self.get_user_profile(uid)

    def resolve_user_id(self, token: str) -> str | None:
        payload = decode_access_token(token, self._secret())
        if not payload:
            return None
        sub = payload.get("sub")
        if not isinstance(sub, str):
            return None
        row = self.conn.execute(
            "SELECT user_id FROM users WHERE user_id = ? AND is_active = 1",
            (sub,),
        ).fetchone()
        return row["user_id"] if row else None

    def get_department(self, dept_id: str) -> DepartmentInfo | None:
        row = self.conn.execute("SELECT * FROM departments WHERE dept_id = ?", (dept_id,)).fetchone()
        if not row:
            spec = self._catalog.get(dept_id)
            if spec:
                return DepartmentInfo(**spec.to_dict())
            return None
        return DepartmentInfo(
            dept_id=row["dept_id"],
            name_cn=row["name_cn"],
            name_en=row["name_en"],
            imaging_sources=json_loads(row["imaging_sources_json"], []),
            default_models=json_loads(row["default_models_json"], []),
            recommended_datasets=json_loads(row["recommended_datasets_json"], []),
            vision_models=json_loads(row["vision_models_json"], []),
            nav_routes=json_loads(row["nav_routes_json"], []),
            description=row["description"],
        )

    def list_departments(self) -> list[DepartmentInfo]:
        rows = self.conn.execute("SELECT * FROM departments ORDER BY sort_order, name_cn").fetchall()
        return [
            DepartmentInfo(
                dept_id=r["dept_id"],
                name_cn=r["name_cn"],
                name_en=r["name_en"],
                imaging_sources=json_loads(r["imaging_sources_json"], []),
                default_models=json_loads(r["default_models_json"], []),
                recommended_datasets=json_loads(r["recommended_datasets_json"], []),
                vision_models=json_loads(r["vision_models_json"], []),
                nav_routes=json_loads(r["nav_routes_json"], []),
                description=r["description"],
            )
            for r in rows
        ]

    def get_user_profile(self, user_id: str) -> UserProfile | None:
        row = self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return None
        dept = self.get_department(row["dept_id"])
        return UserProfile(
            user_id=row["user_id"],
            username=row["username"],
            display_name=row["display_name"],
            role=row["role"],
            dept_id=row["dept_id"],
            department=dept,
        )

    def get_agent_prefs(self, user_id: str) -> dict[str, bool]:
        rows = self.conn.execute(
            "SELECT agent_id, enabled FROM doctor_agent_prefs WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        if not rows:
            return {s.agent_id: s.default_enabled for s in self._registry.list_specs() if s.debate}
        return {r["agent_id"]: bool(r["enabled"]) for r in rows}

    def get_skill_prefs(self, user_id: str) -> dict[tuple[str, str], bool]:
        rows = self.conn.execute(
            "SELECT agent_id, skill_id, enabled FROM doctor_skill_prefs WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        prefs: dict[tuple[str, str], bool] = {}
        for r in rows:
            prefs[(r["agent_id"], r["skill_id"])] = bool(r["enabled"])
        return prefs

    def get_custom_skills(self, user_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT skill_id, agent_id, title, content_md, created_at FROM doctor_custom_skills WHERE user_id = ? ORDER BY created_at",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_workspace(self, user_id: str) -> DoctorWorkspaceResponse | None:
        profile = self.get_user_profile(user_id)
        if not profile:
            return None
        agent_prefs = self.get_agent_prefs(user_id)
        skill_prefs = self.get_skill_prefs(user_id)
        custom = self.get_custom_skills(user_id)

        agents: list[AgentConfigInfo] = []
        for spec in self._registry.list_specs():
            if not spec.debate:
                continue
            skills_meta = self._registry.list_skills(spec.agent_id)
            enabled_skills = [
                s.skill_id
                for s in skills_meta
                if skill_prefs.get((spec.agent_id, s.skill_id), s.skill_id in spec.default_skills or s.skill_id == "base")
            ]
            agents.append(
                AgentConfigInfo(
                    agent_id=spec.agent_id,
                    agent_name=spec.agent_name,
                    role=spec.role,
                    debate=spec.debate,
                    enabled=agent_prefs.get(spec.agent_id, spec.default_enabled),
                    is_department_agent=spec.is_department_agent,
                    available_skills=[
                        AgentSkillInfo(
                            skill_id=s.skill_id,
                            title=s.title,
                            description=s.description,
                            builtin=True,
                            enabled=skill_prefs.get((spec.agent_id, s.skill_id), s.skill_id in enabled_skills),
                        )
                        for s in skills_meta
                    ],
                    enabled_skills=enabled_skills,
                )
            )
        return DoctorWorkspaceResponse(profile=profile, agents=agents, custom_skills=custom)

    def update_agent_prefs(self, user_id: str, updates: list[dict]) -> None:
        for item in updates:
            aid = item.get("agent_id")
            if not aid:
                continue
            enabled = 1 if item.get("enabled", True) else 0
            self.conn.execute(
                """
                INSERT INTO doctor_agent_prefs (user_id, agent_id, enabled) VALUES (?, ?, ?)
                ON CONFLICT(user_id, agent_id) DO UPDATE SET enabled = excluded.enabled
                """,
                (user_id, aid, enabled),
            )
        self.conn.commit()

    def update_skill_prefs(self, user_id: str, updates: list[dict]) -> None:
        for item in updates:
            aid = item.get("agent_id")
            sid = item.get("skill_id")
            if not aid or not sid:
                continue
            enabled = 1 if item.get("enabled", True) else 0
            self.conn.execute(
                """
                INSERT INTO doctor_skill_prefs (user_id, agent_id, skill_id, enabled) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, agent_id, skill_id) DO UPDATE SET enabled = excluded.enabled
                """,
                (user_id, aid, sid, enabled),
            )
        self.conn.commit()

    def add_custom_skill(self, user_id: str, req: CreateCustomSkillRequest) -> dict:
        sid = new_skill_id()
        now = _utc_now()
        self.conn.execute(
            """
            INSERT INTO doctor_custom_skills (skill_id, user_id, agent_id, title, content_md, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (sid, user_id, req.agent_id, req.title, req.content_md, now),
        )
        self.conn.execute(
            """
            INSERT INTO doctor_skill_prefs (user_id, agent_id, skill_id, enabled) VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id, agent_id, skill_id) DO UPDATE SET enabled = 1
            """,
            (user_id, req.agent_id, sid),
        )
        self.conn.commit()
        return {"skill_id": sid, "agent_id": req.agent_id, "title": req.title, "created_at": now}

    def delete_custom_skill(self, user_id: str, skill_id: str) -> bool:
        cur = self.conn.execute(
            "DELETE FROM doctor_custom_skills WHERE skill_id = ? AND user_id = ?",
            (skill_id, user_id),
        )
        self.conn.execute(
            "DELETE FROM doctor_skill_prefs WHERE user_id = ? AND skill_id = ?",
            (user_id, skill_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def build_agent_runtime_config(self, user_id: str | None) -> dict[str, Any]:
        """Return enabled agents + composed skill ids for orchestrator."""
        if not user_id:
            return {
                "agent_enabled": {s.agent_id: s.default_enabled for s in self._registry.list_specs() if s.debate},
                "skills_enabled": {},
                "custom_skill_bodies": [],
            }
        agent_prefs = self.get_agent_prefs(user_id)
        skill_prefs = self.get_skill_prefs(user_id)
        custom = self.get_custom_skills(user_id)
        skills_enabled: dict[str, list[str]] = {}
        for spec in self._registry.list_specs():
            if not spec.debate:
                continue
            enabled = [
                s.skill_id
                for s in self._registry.list_skills(spec.agent_id)
                if skill_prefs.get((spec.agent_id, s.skill_id), s.skill_id in spec.default_skills or s.skill_id == "base")
            ]
            for c in custom:
                if c["agent_id"] == spec.agent_id and skill_prefs.get((spec.agent_id, c["skill_id"]), True):
                    enabled.append(c["skill_id"])
            skills_enabled[spec.agent_id] = enabled
        return {
            "agent_enabled": agent_prefs,
            "skills_enabled": skills_enabled,
            "custom_skill_bodies": custom,
        }


_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
