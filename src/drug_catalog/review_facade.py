from __future__ import annotations

import uuid
from typing import Literal

from src.config import get_config
from src.drug_catalog.catalog_service import DrugCatalogService, get_drug_catalog_service
from src.drug_catalog.models import HospitalDrug
from src.drug_catalog.terminology import CatalogAwareKnowledgeBase
from src.review_engine import ReviewEngine
from src.schemas import (
    CandidateDrug,
    CpoeMedicationReviewRequest,
    CpoeMedicationReviewResponse,
    CpoeMedicationOrder,
    CpoePatientSnapshot,
    CpoeReviewAlert,
    DrugItem,
    PatientContext,
    RuleEvidence,
)

AlertLevel = Literal["info", "warning", "hard_stop"]


class CpoeReviewFacade:
    """Unified CPOE medication review: formulary + terminology + rule engine."""

    def __init__(
        self,
        catalog: DrugCatalogService | None = None,
        review_engine: ReviewEngine | None = None,
    ) -> None:
        self.catalog = catalog or get_drug_catalog_service()
        self.kb = CatalogAwareKnowledgeBase(catalog=self.catalog)
        self.review_engine = review_engine or ReviewEngine(kb=self.kb)
        cfg = get_config()
        self.knowledge_version = cfg.get("clinical_knowledge", {}).get("version", "minimal_rules_v1")
        self.rule_strict = cfg.get("agents", {}).get("rule_strict", True)

    def _resolve_order(self, order: CpoeMedicationOrder) -> tuple[HospitalDrug | None, CandidateDrug]:
        record: HospitalDrug | None = None
        if order.hospital_drug_id:
            record = self.catalog.get_by_id(order.hospital_drug_id)
        if record is None and order.display_name:
            record = self.catalog.resolve_by_name(order.display_name)

        display = order.display_name or (record.display_name if record else "")
        ingredient = order.ingredient or (record.generic_name_en or record.generic_name_cn if record else "")
        canonical = self.kb.resolve_drug(display or ingredient, order.hospital_drug_id)

        candidate = CandidateDrug(
            name=display or order.hospital_drug_id,
            ingredient=ingredient or canonical,
            dose=order.dose,
            route=order.route,
            frequency=order.frequency,
            hospital_drug_id=order.hospital_drug_id or (record.hospital_drug_id if record else ""),
            source="cpoe_order",
        )
        return record, candidate

    def _build_patient_context(self, patient: CpoePatientSnapshot, existing: list[DrugItem]) -> PatientContext:
        return PatientContext(
            subject_id=int(patient.patient_id) if patient.patient_id.isdigit() else None,
            gender=patient.gender,
            age=patient.age,
            weight_kg=patient.weight_kg,
            egfr=patient.egfr,
            allergies=list(patient.allergies),
            current_medications=existing,
            pregnancy_status=patient.pregnancy_status,
            lactation_status=patient.lactation_status,
        )

    def _catalog_alerts(
        self,
        order: CpoeMedicationOrder,
        record: HospitalDrug | None,
    ) -> list[CpoeReviewAlert]:
        alerts: list[CpoeReviewAlert] = []
        if record is None:
            alerts.append(
                CpoeReviewAlert(
                    alert_id=f"ALT-{uuid.uuid4().hex[:10]}",
                    order_id=order.order_id,
                    rule_id="UNRESOLVED_DRUG",
                    alert_level="warning",
                    category="terminology",
                    summary=f"未能解析药品：{order.display_name or order.hospital_drug_id}",
                    recommendation="请核对院内药品码或联系药学部维护院目录映射。",
                    overridable=True,
                )
            )
            return alerts

        if not record.in_formulary:
            alerts.append(
                CpoeReviewAlert(
                    alert_id=f"ALT-{uuid.uuid4().hex[:10]}",
                    order_id=order.order_id,
                    rule_id="NOT_IN_FORMULARY",
                    alert_level="warning",
                    category="formulary",
                    summary=f"{record.display_name} 不在院基本目录内。",
                    recommendation="需特殊审批或更换为目录内品种。",
                    hospital_drug_id=record.hospital_drug_id,
                    display_name=record.display_name,
                    overridable=True,
                )
            )

        if not record.in_stock:
            alt_ids = [a.hospital_drug_id for a in self.catalog.list_alternatives(record.hospital_drug_id)]
            alt_display = [a.display_name for a in self.catalog.list_alternatives(record.hospital_drug_id)]
            alerts.append(
                CpoeReviewAlert(
                    alert_id=f"ALT-{uuid.uuid4().hex[:10]}",
                    order_id=order.order_id,
                    rule_id="OUT_OF_STOCK",
                    alert_level="warning",
                    category="inventory",
                    summary=f"{record.display_name} 当前缺货。",
                    recommendation="请更换为可调配品种或联系中心药房。",
                    hospital_drug_id=record.hospital_drug_id,
                    display_name=record.display_name,
                    alternatives=alt_display,
                    alternative_drug_ids=alt_ids,
                    overridable=True,
                )
            )

        if record.high_alert:
            alerts.append(
                CpoeReviewAlert(
                    alert_id=f"ALT-{uuid.uuid4().hex[:10]}",
                    order_id=order.order_id,
                    rule_id="HIGH_ALERT_DRUG",
                    alert_level="info",
                    category="high_alert",
                    summary=f"{record.display_name} 为高警示药品，需双人核对。",
                    recommendation="按高警示药品管理规范复核剂量与途径。",
                    hospital_drug_id=record.hospital_drug_id,
                    display_name=record.display_name,
                    overridable=True,
                )
            )
        return alerts

    def _evidence_to_alert(self, evidence: RuleEvidence, order_id: str) -> CpoeReviewAlert:
        if evidence.risk_level == "high":
            alert_level: AlertLevel = "hard_stop" if self.rule_strict else "warning"
            overridable = not self.rule_strict
        elif evidence.risk_level == "medium":
            alert_level = "warning"
            overridable = True
        else:
            alert_level = "info"
            overridable = True

        return CpoeReviewAlert(
            alert_id=f"ALT-{uuid.uuid4().hex[:10]}",
            order_id=order_id,
            rule_id=evidence.rule_id,
            alert_level=alert_level,
            category=evidence.category,
            evidence_grade="A" if evidence.risk_level == "high" else "B",
            summary=evidence.summary,
            recommendation=evidence.recommendation,
            alternatives=evidence.alternatives,
            implicated_drugs=evidence.implicated_drugs,
            overridable=overridable,
        )

    def _pick_primary_order_id(self, orders: list[CpoeMedicationOrder]) -> str:
        for order in orders:
            if order.status in {"", "new", "active"}:
                return order.order_id
        return orders[0].order_id if orders else ""

    def review(self, request: CpoeMedicationReviewRequest) -> CpoeMedicationReviewResponse:
        existing_meds: list[DrugItem] = []
        for med in request.existing_medications:
            record = None
            if med.hospital_drug_id:
                record = self.catalog.get_by_id(med.hospital_drug_id)
            if record is None and med.name:
                record = self.catalog.resolve_by_name(med.name)
            existing_meds.append(
                DrugItem(
                    name=med.name or (record.display_name if record else ""),
                    ingredient=record.generic_name_en if record else med.ingredient,
                    dose=med.dose,
                    route=med.route,
                    frequency=med.frequency,
                    hospital_drug_id=med.hospital_drug_id or (record.hospital_drug_id if record else ""),
                )
            )

        patient_context = self._build_patient_context(request.patient, existing_meds)

        candidate_drugs: list[CandidateDrug] = []
        order_records: dict[str, HospitalDrug | None] = {}
        catalog_alerts: list[CpoeReviewAlert] = []
        unresolved: list[str] = []

        for order in request.orders:
            record, candidate = self._resolve_order(order)
            order_records[order.order_id] = record
            candidate_drugs.append(candidate)
            catalog_alerts.extend(self._catalog_alerts(order, record))
            if record is None:
                unresolved.append(order.hospital_drug_id or order.display_name)

        review_output = self.review_engine.review(patient_context, candidate_drugs)

        clinical_alerts: list[CpoeReviewAlert] = []
        primary_order_id = self._pick_primary_order_id(request.orders)
        for evidence in review_output.evidence:
            order_id = primary_order_id
            for order in request.orders:
                if any(
                    name in (order.display_name, order.hospital_drug_id)
                    for name in evidence.implicated_drugs
                ):
                    order_id = order.order_id
                    break
            clinical_alerts.append(self._evidence_to_alert(evidence, order_id))

        all_alerts = catalog_alerts + clinical_alerts
        has_hard_stop = any(a.alert_level == "hard_stop" for a in all_alerts)
        has_warning = any(a.alert_level == "warning" for a in all_alerts)

        if has_hard_stop:
            overall = "blocked"
        elif has_warning or review_output.need_clarification:
            overall = "warning"
        else:
            overall = "passed"

        catalog_stats = self.catalog.stats()
        sync_version = ""
        if catalog_stats.get("last_sync"):
            sync_version = catalog_stats["last_sync"].get("sync_version", "")

        return CpoeMedicationReviewResponse(
            encounter_id=request.encounter_id,
            overall_status=overall,
            alerts=all_alerts,
            unresolved_drugs=unresolved,
            requires_pharmacist_review=has_hard_stop or review_output.risk_level in {"high", "medium"},
            review_output=review_output,
            knowledge_version=f"{self.knowledge_version}+{sync_version or 'no_formulary_sync'}",
            formulary_drug_count=catalog_stats.get("total_drugs", 0),
        )
