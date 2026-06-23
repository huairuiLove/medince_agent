"""Doctor agent prefs auto-enable department specialists by dept."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.auth.service import AuthService


def test_radiology_user_gets_radiology_specialist_enabled() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "auth.db"
        svc = AuthService(db_path=db)
        _ = svc.conn

        profile = svc.register("radio_test", "pass1234", "放射测试", "radiology")
        assert profile is not None

        prefs = svc.get_agent_prefs(profile.user_id)
        assert prefs.get("radiology_specialist") is True

        workspace = svc.get_workspace(profile.user_id)
        assert workspace is not None
        radio = next(a for a in workspace.agents if a.agent_id == "radiology_specialist")
        assert radio.enabled is True
        assert radio.is_department_agent is True


def test_migration_enables_existing_radiology_user() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "auth.db"
        svc = AuthService(db_path=db)
        conn = svc.conn

        uid = "usr_test123456"
        conn.execute(
            """
            INSERT INTO users (user_id, username, password_hash, display_name, role, dept_id, created_at)
            VALUES (?, 'legacy_radio', 'x', '旧放射账号', 'doctor', 'radiology', '2020-01-01T00:00:00+00:00')
            """,
            (uid,),
        )
        conn.execute(
            "INSERT INTO doctor_agent_prefs (user_id, agent_id, enabled) VALUES (?, 'radiology_specialist', 0)",
            (uid,),
        )
        conn.execute("DELETE FROM auth_meta WHERE key = 'dept_agent_prefs_v1'")
        conn.commit()

        svc._migrate_department_agent_prefs_v1()

        prefs = svc.get_agent_prefs(uid)
        assert prefs.get("radiology_specialist") is True


def test_v2_migration_backfills_missing_respiratory_specialist() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "auth.db"
        svc = AuthService(db_path=db)
        conn = svc.conn

        uid = "usr_resp_legacy01"
        conn.execute(
            """
            INSERT INTO users (user_id, username, password_hash, display_name, role, dept_id, created_at)
            VALUES (?, 'legacy_resp', 'x', '旧呼吸账号', 'doctor', 'respiratory', '2020-01-01T00:00:00+00:00')
            """,
            (uid,),
        )
        conn.execute(
            "INSERT INTO doctor_agent_prefs (user_id, agent_id, enabled) VALUES (?, 'clinical_pharmacist', 1)",
            (uid,),
        )
        conn.execute("DELETE FROM auth_meta WHERE key = 'dept_agent_prefs_v2'")
        conn.commit()

        svc._migrate_department_agent_prefs_v2()

        prefs = svc.get_agent_prefs(uid)
        assert prefs.get("respiratory_specialist") is True


def test_workspace_hides_other_department_agents() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "auth.db"
        svc = AuthService(db_path=db)
        profile = svc.register("resp_hide_test", "pass1234", "呼吸测试", "respiratory")
        assert profile is not None

        workspace = svc.get_workspace(profile.user_id)
        assert workspace is not None
        agent_ids = {a.agent_id for a in workspace.agents}
        assert "respiratory_specialist" in agent_ids
        assert "radiology_specialist" not in agent_ids
        assert "cardiology_specialist" not in agent_ids
        assert "clinical_pharmacist" in agent_ids
