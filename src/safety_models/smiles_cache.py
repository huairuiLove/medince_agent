from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_config, resolve_path
from src.utils import normalize_text

def _default_cache_path() -> Path:
    cfg = get_config()
    rel = cfg.get("safety_models", {}).get("pubchem", {}).get("cache_path", "data/smiles_cache.db")
    return resolve_path(rel)


DEFAULT_CACHE_PATH = _default_cache_path()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS smiles_cache (
    query_key TEXT PRIMARY KEY,
    query_name TEXT NOT NULL,
    pubchem_query TEXT NOT NULL DEFAULT '',
    smiles TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'pubchem',
    fetched_at TEXT NOT NULL
);
"""


class SmilesCache:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(resolve_path(db_path or DEFAULT_CACHE_PATH))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def get(self, query_name: str) -> str | None:
        key = normalize_text(query_name)
        if not key:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT smiles FROM smiles_cache WHERE query_key = ?",
                (key,),
            ).fetchone()
        return row["smiles"] if row else None

    def put(
        self,
        query_name: str,
        smiles: str,
        *,
        pubchem_query: str = "",
        source: str = "pubchem",
    ) -> None:
        key = normalize_text(query_name)
        if not key or not smiles:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO smiles_cache (query_key, query_name, pubchem_query, smiles, source, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(query_key) DO UPDATE SET
                    smiles = excluded.smiles,
                    pubchem_query = excluded.pubchem_query,
                    source = excluded.source,
                    fetched_at = excluded.fetched_at
                """,
                (key, query_name, pubchem_query or query_name, smiles, source, now),
            )
            conn.commit()

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM smiles_cache").fetchone()
        return int(row["c"]) if row else 0

    def stats(self) -> dict[str, int | str]:
        return {"entries": self.count(), "db_path": str(self.db_path)}
