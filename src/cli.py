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


def cmd_demo_data(args: argparse.Namespace) -> None:
    script = PROJECT_ROOT / "scripts" / "generate_demo_data.py"
    subprocess.run([sys.executable, str(script)], check=True)


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
    sub.add_parser("demo-data", help="Generate demo data").set_defaults(func=cmd_demo_data)
    sub.add_parser("info", help="Print system info").set_defaults(func=cmd_info)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
