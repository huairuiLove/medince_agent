"""Expand drug_kg_v2 with formulary ATC, metabolism, and clinical lab nodes."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from src.config import resolve_path
from src.utils import load_json, normalize_text

ATC_INDICATION_MAP: dict[str, str] = {
    "A10": "cond_diabetes_t2",
    "C01": "cond_atrial_fibrillation",
    "C03": "cond_hypertension",
    "C07": "cond_hypertension",
    "C08": "cond_hypertension",
    "C09": "cond_hypertension",
    "C10": "cond_hyperlipidemia",
    "B01": "cond_atrial_fibrillation",
}

METABOLIZED_BY: dict[str, list[str]] = {
    "simvastatin": ["enzyme_cyp3a4"],
    "atorvastatin": ["enzyme_cyp3a4"],
    "warfarin": ["enzyme_cyp2c9"],
    "clopidogrel": ["enzyme_cyp2c19"],
    "omeprazole": ["enzyme_cyp2c19"],
    "fluoxetine": ["enzyme_cyp2d6"],
    "metoprolol": ["enzyme_cyp2d6"],
    "codeine": ["enzyme_cyp2d6"],
    "cyclosporine": ["enzyme_cyp3a4"],
    "tacrolimus": ["enzyme_cyp3a4"],
    "digoxin": ["transporter_pgp"],
    "dabigatran": ["transporter_pgp"],
}

LAB_TESTS = [
    ("lab_egfr", "eGFR", "69405-9"),
    ("lab_inr", "INR", "6301-6"),
    ("lab_potassium", "血钾", "2823-3"),
    ("lab_glucose", "血糖", "2345-7"),
]

TRANSPORTERS = [
    ("transporter_pgp", "P-gp/ABCB1"),
    ("transporter_oatp1b1", "OATP1B1"),
]

EXTRA_ENZYMES = [
    ("enzyme_cyp1a2", "CYP1A2"),
    ("enzyme_cyp2b6", "CYP2B6"),
    ("enzyme_cyp2e1", "CYP2E1"),
    ("enzyme_ugt1a1", "UGT1A1"),
]


def _drug_node_id(canonical: str) -> str:
    slug = normalize_text(canonical).replace(" ", "_").replace("-", "_")
    return f"d_{slug}"


def _class_node_id(atc_code: str) -> str:
    code = atc_code.strip().upper()
    return f"cls_{code.replace('.', '_')}"


def _load_formulary_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def enrich_knowledge_graph(
    kg: dict[str, Any],
    merged_kb: dict[str, Any],
    *,
    formulary_csv: Path | None = None,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = list(kg.get("nodes", []))
    edges: list[dict[str, Any]] = list(kg.get("edges", []))
    node_ids = {node["id"] for node in nodes}
    edge_keys = {(edge["source"], edge["target"], edge["type"]) for edge in edges}

    name_to_id: dict[str, str] = {}
    for node in nodes:
        if node.get("type") == "Drug":
            name_to_id[normalize_text(node.get("name", ""))] = node["id"]
            name_to_id[normalize_text(node["id"].replace("d_", "").replace("_", " "))] = node["id"]

    for alias, canonical in merged_kb.get("drug_aliases", {}).items():
        canon = normalize_text(canonical)
        if canon in name_to_id:
            name_to_id[normalize_text(alias)] = name_to_id[canon]
        name_to_id[canon] = name_to_id.get(canon, _drug_node_id(canon))

    def ensure_node(node: dict[str, Any]) -> None:
        if node["id"] in node_ids:
            return
        nodes.append(node)
        node_ids.add(node["id"])

    def ensure_edge(source: str, target: str, edge_type: str, payload: dict[str, Any]) -> None:
        key = (source, target, edge_type)
        if key in edge_keys:
            return
        edges.append({"source": source, "target": target, "type": edge_type, **payload})
        edge_keys.add(key)

    for test_id, label, loinc in LAB_TESTS:
        ensure_node({"id": test_id, "type": "LabTest", "name": label, "loinc_code": loinc})

    for transporter_id, label in TRANSPORTERS:
        ensure_node({"id": transporter_id, "type": "Transporter", "name": label})

    for enzyme_id, label in EXTRA_ENZYMES:
        ensure_node({"id": enzyme_id, "type": "Enzyme", "name": label})

    csv_path = formulary_csv or resolve_path("data/hospital/formulary_demo.csv")
    if not csv_path.exists():
        raise FileNotFoundError(f"Formulary CSV required for KG enrichment: {csv_path}")

    for row in _load_formulary_rows(csv_path):
        generic = normalize_text(row.get("generic_name_en", ""))
        atc = (row.get("atc_code") or "").strip().upper()
        if not generic or not atc:
            continue
        drug_id = name_to_id.get(generic) or _drug_node_id(generic)
        if drug_id not in node_ids:
            ensure_node(
                {
                    "id": drug_id,
                    "type": "Drug",
                    "name": generic,
                    "brand_names": [],
                    "atc_code": atc,
                    "category": "",
                    "rx_type": "Rx",
                    "description": f"Formulary drug {generic}",
                }
            )
            name_to_id[generic] = drug_id

        class_id = _class_node_id(atc)
        ensure_node(
            {
                "id": class_id,
                "type": "DrugClass",
                "name": atc,
                "category": "ATC",
            }
        )
        ensure_edge(
            drug_id,
            class_id,
            "BELONGS_TO_CLASS",
            {"evidence_level": "A", "source": "formulary_atc"},
        )

        for prefix, condition_id in ATC_INDICATION_MAP.items():
            if atc.startswith(prefix):
                ensure_edge(
                    drug_id,
                    condition_id,
                    "INDICATED_FOR",
                    {
                        "severity": "mild",
                        "mechanism": f"ATC {atc} 对应适应症",
                        "effect": "标准适应症",
                        "recommendation": "按指南评估用药指征",
                        "evidence_level": "B",
                    },
                )

    for drug, enzyme_ids in METABOLIZED_BY.items():
        canon = normalize_text(drug)
        drug_id = name_to_id.get(canon) or _drug_node_id(canon)
        if drug_id not in node_ids:
            continue
        for enzyme_id in enzyme_ids:
            if enzyme_id not in node_ids:
                label = enzyme_id.replace("transporter_", "").replace("enzyme_", "").upper()
                node_type = "Transporter" if enzyme_id.startswith("transporter_") else "Enzyme"
                ensure_node({"id": enzyme_id, "type": node_type, "name": label})
            ensure_edge(
                drug_id,
                enzyme_id,
                "METABOLIZED_BY",
                {
                    "severity": "moderate",
                    "mechanism": "主要代谢/转运途径",
                    "effect": "影响药物暴露与相互作用",
                    "recommendation": "联用 CYP/转运体抑制剂或诱导剂时需评估",
                    "evidence_level": "B",
                },
            )

    base_food = load_json(resolve_path("data/knowledge/drug_kg.json"))
    for edge in base_food.get("edges", []):
        if edge.get("type") != "FOOD_INTERACTION":
            continue
        key = (edge["source"], edge["target"], edge["type"])
        if key not in edge_keys:
            edges.append(edge)
            edge_keys.add(key)

    meta = dict(kg.get("meta", {}))
    meta["node_count"] = len(nodes)
    meta["edge_count"] = len(edges)
    meta["enrichment_source"] = str(csv_path)
    return {"meta": meta, "nodes": nodes, "edges": edges}
