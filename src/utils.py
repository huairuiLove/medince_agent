from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any, Iterable, Iterator, Optional

from pydantic import BaseModel


def ensure_dir(path: str | Path) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def save_json(obj: Any, path: str | Path) -> None:
    target = Path(path)
    ensure_dir(target.parent)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2)


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_jsonl(records: Iterable[dict[str, Any]], path: str | Path) -> None:
    target = Path(path)
    ensure_dir(target.parent)
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


_UNKNOWN_LIST_VALUES = frozenset(
    {"unknown", "none", "n/a", "na", "无", "不详", "未知", "nkda", "无过敏", "无已知", "not known"}
)


def _format_llm_list_item(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        drug = item.get("drug") or item.get("name") or item.get("alternative")
        reason = item.get("reason") or item.get("rationale") or item.get("summary") or item.get("text")
        if drug and reason:
            return f"{drug}: {reason}"
        if drug:
            return str(drug).strip()
        for key in ("message", "summary", "text", "recommendation"):
            if item.get(key):
                return str(item[key]).strip()
        return json.dumps(item, ensure_ascii=False)
    return str(item).strip()


def _repair_char_split_list(items: list[str]) -> list[str]:
    """Merge lists produced by iterating a string char-by-char (e.g. list('青霉素'))."""
    stripped = [part.strip() for part in items if part and part.strip()]
    if len(stripped) >= 2 and all(len(part) == 1 for part in stripped):
        return ["".join(stripped)]
    return stripped


def coerce_llm_str_list(value: object) -> list[str]:
    """Normalize LLM JSON list fields that may arrive as strings or dict items."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in _UNKNOWN_LIST_VALUES:
            return []
        if re.search(r"[,，;；\n]", text):
            parts = re.split(r"[,，;；\n]+", text)
            return _repair_char_split_list([part.strip() for part in parts if part.strip()])
        return [text]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            formatted = _format_llm_list_item(item)
            if formatted:
                result.append(formatted)
        return _repair_char_split_list(result)
    formatted = _format_llm_list_item(value)
    return _repair_char_split_list([formatted]) if formatted else []


def extract_json_payload(text: str) -> Optional[Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    for candidate in (cleaned,):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_case_id(prefix: str = "case") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


CONFIDENCE_FROM_RISK = {
    "none": 0.95,
    "low": 0.85,
    "medium": 0.65,
    "high": 0.9,
    "unknown": 0.4,
}


def parse_confidence(value: Any, default: float = 0.5) -> float:
    """Parse LLM confidence — accepts 0-1 numbers or risk-level strings like 'high'."""
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, str):
        text = value.strip().lower()
        if text in CONFIDENCE_FROM_RISK:
            return CONFIDENCE_FROM_RISK[text]
        try:
            return max(0.0, min(1.0, float(text)))
        except ValueError:
            return default
    return default


def normalize_text(text: str) -> str:
    cleaned = str(text or "").strip().lower()
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    return value
