"""Unified CLI for MedSafe multi-agent system."""
from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _ensure_deps():
    try:
        from dotenv import load_dotenv
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            load_dotenv(env_file)
    except ImportError:
        pass


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn
    from src.config import load_config
    from src.logging_config import setup_logging

    cfg = load_config()
    log_cfg = cfg.get("logging", {})
    setup_logging(
        level=log_cfg.get("level", "INFO"),
        log_format=log_cfg.get("format", "console"),
        log_dir=log_cfg.get("log_dir"),
        log_file=log_cfg.get("log_file", "medsafe.log"),
    )
    server_cfg = cfg.get("server", {})
    uvicorn.run(
        "src.app:app",
        host=args.host or server_cfg.get("host", "0.0.0.0"),
        port=args.port or server_cfg.get("port", 8000),
        workers=args.workers or server_cfg.get("workers", 1),
        reload=args.reload,
    )


def cmd_test(args: argparse.Namespace) -> None:
    script = PROJECT_ROOT / "scripts" / "run_integration_tests.py"
    subprocess.run([sys.executable, str(script)], check=True)


def cmd_case_templates(args: argparse.Namespace) -> None:
    script = PROJECT_ROOT / "scripts" / "generate_demo_data.py"
    subprocess.run([sys.executable, str(script)], check=True)


def cmd_build_mimic(args: argparse.Namespace) -> None:
    from scripts.generate_demo_data import (
        generate_mimic_patient_contexts,
        is_full_mimic_dataset,
        resolve_mimic_raw_dir,
    )
    from src.config import load_config

    raw_dir = resolve_mimic_raw_dir()
    if raw_dir is None:
        print("MIMIC-III CSV not found under datasets/mimic-iii-clinical-database-1.4/")
        sys.exit(1)

    cfg = load_config().get("data", {}).get("mimic", {})
    max_samples = args.max_samples if args.max_samples is not None else int(cfg.get("max_samples", 0))
    skip_notes = args.skip_notes or bool(cfg.get("skip_notes", False))
    if not args.skip_notes and not skip_notes:
        skip_notes = not is_full_mimic_dataset(raw_dir)

    generate_mimic_patient_contexts(
        max_samples=max_samples,
        skip_notes=skip_notes,
        require_medications=args.require_medications if args.require_medications is not None else bool(cfg.get("require_medications", True)),
        include_labs=not args.no_labs and bool(cfg.get("include_labs", True)),
        include_icu=bool(cfg.get("include_icu", True)),
        include_imaging=bool(cfg.get("include_imaging", True)),
    )
    from src.mimic_store import get_mimic_store

    get_mimic_store().invalidate_cache()


def cmd_validate_mimic(args: argparse.Namespace) -> None:
    script = PROJECT_ROOT / "scripts" / "validate_mimic_data.py"
    cmd = [sys.executable, str(script)]
    if args.strict:
        cmd.append("--strict")
    subprocess.run(cmd, check=not args.no_fail)


def cmd_segment_worker(args: argparse.Namespace) -> None:
    import uvicorn
    from src.config import load_config
    from src.imaging.remote_config import get_remote_segment_config
    from src.logging_config import setup_logging

    cfg = load_config()
    log_cfg = cfg.get("logging", {})
    setup_logging(
        level=log_cfg.get("level", "INFO"),
        log_format=log_cfg.get("format", "console"),
        log_dir=log_cfg.get("log_dir"),
        log_file="segment_worker.log",
    )
    remote_cfg = get_remote_segment_config()
    host = args.host or remote_cfg["worker_host"]
    port = args.port or remote_cfg["worker_port"]
    uvicorn.run(
        "src.imaging.remote_worker:app",
        host=host,
        port=port,
        workers=1,
        reload=args.reload,
    )


def cmd_info(args: argparse.Namespace) -> None:
    from src.config import load_config
    from src.llm.client import get_llm_client, is_llm_configured

    cfg = load_config()
    provider = cfg.get("llm", {}).get("provider", "")
    if is_llm_configured():
        llm = get_llm_client()
        llm_line = f"{type(llm).__name__} (provider={provider})"
    else:
        llm_line = f"未配置 (provider={provider or 'unset'})"
    print("MedSafe v2.0.0 — Multi-Agent Drug Safety Review")
    print(f"Python: {platform.python_version()}")
    print(f"Platform: {platform.platform()}")
    print(f"Project: {PROJECT_ROOT}")
    print(f"LLM: {llm_line}")
    print(f"Rule strict: {cfg.get('agents', {}).get('rule_strict', True)}")


def main() -> None:
    _ensure_deps()
    parser = argparse.ArgumentParser(description="MedSafe CLI", prog="medsafe")
    sub = parser.add_subparsers(dest="command")

    serve_p = sub.add_parser("serve", help="Start API server")
    serve_p.add_argument("--host", type=str)
    serve_p.add_argument("--port", type=int)
    serve_p.add_argument("--workers", type=int)
    serve_p.add_argument("--reload", action="store_true")
    serve_p.set_defaults(func=cmd_serve)

    sub.add_parser("test", help="Run integration tests").set_defaults(func=cmd_test)
    sub.add_parser("case-templates", help="Generate case template fixtures").set_defaults(func=cmd_case_templates)
    build_p = sub.add_parser("build-mimic", help="Build MIMIC-III patient contexts from CSV tables")
    build_p.add_argument("--max-samples", type=int, default=None, help="Max admissions (0 = all; default from config.yaml)")
    build_p.add_argument("--skip-notes", action="store_true", help="Skip NOTEEVENTS (faster, no chief complaint)")
    build_p.add_argument("--require-medications", action="store_true", default=None, help="Only admissions with Rx")
    build_p.add_argument("--no-labs", action="store_true", help="Skip LABEVENTS during build")
    build_p.set_defaults(func=cmd_build_mimic)
    validate_p = sub.add_parser("validate-mimic", help="Check MIMIC-III raw + processed data")
    validate_p.add_argument("--strict", action="store_true", help="Require clinical notes in processed file")
    validate_p.add_argument("--no-fail", action="store_true", help="Always exit 0")
    validate_p.set_defaults(func=cmd_validate_mimic)
    worker_p = sub.add_parser("segment-worker", help="Start remote GPU segment worker")
    worker_p.add_argument("--host", type=str)
    worker_p.add_argument("--port", type=int)
    worker_p.add_argument("--reload", action="store_true")
    worker_p.set_defaults(func=cmd_segment_worker)
    legacy = sub.add_parser("demo-data", help="(deprecated) use case-templates")
    legacy.set_defaults(func=cmd_case_templates)
    sub.add_parser("info", help="Print system info").set_defaults(func=cmd_info)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
