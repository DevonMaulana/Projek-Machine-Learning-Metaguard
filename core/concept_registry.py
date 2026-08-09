"""Deterministic semantic concept registry for future domain-aware validation.

The registry maps normalized column names to curated concepts only. It does not
evaluate dataframe values, activate rules, or infer a domain.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
import unicodedata

from core.domain_models import DomainId, validate_domain_id


CONCEPT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "concept_registry.json"
VALID_EXPECTED_DATA_TYPES = frozenset(
    {"integer", "number", "string", "date", "percentage"}
)
REQUIRED_CONCEPT_FIELDS = frozenset(
    {"concept_id", "domain_id", "canonical_name", "aliases", "description"}
)
OPTIONAL_CONCEPT_FIELDS = frozenset({"expected_data_type", "unit_expectation"})


class ConceptRegistryError(ValueError):
    """Raised when deterministic concept-registry validation fails."""


def normalize_column_name(value: object) -> str:
    """Normalize a column name with conservative, exact-match-friendly rules."""
    normalized = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    normalized = re.sub(r"[\s\-./]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


@dataclass(frozen=True)
class ConceptRecord:
    """One curated semantic mapping; aliases are MetaGuard mappings, not policy."""

    concept_id: str
    domain_id: DomainId
    canonical_name: str
    aliases: tuple[str, ...]
    description: str
    expected_data_type: str | None = None
    unit_expectation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe declarative metadata without executable behavior."""
        result: dict[str, Any] = {
            "concept_id": self.concept_id,
            "domain_id": self.domain_id.value,
            "canonical_name": self.canonical_name,
            "aliases": list(self.aliases),
            "description": self.description,
        }
        if self.expected_data_type is not None:
            result["expected_data_type"] = self.expected_data_type
        if self.unit_expectation is not None:
            result["unit_expectation"] = self.unit_expectation
        return result


@dataclass(frozen=True)
class ConceptResolution:
    """Compact result of resolving one input column against a selected domain."""

    column: str
    normalized_column: str
    concept_id: str | None
    domain_id: DomainId
    matched_alias: str | None
    is_duplicate_normalized_column: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe resolution without dataframe references."""
        return {
            "column": self.column,
            "normalized_column": self.normalized_column,
            "concept_id": self.concept_id,
            "domain_id": self.domain_id.value,
            "matched_alias": self.matched_alias,
            "is_duplicate_normalized_column": self.is_duplicate_normalized_column,
        }


@dataclass(frozen=True)
class ConceptRegistry:
    """Validated concept records with deterministic resolution and snapshots."""

    schema_version: str
    concepts: tuple[ConceptRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a canonical JSON-safe representation sorted by concept ID."""
        return {
            "schema_version": self.schema_version,
            "concepts": [
                concept.to_dict()
                for concept in sorted(self.concepts, key=lambda item: item.concept_id)
            ],
        }

    def canonical_snapshot(self) -> str:
        """Return deterministic metadata JSON suitable for a future fingerprint."""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def fingerprint(self) -> str:
        """Return a metadata-only fingerprint, excluding runtime dataframe columns."""
        return sha256(self.canonical_snapshot().encode("utf-8")).hexdigest()

    def get(self, concept_id: str) -> ConceptRecord:
        """Return one registered concept or raise a clear KeyError."""
        for concept in self.concepts:
            if concept.concept_id == concept_id:
                return concept
        raise KeyError(f"Concept ID tidak ditemukan: {concept_id}")

    def resolve(
        self,
        column: object,
        selected_domain: DomainId | str,
    ) -> ConceptResolution:
        """Resolve exact aliases in selected domain, then generic when applicable."""
        domain_id = validate_domain_id(selected_domain)
        normalized_column = normalize_column_name(column)
        search_domains = (domain_id,) if domain_id is DomainId.GENERIC else (
            domain_id,
            DomainId.GENERIC,
        )
        for search_domain in search_domains:
            for concept in self.concepts:
                if concept.domain_id is not search_domain:
                    continue
                if normalized_column in concept.aliases:
                    return ConceptResolution(
                        column=str(column),
                        normalized_column=normalized_column,
                        concept_id=concept.concept_id,
                        domain_id=concept.domain_id,
                        matched_alias=normalized_column,
                    )
        return ConceptResolution(
            column=str(column),
            normalized_column=normalized_column,
            concept_id=None,
            domain_id=domain_id,
            matched_alias=None,
        )

    def map_columns(
        self,
        columns: Iterable[object],
        selected_domain: DomainId | str,
    ) -> tuple[ConceptResolution, ...]:
        """Resolve columns without mutating their source and flag normalized duplicates."""
        column_values = tuple(columns)
        normalized_values = tuple(normalize_column_name(column) for column in column_values)
        counts = Counter(normalized_values)
        resolutions = []
        for column, normalized_column in zip(column_values, normalized_values, strict=True):
            resolution = self.resolve(column, selected_domain)
            resolutions.append(
                replace(
                    resolution,
                    is_duplicate_normalized_column=(
                        bool(normalized_column) and counts[normalized_column] > 1
                    ),
                )
            )
        return tuple(resolutions)


def _required_string(raw: Mapping[str, Any], field_name: str) -> str:
    value = raw.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ConceptRegistryError(
            f"Field concept {field_name!r} harus berupa string tidak kosong."
        )
    return value.strip()


