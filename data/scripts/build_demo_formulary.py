#!/usr/bin/env python3
"""Build MedSafe demo hospital formulary CSV (target 1000+ rows).

Sources:
  1. Curated Chinese hospital drugs (demo_formulary_data.py) — DDI demo, 中文名
  2. ATC-expanded templates (drug_template_catalog.py) — bulk from RxNorm-aligned seeds

Run: python scripts/build_demo_formulary.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from demo_formulary_data import DEMO_FORMULARY_DRUGS
from drug_template_catalog import iter_generated_templates

PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT = PROJECT_ROOT / "datasets/hospital/formulary_demo.csv"
TARGET_MIN_ROWS = 1050

HEADERS = [
    "hospital_drug_id",
    "generic_name_cn",
    "generic_name_en",
    "trade_name_cn",
    "strength",
    "dosage_form",
    "route",
    "atc_code",
    "rxnorm_rxcui",
    "insurance_code",
    "manufacturer",
    "in_formulary",
    "in_stock",
    "high_alert",
    "antibiotic_level",
    "narcotic_class",
    "restricted_dept",
    "alternatives",
]

MANUFACTURERS = [
    "华北制药", "扬子江药业", "恒瑞医药", "石药集团", "中国生物",
    "拜耳", "辉瑞", "诺华", "赛诺菲", "AstraZeneca", "罗氏", "齐鲁制药",
    "复星医药", "科伦药业", "华润双鹤", "正大天晴", "豪森药业", "人福医药",
]


def _norm_key(cn: str, en: str, spec: str, form: str) -> tuple[str, str, str, str]:
    return (cn.strip(), en.strip().lower(), spec.strip().lower(), form.strip())


def _atc_code(raw: str, fallback_prefix: str = "") -> str:
    if raw and len(raw) >= 7:
        return raw[:7]
    prefix = (raw or fallback_prefix or "Z")[:3]
    return f"{prefix}XX01".ljust(7, "0")[:7]


def _drug_to_row(
    drug: dict,
    idx: int,
    *,
    prefer_cn: bool = True,
) -> dict[str, str]:
    en = drug.get("en", drug.get("generic_name_en", "")).lower().strip()
    cn = drug.get("cn", drug.get("generic_name_cn", en))
    if not prefer_cn and not drug.get("cn"):
        cn = en
    trade = drug.get("trade", drug.get("trade_name_cn", cn))
    form = drug.get("form", drug.get("dosage_form", "片剂"))
    route = drug.get("route", "PO")
    spec = drug.get("spec", drug.get("strength", ""))
    atc = _atc_code(drug.get("atc", ""))

    return {
        "hospital_drug_id": f"H-DEMO-{idx:05d}",
        "generic_name_cn": cn,
        "generic_name_en": en,
        "trade_name_cn": trade,
        "strength": spec,
        "dosage_form": form,
        "route": route,
        "atc_code": atc,
        "rxnorm_rxcui": str(drug.get("rxcui", drug.get("rxnorm_rxcui", ""))),
        "insurance_code": f"8690{idx:09d}",
        "manufacturer": MANUFACTURERS[idx % len(MANUFACTURERS)],
        "in_formulary": "0" if drug.get("formulary") == 0 else "1",
        "in_stock": "0" if drug.get("stock") == 0 else "1",
        "high_alert": "1" if drug.get("high") else "0",
        "antibiotic_level": str(drug.get("abx", 0)),
        "narcotic_class": str(drug.get("narcotic", 0)),
        "restricted_dept": drug.get("dept", ""),
        "alternatives": "",
    }


def build_merged_drugs() -> list[tuple[dict, bool]]:
    """Return (drug_dict, is_curated) list, curated first."""
    merged: list[tuple[dict, bool]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for drug in DEMO_FORMULARY_DRUGS:
        key = _norm_key(drug["cn"], drug["en"], drug["spec"], drug["form"])
        if key in seen:
            continue
        seen.add(key)
        merged.append((drug, True))

    generated = iter_generated_templates()
    for drug in generated:
        key = _norm_key(drug["cn"], drug["en"], drug["spec"], drug["form"])
        if key in seen:
            continue
        seen.add(key)
        merged.append((drug, False))

    # If still below target, add extra spec variants for curated EN names
    if len(merged) < TARGET_MIN_ROWS:
        extra_specs = ["2.5mg", "5mg", "10mg", "20mg", "40mg", "80mg", "0.1g", "0.25g", "0.5g", "1g"]
        extra_forms = ["片剂", "胶囊", "注射液"]
        for drug, _ in list(merged):
            if len(merged) >= TARGET_MIN_ROWS:
                break
            for form in extra_forms:
                for spec in extra_specs:
                    if len(merged) >= TARGET_MIN_ROWS:
                        break
                    key = _norm_key(drug["cn"], drug["en"], spec, form)
                    if key in seen:
                        continue
                    seen.add(key)
                    variant = {**drug, "spec": spec, "form": form, "route": "IV" if form == "注射液" else "PO"}
                    merged.append((variant, False))

    return merged


def main() -> int:
    merged = build_merged_drugs()
    en_to_id: dict[str, str] = {}
    rows: list[dict[str, str]] = []

    for idx, (drug, is_curated) in enumerate(merged, start=1):
        row = _drug_to_row(drug, idx, prefer_cn=is_curated or bool(drug.get("cn")))
        rows.append(row)
        if drug["en"] not in en_to_id:
            en_to_id[drug["en"]] = row["hospital_drug_id"]

    for row, (drug, _) in zip(rows, merged):
        alt_en = drug.get("alt", "")
        if alt_en and alt_en in en_to_id:
            row["alternatives"] = en_to_id[alt_en]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    cn_count = sum(1 for r in rows if any("\u4e00" <= c <= "\u9fff" for c in r["generic_name_cn"]))
    print(f"Wrote {len(rows)} demo formulary rows -> {OUTPUT}")
    print(f"  Target (>={TARGET_MIN_ROWS}): {'OK' if len(rows) >= TARGET_MIN_ROWS else 'BELOW'}")
    print(f"  Chinese generic names: {cn_count}")
    print(f"  Unique EN ingredients: {len(en_to_id)}")
    print(f"  In-stock: {sum(1 for r in rows if r['in_stock'] == '1')}")
    print(f"  High-alert: {sum(1 for r in rows if r['high_alert'] == '1')}")
    print(f"  Antibiotics (level>0): {sum(1 for r in rows if int(r['antibiotic_level']) > 0)}")
    print("Import: python scripts/sync_formulary.py --csv data/hospital/formulary_demo.csv")
    return 0 if len(rows) >= TARGET_MIN_ROWS else 1


if __name__ == "__main__":
    raise SystemExit(main())
