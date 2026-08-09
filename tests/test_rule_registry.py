"""Tests for declarative, non-executable MetaGuard domain-rule metadata."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from core.concept_registry import load_concept_registry
from core.rule_registry import (
    ProvenanceType,
    RuleRegistryError,
    load_rule_registry,
    parse_rule_registry,
)


def _raw_registry() -> dict[str, object]:
    return json.loads(Path("data/rule_registry.json").read_text(encoding="utf-8"))


def test_rule_registry_loads_stable_domain_packs_without_policy_claims() -> None:
    registry = load_rule_registry()
    assert [rule.rule_id for rule in registry.rules] == [
        "HEALTH-BED-CAPACITY-001",
        "HEALTH-INTERNET-BANDWIDTH-001",
        "EDU-STUDENT-TEACHER-001",
        "EDU-STUDENT-CLASSROOM-001",
        "ENV-SENSOR-MEASUREMENT-001",
    ]
    assert {rule.rule_pack_id for rule in registry.rules} == {
        "healthcare_core",
        "education_core",
        "environment_core",
    }
    assert {rule.domain_id.value for rule in registry.rules} == {"healthcare", "education", "environment"}
    assert registry.rules[0].provenance_type is ProvenanceType.DETERMINISTIC_INVARIANT
    assert registry.rules[1].provenance_type is ProvenanceType.HEURISTIC
    pilot_rules = [rule for rule in registry.rules if rule.domain_id.value in {"education", "environment"}]
    assert all(rule.provenance_type is ProvenanceType.HEURISTIC for rule in pilot_rules)
    assert all(not rule.policy_requirement for rule in registry.rules)


def test_rule_registry_is_json_safe_and_snapshot_is_order_independent() -> None:
    raw = _raw_registry()
    reordered = copy.deepcopy(raw)
    reordered["rules"].reverse()  # type: ignore[index]
    registry = parse_rule_registry(raw)
    other = parse_rule_registry(reordered)
    assert registry.canonical_snapshot() == other.canonical_snapshot()
    assert registry.fingerprint() == other.fingerprint()
    json.dumps(registry.to_dict(), ensure_ascii=False)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("rule_id", "", "string tidak kosong"),
        ("domain_id", "unknown", "Domain tidak didukung"),
        ("rule_pack_id", "unknown", "rule_pack_id"),
        ("severity", "critical", "severity"),
        ("provenance_type", "LEGAL", "provenance_type"),
        ("evaluator_id", "arbitrary_python", "evaluator_id"),
        ("required_concepts", [], "required_concepts"),
    ],
)
def test_rule_registry_rejects_invalid_values(field: str, value: object, message: str) -> None:
    raw = _raw_registry()
    raw["rules"][0][field] = value  # type: ignore[index]
    with pytest.raises(RuleRegistryError, match=message):
        parse_rule_registry(raw)


def test_rule_registry_rejects_duplicate_ids_unknown_fields_and_concept_errors() -> None:
    raw = _raw_registry()
    duplicate = copy.deepcopy(raw["rules"][0])  # type: ignore[index]
    raw["rules"].append(duplicate)  # type: ignore[index]
    with pytest.raises(RuleRegistryError, match="rule_id tidak boleh duplikat"):
        parse_rule_registry(raw)

    raw = _raw_registry()
    raw["rules"][0]["callable"] = "os.system"  # type: ignore[index]
    with pytest.raises(RuleRegistryError, match="field tidak didukung"):
        parse_rule_registry(raw)

    raw = _raw_registry()
    raw["rules"][0]["required_concepts"] = ["student_count"]  # type: ignore[index]
    with pytest.raises(RuleRegistryError, match="bukan milik domain rule"):
        parse_rule_registry(raw)


def test_rule_registry_rejects_duplicate_or_unknown_required_concepts() -> None:
    raw = _raw_registry()
    raw["rules"][0]["required_concepts"] = ["occupied_beds", "occupied_beds"]  # type: ignore[index]
    with pytest.raises(RuleRegistryError, match="duplikat"):
        parse_rule_registry(raw)

    raw = _raw_registry()
    raw["rules"][0]["required_concepts"] = ["not_a_concept"]  # type: ignore[index]
    with pytest.raises(RuleRegistryError, match="tidak ditemukan"):
        parse_rule_registry(raw)


def test_rule_registry_scopes_rules_strictly_to_their_domain() -> None:
    registry = load_rule_registry()
    assert {rule.rule_pack_id for rule in registry.rules_for_domain("education")} == {"education_core"}
    assert {rule.rule_pack_id for rule in registry.rules_for_domain("environment")} == {"environment_core"}
    assert not registry.rules_for_domain("generic")
    assert not registry.rules_for_domain("other")
    assert {rule.rule_pack_id for rule in registry.rules_for_domain("healthcare")} == {"healthcare_core"}


def test_rule_registry_can_validate_against_an_explicit_concept_registry() -> None:
    concepts = load_concept_registry()
    registry = load_rule_registry(concept_registry=concepts)
    assert len(registry.rules) == 5


def test_rule_registry_rejects_cross_domain_optional_concepts() -> None:
    raw = _raw_registry()
    raw["rules"][2]["optional_concepts"] = ["pm25_measurement"]  # type: ignore[index]
    with pytest.raises(RuleRegistryError, match="bukan milik domain rule"):
        parse_rule_registry(raw)
