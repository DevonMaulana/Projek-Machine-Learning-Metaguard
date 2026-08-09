"""Tests for explicit, deterministic MetaGuard analysis semantics."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from core.analysis_context import build_analysis_context
from core.concept_registry import parse_concept_registry
from core.policy_registry import parse_policy_registry
from core.rule_registry import parse_rule_registry


def _read_json(path: str) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_analysis_context_is_json_safe_and_stable() -> None:
    first = build_analysis_context(
        selected_domain="generic",
        governance_context="generic_non_government",
    )
    second = build_analysis_context(
        selected_domain="generic",
        governance_context="generic_non_government",
    )
    assert first.fingerprint() == second.fingerprint()
    assert first.canonical_snapshot() == second.canonical_snapshot()
    assert first.to_dict()["selected_domain"] == "generic"
    assert first.to_dict()["governance_context"] == "generic_non_government"
    json.dumps(first.to_dict(), ensure_ascii=False)


def test_selected_domain_and_governance_context_are_independent_fingerprint_inputs() -> None:
    generic = build_analysis_context(
        selected_domain="generic",
        governance_context="generic_non_government",
    )
    healthcare_non_government = build_analysis_context(
        selected_domain="healthcare",
        governance_context="generic_non_government",
    )
    healthcare_government = build_analysis_context(
        selected_domain="healthcare",
        governance_context="government_public",
    )
    assert generic.fingerprint() != healthcare_non_government.fingerprint()
    assert healthcare_non_government.fingerprint() != healthcare_government.fingerprint()


def test_registry_fingerprints_contribute_to_analysis_context() -> None:
    raw_concepts = _read_json("data/concept_registry.json")
    concepts = parse_concept_registry(raw_concepts)
    raw_rules = _read_json("data/rule_registry.json")
    rules = parse_rule_registry(raw_rules, concept_registry=concepts)
    raw_policies = _read_json("data/policy_registry.json")
    policies = parse_policy_registry(raw_policies)
    baseline = build_analysis_context(
        selected_domain="healthcare",
        governance_context="government_public",
        concept_registry=concepts,
        rule_registry=rules,
        policy_registry=policies,
    )

    changed_concepts = replace(concepts, schema_version="1.0")
    changed_rules = replace(rules, schema_version="1.0")
    changed_policies = replace(policies, schema_version="1.0")
    # Altering any registry's canonical metadata must alter the composite context.
    changed_concepts = replace(
        changed_concepts,
        concepts=(replace(changed_concepts.concepts[0], description="changed"), *changed_concepts.concepts[1:]),
    )
    changed_rules = replace(
        changed_rules,
        rules=(replace(changed_rules.rules[0], interpretation_note="changed"), *changed_rules.rules[1:]),
    )
    changed_policies = replace(
        changed_policies,
        policies=(replace(changed_policies.policies[0], title="changed"), *changed_policies.policies[1:]),
    )
    for modified_concepts, modified_rules, modified_policies in (
        (changed_concepts, rules, policies),
        (concepts, changed_rules, policies),
        (concepts, rules, changed_policies),
    ):
        changed = build_analysis_context(
            selected_domain="healthcare",
            governance_context="government_public",
            concept_registry=modified_concepts,
            rule_registry=modified_rules,
            policy_registry=modified_policies,
        )
        assert changed.fingerprint() != baseline.fingerprint()
