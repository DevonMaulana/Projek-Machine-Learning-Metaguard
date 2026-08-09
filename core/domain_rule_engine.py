"""Controlled execution of declarative domain rules without app integration.

This milestone deliberately adapts the stable v0.2 healthcare evaluators.  The
adapter resolves semantic concepts to actual columns and adds provenance, while
leaving the legacy application's caller and behavior untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

import pandas as pd

from core.concept_registry import ConceptRegistry, load_concept_registry, map_dataframe_columns
from core.cross_column_rules import _beds_rule, _internet_rule
from core.domain_models import DomainId, validate_domain_id
from core.rule_registry import KNOWN_EVALUATOR_IDS, RuleDefinition, RuleRegistry, load_rule_registry


RULE_STATE_EVALUATED = "evaluated"
RULE_STATE_SKIPPED_MISSING_CONCEPT = "skipped_missing_concept"
RULE_STATE_SKIPPED_AMBIGUOUS_CONCEPT = "skipped_ambiguous_concept"
RULE_STATE_NOT_APPLICABLE = "not_applicable"
RULE_STATE_ERROR = "error"


@dataclass(frozen=True)
class ResolvedConceptColumn:
    """One concept resolved to a specific source dataframe column."""

    concept_id: str
    source_column: str
    column_position: int

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe source-column provenance."""
        return {
            "concept_id": self.concept_id,
            "source_column": self.source_column,
            "column_position": self.column_position,
        }


@dataclass(frozen=True)
class RuleExecutionResult:
    """Outcome of one rule; skipped state is never represented as zero findings."""

    rule_id: str
    state: str
    findings: tuple[dict[str, Any], ...]
    resolved_columns: tuple[ResolvedConceptColumn, ...]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return compact JSON-safe outcome metadata and enriched findings."""
        return {
            "rule_id": self.rule_id,
            "state": self.state,
            "finding_count": len(self.findings),
            "findings": list(self.findings),
            "resolved_columns": [column.to_dict() for column in self.resolved_columns],
            "error": self.error,
        }


@dataclass(frozen=True)
class DomainRuleExecutionSummary:
    """Compact future-facing summary of a deterministic domain-rule run."""

    selected_domain: DomainId
    active_rule_packs: tuple[str, ...]
    rules_total: int
    rules_evaluated: int
    rules_skipped: int
    findings_count: int
    rule_results: tuple[RuleExecutionResult, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe data without retaining a dataframe reference."""
        return {
            "selected_domain": self.selected_domain.value,
            "active_rule_packs": list(self.active_rule_packs),
            "rules_total": self.rules_total,
            "rules_evaluated": self.rules_evaluated,
            "rules_skipped": self.rules_skipped,
            "findings_count": self.findings_count,
            "rule_results": [result.to_dict() for result in self.rule_results],
        }


def _resolve_concept_columns(
    dataframe: pd.DataFrame,
    selected_domain: DomainId,
    concept_registry: ConceptRegistry,
) -> tuple[dict[str, ResolvedConceptColumn], frozenset[str]]:
    resolutions = map_dataframe_columns(dataframe.columns, selected_domain, concept_registry)
    candidates: dict[str, list[ResolvedConceptColumn]] = {}
    ambiguous: set[str] = set()
    for position, resolution in enumerate(resolutions):
        if resolution.concept_id is None:
            continue
        candidates.setdefault(resolution.concept_id, []).append(
            ResolvedConceptColumn(
                concept_id=resolution.concept_id,
                source_column=str(dataframe.columns[position]),
                column_position=position,
            )
        )
        if resolution.is_duplicate_normalized_column:
            ambiguous.add(resolution.concept_id)
    resolved: dict[str, ResolvedConceptColumn] = {}
    for concept_id, columns in candidates.items():
        if len(columns) == 1 and concept_id not in ambiguous:
            resolved[concept_id] = columns[0]
        else:
            ambiguous.add(concept_id)
    return resolved, frozenset(ambiguous)


def _canonical_dataframe(
    dataframe: pd.DataFrame,
    resolved_columns: Mapping[str, ResolvedConceptColumn],
    required_concepts: tuple[str, ...],
    concept_registry: ConceptRegistry,
) -> pd.DataFrame:
    """Create an isolated two-column view for legacy parity without mutation."""
    return pd.DataFrame(
        {
            concept_registry.get(concept_id).canonical_name: dataframe.iloc[
                :, resolved_columns[concept_id].column_position
            ].copy()
            for concept_id in required_concepts
        },
        index=dataframe.index.copy(),
    )


def _enrich_findings(
    findings: list[dict[str, Any]],
    rule: RuleDefinition,
    resolved_columns: tuple[ResolvedConceptColumn, ...],
) -> tuple[dict[str, Any], ...]:
    enriched = []
    for finding in findings:
        item = dict(finding)
        item.update(
            {
                "rule_id": rule.rule_id,
                "rule_pack_id": rule.rule_pack_id,
                "domain_id": rule.domain_id.value,
                "provenance_type": rule.provenance_type.value,
                "required_concepts": list(rule.required_concepts),
                "resolved_columns": [column.to_dict() for column in resolved_columns],
                "human_review_required": rule.human_review_required,
                "policy_requirement": rule.policy_requirement,
            }
        )
        enriched.append(item)
    return tuple(enriched)


