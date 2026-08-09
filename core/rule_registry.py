"""Declarative, validated domain-rule metadata for MetaGuard v0.3.

Rule definitions identify only allowlisted evaluator IDs.  They never carry
executable code, import paths, or expressions from the JSON registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from core.concept_registry import ConceptRegistry, load_concept_registry
from core.domain_models import DomainId, validate_domain_id


RULE_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "rule_registry.json"
VALID_SEVERITIES = frozenset({"high", "medium", "low", "info"})
VALID_RULE_TYPES = frozenset({"cross_column"})
VALID_RULE_PACK_IDS = frozenset({"healthcare_core"})
KNOWN_EVALUATOR_IDS = frozenset(
    {"health_bed_capacity_consistency", "health_internet_bandwidth_consistency"}
)
REQUIRED_RULE_FIELDS = frozenset(
    {
        "rule_id",
        "domain_id",
        "rule_pack_id",
        "name",
        "description",
        "severity",
        "rule_type",
        "required_concepts",
        "evaluator_id",
        "provenance_type",
        "policy_requirement",
        "human_review_required",
        "interpretation_note",
    }
)
OPTIONAL_RULE_FIELDS = frozenset({"optional_concepts"})


class RuleRegistryError(ValueError):
    """Raised when deterministic domain-rule registry validation fails."""


class ProvenanceType(str, Enum):
    """Declare the non-legal basis of a deterministic rule."""

    DETERMINISTIC_INVARIANT = "DETERMINISTIC_INVARIANT"
    POLICY_SUPPORTED = "POLICY_SUPPORTED"
    TECHNICAL_STANDARD = "TECHNICAL_STANDARD"
    HEURISTIC = "HEURISTIC"


@dataclass(frozen=True)
class RuleDefinition:
    """Immutable declarative definition for one allowlisted domain rule."""

    rule_id: str
    domain_id: DomainId
    rule_pack_id: str
    name: str
    description: str
    severity: str
    rule_type: str
    required_concepts: tuple[str, ...]
    optional_concepts: tuple[str, ...]
    evaluator_id: str
    provenance_type: ProvenanceType
    policy_requirement: bool
    human_review_required: bool
    interpretation_note: str

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe rule metadata without executable behavior."""
        return {
            "rule_id": self.rule_id,
            "domain_id": self.domain_id.value,
            "rule_pack_id": self.rule_pack_id,
            "name": self.name,
            "description": self.description,
            "severity": self.severity,
            "rule_type": self.rule_type,
            "required_concepts": list(self.required_concepts),
            "optional_concepts": list(self.optional_concepts),
            "evaluator_id": self.evaluator_id,
            "provenance_type": self.provenance_type.value,
            "policy_requirement": self.policy_requirement,
            "human_review_required": self.human_review_required,
            "interpretation_note": self.interpretation_note,
        }