def _parse_optional_string(raw: Mapping[str, Any], field_name: str) -> str | None:
    if field_name not in raw:
        return None
    return _required_string(raw, field_name)


def _parse_concept_record(raw: Mapping[str, Any]) -> ConceptRecord:
    if not isinstance(raw, Mapping):
        raise ConceptRegistryError("Setiap concept harus berupa object JSON.")
    missing = REQUIRED_CONCEPT_FIELDS - set(raw)
    if missing:
        raise ConceptRegistryError(
            "Concept kehilangan field wajib: " + ", ".join(sorted(missing))
        )
    unknown = set(raw) - REQUIRED_CONCEPT_FIELDS - OPTIONAL_CONCEPT_FIELDS
    if unknown:
        raise ConceptRegistryError(
            "Concept memiliki field yang tidak didukung: " + ", ".join(sorted(unknown))
        )

    try:
        domain_id = validate_domain_id(_required_string(raw, "domain_id"))
    except ValueError as error:
        raise ConceptRegistryError(str(error)) from error

    canonical_name = _required_string(raw, "canonical_name")
    normalized_canonical_name = normalize_column_name(canonical_name)
    if not normalized_canonical_name:
        raise ConceptRegistryError("canonical_name harus memiliki bentuk ter-normalisasi.")

    aliases = raw.get("aliases")
    if (
        not isinstance(aliases, list)
        or not aliases
        or any(not isinstance(alias, str) or not alias.strip() for alias in aliases)
    ):
        raise ConceptRegistryError("aliases harus berupa list string tidak kosong.")
    normalized_aliases = tuple(normalize_column_name(alias) for alias in aliases)
    if not all(normalized_aliases):
        raise ConceptRegistryError("aliases tidak boleh kosong setelah normalisasi.")
    if len(set(normalized_aliases)) != len(normalized_aliases):
        raise ConceptRegistryError("aliases memiliki duplikat setelah normalisasi.")
    if normalized_canonical_name not in normalized_aliases:
        raise ConceptRegistryError("canonical_name harus tercantum dalam aliases.")

    expected_data_type = _parse_optional_string(raw, "expected_data_type")
    if expected_data_type is not None and expected_data_type not in VALID_EXPECTED_DATA_TYPES:
        raise ConceptRegistryError(
            f"expected_data_type tidak didukung: {expected_data_type!r}"
        )

    return ConceptRecord(
        concept_id=_required_string(raw, "concept_id"),
        domain_id=domain_id,
        canonical_name=normalized_canonical_name,
        aliases=normalized_aliases,
        description=_required_string(raw, "description"),
        expected_data_type=expected_data_type,
        unit_expectation=_parse_optional_string(raw, "unit_expectation"),
    )


def parse_concept_registry(raw: Mapping[str, Any]) -> ConceptRegistry:
    """Validate JSON-compatible concept metadata without reading dataframe values."""
    if not isinstance(raw, Mapping):
        raise ConceptRegistryError("Registry concept harus berupa object JSON.")
    if set(raw) != {"schema_version", "concepts"}:
        raise ConceptRegistryError("Registry concept hanya mendukung schema_version dan concepts.")
    if raw.get("schema_version") != "1.0":
        raise ConceptRegistryError("schema_version concept registry harus bernilai '1.0'.")
    raw_concepts = raw.get("concepts")
    if not isinstance(raw_concepts, list) or not raw_concepts:
        raise ConceptRegistryError("concepts harus berupa list tidak kosong.")

    concepts = tuple(_parse_concept_record(raw_concept) for raw_concept in raw_concepts)
    concept_ids = [concept.concept_id for concept in concepts]
    if len(set(concept_ids)) != len(concept_ids):
        raise ConceptRegistryError("concept_id tidak boleh duplikat.")

    aliases_by_domain: dict[DomainId, dict[str, str]] = {}
    for concept in concepts:
        domain_aliases = aliases_by_domain.setdefault(concept.domain_id, {})
        for alias in concept.aliases:
            previous = domain_aliases.get(alias)
            if previous is not None and previous != concept.concept_id:
                raise ConceptRegistryError(
                    "Alias ter-normalisasi collision pada domain "
                    f"{concept.domain_id.value!r}: {alias!r}."
                )
            domain_aliases[alias] = concept.concept_id
    return ConceptRegistry(schema_version="1.0", concepts=concepts)


def load_concept_registry(path: str | Path = CONCEPT_REGISTRY_PATH) -> ConceptRegistry:
    """Load a local declarative concept registry without network or code execution."""
    registry_path = Path(path)
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConceptRegistryError(f"File concept registry tidak ditemukan: {registry_path}") from error
    except json.JSONDecodeError as error:
        raise ConceptRegistryError(f"JSON concept registry tidak valid: {registry_path}") from error
    return parse_concept_registry(raw)


def resolve_concept(
    column: object,
    selected_domain: DomainId | str,
    registry: ConceptRegistry | None = None,
) -> ConceptResolution:
    """Resolve one column using an explicit domain and a validated registry."""
    active_registry = registry or load_concept_registry()
    return active_registry.resolve(column, selected_domain)


def map_dataframe_columns(
    columns: Iterable[object],
    selected_domain: DomainId | str,
    registry: ConceptRegistry | None = None,
) -> tuple[ConceptResolution, ...]:
    """Map dataframe-like columns without importing or mutating pandas objects."""
    active_registry = registry or load_concept_registry()
    return active_registry.map_columns(columns, selected_domain)
