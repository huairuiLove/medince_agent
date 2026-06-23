from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from src.department.priority import DepartmentRulePrioritizer
from src.knowledge_base import SafetyKnowledgeBase
from src.schemas import CandidateDrug, PatientContext, ReviewOutput, RuleEvidence
from src.utils import dedupe_preserve_order, normalize_text

from src.safety_models.ddi_classifier import get_ddi_classifier, is_ddi_bert_enabled


RISK_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "unknown": 4}


class ReviewEngine:
    def __init__(self, kb: SafetyKnowledgeBase | None = None) -> None:
        self.kb = kb or SafetyKnowledgeBase()

    def _to_candidate_drugs(self, patient_context: PatientContext, candidate_drugs: list[CandidateDrug]) -> list[CandidateDrug]:
        if candidate_drugs:
            return candidate_drugs
        return [
            CandidateDrug(
                name=drug.name,
                ingredient=drug.ingredient,
                dose=drug.dose,
                route=drug.route,
                frequency=drug.frequency,
                source="current_medication_audit",
            )
            for drug in patient_context.current_medications
        ]

    def _pregnancy_relevant(self, patient_context: PatientContext) -> bool:
        if patient_context.pregnancy_status not in {"unknown", "", None}:
            return True
        if str(patient_context.gender).upper() in {"F", "FEMALE"}:
            if patient_context.age is None:
                return True
            return 12 <= patient_context.age <= 55
        return False

    def _max_risk_level(self, levels: Iterable[str], clarification_targets: list[str]) -> str:
        risk = "none"
        for level in levels:
            if RISK_ORDER.get(level, 0) > RISK_ORDER.get(risk, 0):
                risk = level
        if risk == "none" and clarification_targets:
            return "unknown"
        return risk

    def _build_drug_registry(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        current_registry = []
        for med in patient_context.current_medications:
            current_registry.append(
                {
                    "name": med.name,
                    "canonical": self.kb.resolve_drug(
                        med.ingredient or med.name,
                        hospital_drug_id=med.hospital_drug_id or None,
                    ),
                    "source": "current",
                }
            )

        candidate_registry = []
        for med in candidate_drugs:
            candidate_registry.append(
                {
                    "name": med.name,
                    "canonical": self.kb.resolve_drug(
                        med.ingredient or med.name,
                        hospital_drug_id=med.hospital_drug_id or None,
                    ),
                    "source": "candidate",
                }
            )
        return current_registry, candidate_registry

    def _collect_interaction_evidence(
        self,
        current_registry: list[dict[str, str]],
        candidate_registry: list[dict[str, str]],
        department: str | None = None,
    ) -> list[RuleEvidence]:
        evidence: list[RuleEvidence] = []
        pair_cache: set[tuple[str, str, str]] = set()

        for candidate in candidate_registry:
            for other in current_registry + candidate_registry:
                if candidate is other:
                    continue
                pair = tuple(sorted([candidate["canonical"], other["canonical"]]))
                if not all(pair):
                    continue

                matched_rules = self.kb.interaction_rules_for_pair(
                    candidate["canonical"],
                    other["canonical"],
                    department=department,
                )
                for rule in matched_rules:
                    cache_key = (rule["rule_id"], pair[0], pair[1])
                    if cache_key not in pair_cache:
                        pair_cache.add(cache_key)
                        evidence.append(
                            RuleEvidence(
                                rule_id=rule["rule_id"],
                                category="drug_interaction",
                                risk_level=rule["risk_level"],
                                summary=rule["summary"],
                                mechanism=rule.get("mechanism", ""),
                                implicated_drugs=[candidate["name"], other["name"]],
                                recommendation=rule.get("recommendation", ""),
                                alternatives=rule.get("alternatives", []),
                                clarification_fields=rule.get("clarification_fields", []),
                                source=rule.get("source", "rule_base"),
                            )
                        )
        return evidence

    def _collect_model_ddi_evidence(
        self,
        current_registry: list[dict[str, str]],
        candidate_registry: list[dict[str, str]],
        existing_evidence: list[RuleEvidence],
    ) -> list[RuleEvidence]:
        if not is_ddi_bert_enabled():
            return []
        classifier = get_ddi_classifier().require_ready()

        covered_canonical: set[tuple[str, str]] = set()
        for item in existing_evidence:
            if item.category != "drug_interaction" or item.source == "ddi_bert_model":
                continue
            if len(item.implicated_drugs) >= 2:
                pair = tuple(sorted([
                    self.kb.resolve_drug(item.implicated_drugs[0]),
                    self.kb.resolve_drug(item.implicated_drugs[1]),
                ]))
                if all(pair):
                    covered_canonical.add(pair)

        evidence: list[RuleEvidence] = []
        seen: set[tuple[str, str]] = set()
        for candidate in candidate_registry:
            for other in current_registry + candidate_registry:
                if candidate is other:
                    continue
                pair = tuple(sorted([candidate["canonical"], other["canonical"]]))
                if not all(pair) or pair in seen or pair in covered_canonical:
                    continue
                seen.add(pair)
                if candidate["source"] != "candidate" and other["source"] != "candidate":
                    continue

                result = classifier.predict_pair(pair[0], pair[1])
                if not result or result["risk_level"] == "none":
                    continue

                evidence.append(
                    RuleEvidence(
                        rule_id=f"ddi_model_{pair[0]}_{pair[1]}",
                        category="drug_interaction",
                        risk_level=result["risk_level"],
                        summary=(
                            f"DDI 模型预测 {candidate['name']} 与 {other['name']} 存在相互作用"
                            f"（概率 {result['positive_prob']:.0%}）。"
                        ),
                        mechanism="Bio_ClinicalBERT SMILES 药对分类",
                        implicated_drugs=[candidate["name"], other["name"]],
                        recommendation="建议人工复核并查阅说明书。",
                        alternatives=["优先查阅药品说明书或药学咨询。"],
                        clarification_fields=["current_medications"],
                        source="ddi_bert_model",
                    )
                )
        return evidence

    def _collect_duplicate_evidence(
        self,
        current_registry: list[dict[str, str]],
        candidate_registry: list[dict[str, str]],
    ) -> list[RuleEvidence]:
        combined = current_registry + candidate_registry
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for item in combined:
            if item["canonical"]:
                grouped[item["canonical"]].append(item)

        evidence: list[RuleEvidence] = []
        for rule in self.kb.get_duplicate_rules():
            ingredient = self.kb.resolve_drug(rule["ingredient"])
            matched = grouped.get(ingredient, [])
            if len(matched) < 2:
                continue
            if not any(item["source"] == "candidate" for item in matched):
                continue

            evidence.append(
                RuleEvidence(
                    rule_id=rule["rule_id"],
                    category="duplicate_ingredient",
                    risk_level=rule["risk_level"],
                    summary=rule["summary"],
                    mechanism=rule.get("mechanism", ""),
                    implicated_drugs=[item["name"] for item in matched],
                    recommendation=rule.get("recommendation", ""),
                    alternatives=rule.get("alternatives", []),
                    clarification_fields=rule.get("clarification_fields", []),
                )
            )
        return evidence

    def _collect_population_evidence(
        self,
        patient_context: PatientContext,
        candidate_registry: list[dict[str, str]],
    ) -> list[RuleEvidence]:
        evidence: list[RuleEvidence] = []
        age = patient_context.age
        pregnancy_status = normalize_text(patient_context.pregnancy_status)
        egfr = patient_context.egfr
        lactation_status = normalize_text(patient_context.lactation_status)
        hepatic_context = " ".join(normalize_text(diag.name) for diag in patient_context.diagnoses)

        for rule in self.kb.get_population_rules():
            triggers = {self.kb.resolve_drug(drug) for drug in rule.get("trigger_drugs", [])}
            matched = [item for item in candidate_registry if item["canonical"] in triggers]
            if not matched:
                continue

            field_name = rule["population_field"]
            should_trigger = False
            if field_name == "pregnancy_status":
                should_trigger = pregnancy_status in {normalize_text(value) for value in rule.get("match_values", [])}
            elif field_name in ("lactation", "lactation_status"):
                should_trigger = lactation_status in {normalize_text(value) for value in rule.get("match_values", [])}
            elif field_name == "egfr":
                egfr_max = rule.get("egfr_max")
                if egfr is not None and egfr_max is not None and egfr < egfr_max:
                    should_trigger = True
            elif field_name == "hepatic":
                match_values = [normalize_text(value) for value in rule.get("match_values", [])]
                should_trigger = any(term and term in hepatic_context for term in match_values)
            elif field_name == "age":
                age_min = rule.get("age_min")
                age_max = rule.get("age_max")
                age_compare = rule.get("age_compare", "lt")
                if age is not None:
                    if age_compare == "gte" and age_min is not None and age >= age_min:
                        should_trigger = True
                    elif age_compare == "lte" and age_max is not None and age <= age_max:
                        should_trigger = True
                    else:
                        if age_min is not None and age < age_min:
                            should_trigger = True
                        if age_max is not None and age > age_max:
                            should_trigger = True

            if should_trigger:
                evidence.append(
                    RuleEvidence(
                        rule_id=rule["rule_id"],
                        category="special_population",
                        risk_level=rule["risk_level"],
                        summary=rule["summary"],
                        mechanism=rule.get("mechanism", ""),
                        implicated_drugs=[item["name"] for item in matched],
                        recommendation=rule.get("recommendation", ""),
                        alternatives=rule.get("alternatives", []),
                        clarification_fields=rule.get("clarification_fields", []),
                    )
                )
        return evidence

    def _collect_allergy_evidence(
        self,
        patient_context: PatientContext,
        candidate_registry: list[dict[str, str]],
    ) -> list[RuleEvidence]:
        allergy_text = " ".join(normalize_text(item) for item in patient_context.allergies)
        evidence: list[RuleEvidence] = []
        for rule in self.kb.get_allergy_rules():
            triggers = {self.kb.resolve_drug(drug) for drug in rule.get("trigger_drugs", [])}
            matched = [item for item in candidate_registry if item["canonical"] in triggers]
            if not matched:
                continue

            allergy_terms = [normalize_text(term) for term in rule.get("allergy_terms", [])]
            if allergy_text and any(term and term in allergy_text for term in allergy_terms):
                evidence.append(
                    RuleEvidence(
                        rule_id=rule["rule_id"],
                        category="allergy_contraindication",
                        risk_level=rule["risk_level"],
                        summary=rule["summary"],
                        mechanism=rule.get("mechanism", ""),
                        implicated_drugs=[item["name"] for item in matched],
                        recommendation=rule.get("recommendation", ""),
                        alternatives=rule.get("alternatives", []),
                        clarification_fields=rule.get("clarification_fields", []),
                    )
                )
        return evidence

    def _collect_scenario_evidence(
        self,
        patient_context: PatientContext,
        current_registry: list[dict[str, str]],
        candidate_registry: list[dict[str, str]],
    ) -> list[RuleEvidence]:
        if not candidate_registry:
            return []

        evidence: list[RuleEvidence] = []
        combined = current_registry + candidate_registry
        all_canonical = {item["canonical"] for item in combined if item["canonical"]}
        age = patient_context.age
        egfr = patient_context.egfr

        for rule in self.kb.get_scenario_rules():
            scenario_type = rule.get("scenario_type", "")
            should_trigger = False
            implicated: list[str] = []

            if scenario_type == "polypharmacy":
                min_total = rule.get("min_total_drugs", 5)
                if len(all_canonical) >= min_total:
                    should_trigger = True
                    implicated = [item["name"] for item in candidate_registry]

            elif scenario_type == "fall_risk_combo":
                drug_classes = rule.get("drug_classes", {})
                if drug_classes and all(
                    any(self.kb.resolve_drug(drug) in all_canonical for drug in drugs)
                    for drugs in drug_classes.values()
                ):
                    should_trigger = True
                    class_hits = {
                        self.kb.resolve_drug(drug)
                        for drugs in drug_classes.values()
                        for drug in drugs
                    }
                    implicated = [item["name"] for item in combined if item["canonical"] in class_hits]

            elif scenario_type == "renal_age_adjustment":
                age_min = rule.get("age_min", 75)
                egfr_max = rule.get("egfr_max", 45)
                if age is not None and age >= age_min and egfr is not None and egfr < egfr_max:
                    should_trigger = True
                    implicated = [item["name"] for item in candidate_registry]

            elif scenario_type == "anticholinergic_burden":
                drug_list = rule.get("drug_list", [])
                min_count = rule.get("min_drug_count", 3)
                anticholinergic = {self.kb.resolve_drug(drug) for drug in drug_list}
                matched = [item for item in combined if item["canonical"] in anticholinergic]
                unique_hits = {item["canonical"] for item in matched}
                if len(unique_hits) >= min_count and any(item["source"] == "candidate" for item in matched):
                    should_trigger = True
                    implicated = [item["name"] for item in matched]

            if should_trigger:
                evidence.append(
                    RuleEvidence(
                        rule_id=rule["rule_id"],
                        category="clinical_scenario",
                        risk_level=rule["risk_level"],
                        summary=rule["summary"],
                        mechanism=rule.get("mechanism", ""),
                        implicated_drugs=dedupe_preserve_order(implicated),
                        recommendation=rule.get("recommendation", ""),
                        alternatives=rule.get("alternatives", []),
                        clarification_fields=rule.get("clarification_fields", []),
                        source=rule.get("source", "rule_base"),
                    )
                )
        return evidence

    def _infer_clarification_targets(
        self,
        patient_context: PatientContext,
        candidate_registry: list[dict[str, str]],
    ) -> list[str]:
        targets = list(patient_context.missing_fields)

        if candidate_registry and not patient_context.allergies and "allergies" not in targets:
            if any(
                item["canonical"] in {self.kb.resolve_drug(drug) for drug in rule.get("trigger_drugs", [])}
                for item in candidate_registry
                for rule in self.kb.get_allergy_rules()
            ):
                targets.append("allergies")

        if candidate_registry and not patient_context.current_medications and "current_medications" not in targets:
            if any(
                item["canonical"] in {self.kb.resolve_drug(drug) for drug in rule.get("drugs", [])}
                for item in candidate_registry
                for rule in self.kb.get_interaction_rules()
            ):
                targets.append("current_medications")

        if self._pregnancy_relevant(patient_context):
            pregnancy_unknown = normalize_text(patient_context.pregnancy_status) in {"", "unknown"}
            if pregnancy_unknown and "pregnancy_status" not in targets:
                for rule in self.kb.get_population_rules():
                    if rule.get("population_field") != "pregnancy_status":
                        continue
                    triggers = {self.kb.resolve_drug(drug) for drug in rule.get("trigger_drugs", [])}
                    if any(item["canonical"] in triggers for item in candidate_registry):
                        targets.append("pregnancy_status")
                        break

        if patient_context.age is None and "age" not in targets:
            for rule in self.kb.get_population_rules():
                if rule.get("population_field") != "age":
                    continue
                triggers = {self.kb.resolve_drug(drug) for drug in rule.get("trigger_drugs", [])}
                if any(item["canonical"] in triggers for item in candidate_registry):
                    targets.append("age")
                    break

        return dedupe_preserve_order(targets)

    def retrieve_evidence(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        department: str | None = None,
    ) -> list[RuleEvidence]:
        candidate_drugs = self._to_candidate_drugs(patient_context, candidate_drugs)
        current_registry, candidate_registry = self._build_drug_registry(patient_context, candidate_drugs)
        dept = department or patient_context.department or None

        evidence = []
        evidence.extend(self._collect_interaction_evidence(current_registry, candidate_registry, department=dept))
        evidence.extend(self._collect_model_ddi_evidence(current_registry, candidate_registry, evidence))
        evidence.extend(self._collect_duplicate_evidence(current_registry, candidate_registry))
        evidence.extend(self._collect_population_evidence(patient_context, candidate_registry))
        evidence.extend(self._collect_allergy_evidence(patient_context, candidate_registry))
        evidence.extend(self._collect_scenario_evidence(patient_context, current_registry, candidate_registry))
        return evidence

    def _apply_department_priority(
        self,
        evidence: list[RuleEvidence],
        department: str | None,
        priority_categories: list[str] | None = None,
    ) -> list[RuleEvidence]:
        if not evidence:
            return evidence
        prioritizer = DepartmentRulePrioritizer(
            department=department,
            priority_categories=priority_categories,
        )
        rule_lookup = self.kb.rule_lookup() if hasattr(self.kb, "rule_lookup") else {}
        return prioritizer.apply(evidence, rule_lookup)

    def review(
        self,
        patient_context: PatientContext,
        candidate_drugs: list[CandidateDrug],
        retrieved_evidence: list[RuleEvidence] | None = None,
        department: str | None = None,
        priority_categories: list[str] | None = None,
    ) -> ReviewOutput:
        candidate_drugs = self._to_candidate_drugs(patient_context, candidate_drugs)
        current_registry, candidate_registry = self._build_drug_registry(patient_context, candidate_drugs)
        dept = department or patient_context.department or None
        computed_evidence = self.retrieve_evidence(patient_context, candidate_drugs, department=dept)

        merged_evidence: list[RuleEvidence] = []
        seen_keys: set[tuple[str, str]] = set()
        for item in computed_evidence + list(retrieved_evidence or []):
            evidence_item = item if isinstance(item, RuleEvidence) else RuleEvidence.model_validate(item)
            key = (evidence_item.rule_id, "|".join(sorted(evidence_item.implicated_drugs)))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged_evidence.append(evidence_item)

        merged_evidence = self._apply_department_priority(
            merged_evidence,
            dept,
            priority_categories=priority_categories,
        )

        clarification_targets = self._infer_clarification_targets(patient_context, candidate_registry)
        clarification_targets.extend(
            field
            for item in merged_evidence
            for field in item.clarification_fields
            if field
        )
        clarification_targets = dedupe_preserve_order(clarification_targets)

        risk_reasons = dedupe_preserve_order(item.summary for item in merged_evidence)
        alternatives = dedupe_preserve_order(
            alternative
            for item in merged_evidence
            for alternative in item.alternatives
        )
        risk_level = self._max_risk_level([item.risk_level for item in merged_evidence], clarification_targets)
        need_clarification = bool(clarification_targets)
        block_decision = risk_level == "high" or need_clarification

        if risk_level == "high":
            final_recommendation = "当前候选用药存在高风险，建议先阻断该方案，并优先采用更安全替代或人工复核。"
        elif need_clarification:
            final_recommendation = "当前信息不足，建议先补充关键字段后再继续用药审查。"
        elif risk_level == "medium":
            final_recommendation = "当前方案存在中等风险，建议结合证据调整方案并进行人工复核。"
        elif risk_level == "low":
            final_recommendation = "当前方案命中低风险提示，可继续人工确认后使用。"
        else:
            final_recommendation = "规则库未命中明显高风险项，可继续结合临床上下文审阅。"

        return ReviewOutput(
            risk_level=risk_level,
            block_decision=block_decision,
            risk_reasons=risk_reasons,
            alternative_suggestions=alternatives,
            need_clarification=need_clarification,
            clarification_targets=clarification_targets,
            evidence=merged_evidence,
            final_recommendation=final_recommendation,
        )