def _evaluate_legacy_rule(
    dataframe: pd.DataFrame,
    rule: RuleDefinition,
    resolved_columns: Mapping[str, ResolvedConceptColumn],
    legacy_evaluator: Callable[[pd.DataFrame], tuple[list[dict[str, Any]], bool]],
    concept_registry: ConceptRegistry,
) -> RuleExecutionResult:
    required = tuple(resolved_columns[concept_id] for concept_id in rule.required_concepts)
    try:
        findings, evaluated = legacy_evaluator(
            _canonical_dataframe(
                dataframe,
                resolved_columns,
                rule.required_concepts,
                concept_registry,
            )
        )
    except Exception as error:  # Preserve a per-rule error state for future integrations.
        return RuleExecutionResult(rule.rule_id, RULE_STATE_ERROR, (), required, str(error))
    state = RULE_STATE_EVALUATED if evaluated else RULE_STATE_NOT_APPLICABLE
    return RuleExecutionResult(
        rule.rule_id,
        state,
        _enrich_findings(findings, rule, required),
        required,
    )


def _evaluate_bed_capacity(
    dataframe: pd.DataFrame,
    rule: RuleDefinition,
    resolved_columns: Mapping[str, ResolvedConceptColumn],
    concept_registry: ConceptRegistry,
) -> RuleExecutionResult:
    return _evaluate_legacy_rule(
        dataframe,
        rule,
        resolved_columns,
        _beds_rule,
        concept_registry,
    )


def _evaluate_internet_bandwidth(
    dataframe: pd.DataFrame,
    rule: RuleDefinition,
    resolved_columns: Mapping[str, ResolvedConceptColumn],
    concept_registry: ConceptRegistry,
) -> RuleExecutionResult:
    return _evaluate_legacy_rule(
        dataframe,
        rule,
        resolved_columns,
        _internet_rule,
        concept_registry,
    )


EVALUATOR_ALLOWLIST: dict[
    str,
    Callable[
        [pd.DataFrame, RuleDefinition, Mapping[str, ResolvedConceptColumn], ConceptRegistry],
        RuleExecutionResult,
    ],
] = {
    "health_bed_capacity_consistency": _evaluate_bed_capacity,
    "health_internet_bandwidth_consistency": _evaluate_internet_bandwidth,
}
if frozenset(EVALUATOR_ALLOWLIST) != KNOWN_EVALUATOR_IDS:  # pragma: no cover - import-time invariant
    raise RuntimeError("Evaluator allowlist tidak selaras dengan registry metadata.")


def run_domain_rule_validation(
    dataframe: pd.DataFrame,
    *,
    selected_domain: DomainId | str,
    rule_registry: RuleRegistry | None = None,
    concept_registry: ConceptRegistry | None = None,
) -> DomainRuleExecutionSummary:
    """Run allowlisted rules for one explicit domain without mutating the dataframe."""
    domain_id = validate_domain_id(selected_domain)
    active_concepts = concept_registry or load_concept_registry()
    active_rules = rule_registry or load_rule_registry(concept_registry=active_concepts)
    resolved, ambiguous = _resolve_concept_columns(dataframe, domain_id, active_concepts)
    results = []
    for rule in active_rules.rules_for_domain(domain_id):
        missing = [concept_id for concept_id in rule.required_concepts if concept_id not in resolved]
        rule_columns = tuple(resolved[concept_id] for concept_id in rule.required_concepts if concept_id in resolved)
        if any(concept_id in ambiguous for concept_id in rule.required_concepts):
            results.append(RuleExecutionResult(rule.rule_id, RULE_STATE_SKIPPED_AMBIGUOUS_CONCEPT, (), rule_columns))
            continue
        if missing:
            results.append(RuleExecutionResult(rule.rule_id, RULE_STATE_SKIPPED_MISSING_CONCEPT, (), rule_columns))
            continue
        evaluator = EVALUATOR_ALLOWLIST.get(rule.evaluator_id)
        if evaluator is None:  # Defensive guard even though registry validation rejects it.
            results.append(RuleExecutionResult(rule.rule_id, RULE_STATE_ERROR, (), rule_columns, "evaluator_id tidak dikenal"))
            continue
        try:
            results.append(evaluator(dataframe, rule, resolved, active_concepts))
        except Exception as error:  # Do not let one controlled rule crash generic checks.
            results.append(
                RuleExecutionResult(
                    rule.rule_id,
                    RULE_STATE_ERROR,
                    (),
                    rule_columns,
                    str(error),
                )
            )
    results_tuple = tuple(results)
    evaluated = sum(result.state == RULE_STATE_EVALUATED for result in results_tuple)
    skipped = sum(result.state != RULE_STATE_EVALUATED for result in results_tuple)
    findings_count = sum(len(result.findings) for result in results_tuple)
    return DomainRuleExecutionSummary(
        selected_domain=domain_id,
        active_rule_packs=tuple(sorted({rule.rule_pack_id for rule in active_rules.rules_for_domain(domain_id)})),
        rules_total=len(results_tuple),
        rules_evaluated=evaluated,
        rules_skipped=skipped,
        findings_count=findings_count,
        rule_results=results_tuple,
    )
