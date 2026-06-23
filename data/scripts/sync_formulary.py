#!/usr/bin/env python3
"""Sync hospital formulary CSV into MedSafe drug catalog database."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config, resolve_path
from src.drug_catalog.catalog_service import get_drug_catalog_service
from src.drug_catalog.csv_import import FormularyCsvImporter


def main() -> int:
    load_config()
    parser = argparse.ArgumentParser(description="Import PIS formulary CSV into MedSafe drug catalog")
    parser.add_argument(
        "--csv",
        default="datasets/hospital/formulary_sample.csv",
        help="CSV path relative to project root (default: sample formulary)",
    )
    parser.add_argument("--version", default="", help="Sync version tag (default: UTC timestamp)")
    parser.add_argument("--encoding", default="utf-8-sig", help="CSV file encoding")
    args = parser.parse_args()

    csv_path = resolve_path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}")
        return 1

    service = get_drug_catalog_service(reload=True)
    importer = FormularyCsvImporter(service.db_path)
    result = importer.import_csv(csv_path, sync_version=args.version or None, encoding=args.encoding)

    stats = get_drug_catalog_service(reload=True).stats()
    print("Formulary sync complete:")
    print(f"  source:    {result['source_path']}")
    print(f"  version:   {result['sync_version']}")
    print(f"  upserted:  {result['rows_upserted']} / {result['rows_total']}")
    print(f"  db:        {stats['db_path']}")
    print(f"  total:     {stats['total_drugs']} drugs ({stats['in_formulary']} in formulary, {stats['in_stock']} in stock)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
