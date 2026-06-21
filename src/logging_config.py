"""Structured logging configuration for MedSafe.

Provides a consistent logging setup across all modules with support for
JSON-structured logs (production) and colored console output (development).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter for machine-parseable logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            payload["exception"] = str(record.exc_info[1])
        for key in ("request_id", "case_id", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False, default=str)


class ColoredConsoleFormatter(logging.Formatter):
    """Colored console formatter with module info."""

    COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[1;31m", # bold red
    }
    RESET = "\033[0m"
    GRAY = "\033[90m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        module = f"{record.name}:{record.lineno}"

        prefix = f"{self.GRAY}{timestamp}{self.RESET} {color}{record.levelname:<8}{self.RESET} {self.GRAY}[{module}]{self.RESET}"
        msg = record.getMessage()

        if record.exc_info and record.exc_info[1]:
            msg = f"{msg}\n{self.RESET}" + self.formatException(record.exc_info)

        return f"{prefix} {msg}"


def setup_logging(
    level: str = "INFO",
    log_format: str = "console",
    log_dir: str | Path | None = None,
    log_file: str = "medsafe.log",
    max_bytes: int = 10_485_760,
    backup_count: int = 5,
    force: bool = False,
) -> logging.Logger:
    """Configure the root logger for MedSafe.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        log_format: "structured" for JSON, "console" for colored output.
        log_dir: Directory for log files. None disables file logging.
        log_file: Log file name.
        max_bytes: Max bytes before rotation.
        backup_count: Number of backup files to keep.
        force: If True, re-configure even if already set up.

    Returns:
        The root "medsafe" logger.
    """
    logger = logging.getLogger("medsafe")
    if logger.handlers and not force:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.DEBUG)
    if log_format == "structured":
        console_handler.setFormatter(StructuredFormatter())
    else:
        console_handler.setFormatter(ColoredConsoleFormatter())
    logger.addHandler(console_handler)

    # File handler
    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path / log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(StructuredFormatter())
        logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    for noisy in ("uvicorn", "uvicorn.access", "uvicorn.error", "httpx", "httpcore"):
        logging.getLogger(noisy).handlers.clear()
        logging.getLogger(noisy).addHandler(logging.NullHandler())

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the medsafe namespace."""
    return logging.getLogger(f"medsafe.{name}")
