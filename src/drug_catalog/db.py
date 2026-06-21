from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hospital_drugs (
    hospital_drug_id TEXT PRIMARY KEY,
    generic_name_cn TEXT NOT NULL DEFAULT '',
    generic_name_en TEXT NOT NULL DEFAULT '',
    trade_name_cn TEXT NOT NULL DEFAULT '',
    strength TEXT NOT NULL DEFAULT '',
    dosage_form TEXT NOT NULL DEFAULT '',
    route TEXT NOT NULL DEFAULT '',
    atc_code TEXT NOT NULL DEFAULT '',
    rxnorm_rxcui TEXT NOT NULL DEFAULT '',
    insurance_code TEXT NOT NULL DEFAULT '',
    manufacturer TEXT NOT NULL DEFAULT '',
    in_formulary INTEGER NOT NULL DEFAULT 1,
    in_stock INTEGER NOT NULL DEFAULT 1,
    high_alert INTEGER NOT NULL DEFAULT 0,
    antibiotic_level TEXT NOT NULL DEFAULT '',
    narcotic_class TEXT NOT NULL DEFAULT '',
    restricted_dept TEXT NOT NULL DEFAULT '',
    alternatives_json TEXT NOT NULL DEFAULT '[]',
    canonical_key TEXT NOT NULL DEFAULT '',
    sync_version TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_hospital_drugs_canonical ON hospital_drugs(canonical_key);
CREATE INDEX IF NOT EXISTS idx_hospital_drugs_atc ON hospital_drugs(atc_code);
CREATE INDEX IF NOT EXISTS idx_hospital_drugs_rxnorm ON hospital_drugs(rxnorm_rxcui);

CREATE TABLE IF NOT EXISTS drug_aliases (
    alias_text TEXT NOT NULL,
    hospital_drug_id TEXT NOT NULL,
    alias_type TEXT NOT NULL DEFAULT 'auto',
    PRIMARY KEY (alias_text, hospital_drug_id),
    FOREIGN KEY (hospital_drug_id) REFERENCES hospital_drugs(hospital_drug_id)
);

CREATE INDEX IF NOT EXISTS idx_drug_aliases_hospital ON drug_aliases(hospital_drug_id);

CREATE TABLE IF NOT EXISTS formulary_sync_log (
    sync_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    sync_version TEXT NOT NULL,
    rows_total INTEGER NOT NULL DEFAULT 0,
    rows_upserted INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'running',
    error_message TEXT NOT NULL DEFAULT ''
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