@dataclass(frozen=True)
class RuleRegistry:
    """Validated rule definitions with deterministic canonical snapshots."""

    schema_version: str
    rules: tuple[RuleDefinition, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return canonical JSON-safe metadata sorted by stable rule ID."""
        return {
            "schema_version": self.schema_version,
            "rules": [rule.to_dict() for rule in sorted(self.rules, key=lambda item: item.rule_id)],
        }

    def canonical_snapshot(self) -> str:
        """Return deterministic metadata JSON suitable for future fingerprinting."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def fingerprint(self) -> str:
        """Return a rule-metadata fingerprint without dataframe or policy-file data."""
        return sha256(self.canonical_snapshot().encode("utf-8")).hexdigest()

    def rules_for_domain(self, domain_id: DomainId | str) -> tuple[RuleDefinition, ...]:
        """Return rules scoped strictly to an explicit selected domain."""
        selected_domain = validate_domain_id(domain_id)
        return tuple(rule for rule in self.rules if rule.domain_id is selected_domain)


def _required_string(raw: Mapping[str, Any], field_name: str) -> str:
    value = raw.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise RuleRegistryError(f"Field rule {field_name!r} harus berupa string tidak kosong.")
    return value.strip()


def _parse_concept_ids(raw: Mapping[str, Any], field_name: str, *, required: bool) -> tuple[str, ...]:
    if field_name not in raw and not required:
        return ()
    values = raw.get(field_name)
    if not isinstance(values, list) or (required and not values):
        raise RuleRegistryError(f"{field_name} harus berupa list {'tidak kosong' if required else 'string'}.")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise RuleRegistryError(f"{field_name} harus berupa list string tidak kosong.")
    parsed = tuple(value.strip() for value in values)
    if len(set(parsed)) != len(parsed):
        raise RuleRegistryError(f"{field_name} tidak boleh mengandung duplikat.")
    return parsed


def _validate_concepts(
    *,
    concepts: tuple[str, ...],
    domain_id: DomainId,
    concept_registry: ConceptRegistry,
) -> None:
    for concept_id in concepts:
        try:
            concept = concept_registry.get(concept_id)
        except KeyError as error:
            raise RuleRegistryError(f"Concept ID rule tidak ditemukan: {concept_id!r}") from error
        if concept.domain_id is not domain_id:
            raise RuleRegistryError(
                f"Concept {concept_id!r} bukan milik domain rule {domain_id.value!r}."
            )


def _parse_rule_definition(
    raw: Mapping[str, Any],
    *,
    concept_registry: ConceptRegistry,
) -> RuleDefinition:
    if not isinstance(raw, Mapping):
        raise RuleRegistryError("Setiap rule harus berupa object JSON.")
    missing = REQUIRED_RULE_FIELDS - set(raw)
    if missing:
        raise RuleRegistryError("Rule kehilangan field wajib: " + ", ".join(sorted(missing)))
    unknown = set(raw) - REQUIRED_RULE_FIELDS - OPTIONAL_RULE_FIELDS
    if unknown:
        raise RuleRegistryError("Rule memiliki field tidak didukung: " + ", ".join(sorted(unknown)))
    try:
        domain_id = validate_domain_id(_required_string(raw, "domain_id"))
    except ValueError as error:
        raise RuleRegistryError(str(error)) from error
    rule_pack_id = _required_string(raw, "rule_pack_id")
    if rule_pack_id not in VALID_RULE_PACK_IDS:
        raise RuleRegistryError(f"rule_pack_id tidak didukung: {rule_pack_id!r}")
    severity = _required_string(raw, "severity")
    if severity not in VALID_SEVERITIES:
        raise RuleRegistryError(f"severity tidak didukung: {severity!r}")
    rule_type = _required_string(raw, "rule_type")
    if rule_type not in VALID_RULE_TYPES:
        raise RuleRegistryError(f"rule_type tidak didukung: {rule_type!r}")
    evaluator_id = _required_string(raw, "evaluator_id")
    if evaluator_id not in KNOWN_EVALUATOR_IDS:
        raise RuleRegistryError(f"evaluator_id tidak dikenal: {evaluator_id!r}")
    try:
        provenance_type = ProvenanceType(_required_string(raw, "provenance_type"))
    except ValueError as error:
        raise RuleRegistryError(f"provenance_type tidak didukung: {raw.get('provenance_type')!r}") from error
    for field_name in ("policy_requirement", "human_review_required"):
        if not isinstance(raw.get(field_name), bool):
            raise RuleRegistryError(f"{field_name} harus berupa boolean.")
    required_concepts = _parse_concept_ids(raw, "required_concepts", required=True)
    optional_concepts = _parse_concept_ids(raw, "optional_concepts", required=False)
    if set(required_concepts) & set(optional_concepts):
        raise RuleRegistryError("required_concepts dan optional_concepts tidak boleh tumpang tindih.")
    _validate_concepts(concepts=required_concepts + optional_concepts, domain_id=domain_id, concept_registry=concept_registry)
    return RuleDefinition(
        rule_id=_required_string(raw, "rule_id"),
        domain_id=domain_id,
        rule_pack_id=rule_pack_id,
        name=_required_string(raw, "name"),
        description=_required_string(raw, "description"),
        severity=severity,
        rule_type=rule_type,
        required_concepts=required_concepts,
        optional_concepts=optional_concepts,
        evaluator_id=evaluator_id,
        provenance_type=provenance_type,
        policy_requirement=raw["policy_requirement"],
        human_review_required=raw["human_review_required"],
        interpretation_note=_required_string(raw, "interpretation_note"),
    )


def parse_rule_registry(
    raw: Mapping[str, Any],
    *,
    concept_registry: ConceptRegistry | None = None,
) -> RuleRegistry:
    """Validate JSON-compatible rule metadata against the concept registry."""
    if not isinstance(raw, Mapping) or set(raw) != {"schema_version", "rules"}:
        raise RuleRegistryError("Registry rule hanya mendukung schema_version dan rules.")
    if raw.get("schema_version") != "1.0":
        raise RuleRegistryError("schema_version rule registry harus bernilai '1.0'.")
    raw_rules = raw.get("rules")
    if not isinstance(raw_rules, list):
        raise RuleRegistryError("rules harus berupa list.")
    active_concepts = concept_registry or load_concept_registry()
    rules = tuple(_parse_rule_definition(item, concept_registry=active_concepts) for item in raw_rules)
    rule_ids = [rule.rule_id for rule in rules]
    if len(set(rule_ids)) != len(rule_ids):
        raise RuleRegistryError("rule_id tidak boleh duplikat.")
    return RuleRegistry(schema_version="1.0", rules=rules)


def load_rule_registry(
    path: str | Path = RULE_REGISTRY_PATH,
    *,
    concept_registry: ConceptRegistry | None = None,
) -> RuleRegistry:
    """Load local declarative rule metadata without code execution or network use."""
    registry_path = Path(path)
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuleRegistryError(f"File rule registry tidak ditemukan: {registry_path}") from error
    except json.JSONDecodeError as error:
        raise RuleRegistryError(f"JSON rule registry tidak valid: {registry_path}") from error
    return parse_rule_registry(raw, concept_registry=concept_registry)
