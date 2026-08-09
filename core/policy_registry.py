"""Typed, local-only policy registry loading for the v0.3 foundation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from core.domain_models import DomainId, validate_domain_id


POLICY_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "policy_registry.json"
REPOSITORY_ROOT = POLICY_REGISTRY_PATH.parents[1]
POLICY_DIRECTORY = REPOSITORY_ROOT / "data" / "policies"

VALID_POLICY_PACKS = frozenset(
    {"government_generic", "healthcare", "education", "environment"}
)
VALID_CLASSIFICATIONS = frozenset({"ESSENTIAL", "SUPPORTING", "REFERENCE_ONLY"})
VALID_EFFECTIVE_STATUSES = frozenset({"current"})
VALID_VERIFICATION_STATES = frozenset({"verified"})
VALID_DOCUMENT_TYPES = frozenset(
    {
        "governance_policy",
        "technical_governance_framework",
        "metadata_governance_policy",
        "sectoral_data_governance",
    }
)
REQUIRED_POLICY_FIELDS = frozenset(
    {
        "policy_id",
        "title",
        "number",
        "year",
        "authority",
        "domain_id",
        "policy_pack",
        "document_type",
        "classification",
        "effective_status",
        "topics",
        "scope",
        "local_file",
        "verification_state",
    }
)


class PolicyRegistryError(ValueError):
    """Raised when deterministic policy-registry validation fails."""


@dataclass(frozen=True)
class PolicyRecord:
    """One compact, immutable policy record without PDF content or secrets."""

    policy_id: str
    title: str
    number: str
    year: int
    authority: str
    domain_id: DomainId
    policy_pack: str
    document_type: str
    classification: str
    effective_status: str
    topics: tuple[str, ...]
    scope: str
    local_file: str
    verification_state: str

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-safe policy metadata used by later milestones."""
        return {
            "policy_id": self.policy_id,
            "title": self.title,
            "number": self.number,
            "year": self.year,
            "authority": self.authority,
            "domain_id": self.domain_id.value,
            "policy_pack": self.policy_pack,
            "document_type": self.document_type,
            "classification": self.classification,
            "effective_status": self.effective_status,
            "topics": list(self.topics),
            "scope": self.scope,
            "local_file": self.local_file,
            "verification_state": self.verification_state,
        }


@dataclass(frozen=True)
class PolicyRegistry:
    """Validated registry with deterministic snapshot and lookup helpers."""

    schema_version: str
    policies: tuple[PolicyRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a canonical, JSON-safe registry representation."""
        return {
            "schema_version": self.schema_version,
            "policies": [
                policy.to_dict()
                for policy in sorted(self.policies, key=lambda item: item.policy_id)
            ],
        }

    def canonical_snapshot(self) -> str:
        """Serialize registry-relevant metadata in a deterministic JSON form."""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def fingerprint(self) -> str:
        """Return a metadata-only fingerprint, not an ingestion/corpus fingerprint."""
        return sha256(self.canonical_snapshot().encode("utf-8")).hexdigest()

    def get(self, policy_id: str) -> PolicyRecord:
        """Return one registered policy or raise a clear KeyError."""
        for policy in self.policies:
            if policy.policy_id == policy_id:
                return policy
        raise KeyError(f"Policy ID tidak ditemukan: {policy_id}")


def _required_string(raw: Mapping[str, Any], field_name: str) -> str:
    value = raw.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise PolicyRegistryError(f"Field policy {field_name!r} harus berupa string tidak kosong.")
    return value.strip()


def _validate_local_file(value: str) -> str:
    if "\\" in value:
        raise PolicyRegistryError("local_file harus menggunakan path relatif POSIX.")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.parts[:2] != ("data", "policies"):
        raise PolicyRegistryError("local_file harus berada di bawah data/policies/." )
    if len(path.parts) < 3 or not path.name:
        raise PolicyRegistryError("local_file harus menunjuk file di bawah data/policies/.")
    return path.as_posix()


def _parse_policy_record(raw: Mapping[str, Any]) -> PolicyRecord:
    if not isinstance(raw, Mapping):
        raise PolicyRegistryError("Setiap policy harus berupa object JSON.")
    missing = REQUIRED_POLICY_FIELDS - set(raw)
    if missing:
        raise PolicyRegistryError(
            "Policy kehilangan field wajib: " + ", ".join(sorted(missing))
        )
    unknown = set(raw) - REQUIRED_POLICY_FIELDS
    if unknown:
        raise PolicyRegistryError(
            "Policy memiliki field yang tidak didukung: " + ", ".join(sorted(unknown))
        )

    policy_id = _required_string(raw, "policy_id")
    try:
        domain_id = validate_domain_id(_required_string(raw, "domain_id"))
    except ValueError as error:
        raise PolicyRegistryError(str(error)) from error

    year = raw.get("year")
    if type(year) is not int or year < 1900 or year > 2100:
        raise PolicyRegistryError("Field policy 'year' harus berupa integer tahun yang didukung.")

    policy_pack = _required_string(raw, "policy_pack")
    if policy_pack not in VALID_POLICY_PACKS:
        raise PolicyRegistryError(f"policy_pack tidak didukung: {policy_pack!r}")

    document_type = _required_string(raw, "document_type")
    if document_type not in VALID_DOCUMENT_TYPES:
        raise PolicyRegistryError(f"document_type tidak didukung: {document_type!r}")

    classification = _required_string(raw, "classification")
    if classification not in VALID_CLASSIFICATIONS:
        raise PolicyRegistryError(f"classification tidak didukung: {classification!r}")

    effective_status = _required_string(raw, "effective_status")
    if effective_status not in VALID_EFFECTIVE_STATUSES:
        raise PolicyRegistryError(
            f"effective_status tidak didukung: {effective_status!r}"
        )

    verification_state = _required_string(raw, "verification_state")
    if verification_state not in VALID_VERIFICATION_STATES:
        raise PolicyRegistryError(
            f"verification_state tidak didukung: {verification_state!r}"
        )

    topics = raw.get("topics")
    if (
        not isinstance(topics, list)
        or not topics
        or any(not isinstance(topic, str) or not topic.strip() for topic in topics)
    ):
        raise PolicyRegistryError("topics harus berupa list string tidak kosong.")
    normalized_topics = tuple(topic.strip() for topic in topics)
    if len(set(normalized_topics)) != len(normalized_topics):
        raise PolicyRegistryError("topics tidak boleh memiliki nilai duplikat.")

    return PolicyRecord(
        policy_id=policy_id,
        title=_required_string(raw, "title"),
        number=_required_string(raw, "number"),
        year=year,
        authority=_required_string(raw, "authority"),
        domain_id=domain_id,
        policy_pack=policy_pack,
        document_type=document_type,
        classification=classification,
        effective_status=effective_status,
        topics=normalized_topics,
        scope=_required_string(raw, "scope"),
        local_file=_validate_local_file(_required_string(raw, "local_file")),
        verification_state=verification_state,
    )


def parse_policy_registry(raw: Mapping[str, Any]) -> PolicyRegistry:
    """Validate a JSON-compatible registry mapping without accessing local files."""
    if not isinstance(raw, Mapping):
        raise PolicyRegistryError("Registry harus berupa object JSON.")
    if set(raw) != {"schema_version", "policies"}:
        raise PolicyRegistryError("Registry hanya mendukung schema_version dan policies.")
    schema_version = raw.get("schema_version")
    if schema_version != "1.0":
        raise PolicyRegistryError("schema_version registry harus bernilai '1.0'.")
    raw_policies = raw.get("policies")
    if not isinstance(raw_policies, list) or not raw_policies:
        raise PolicyRegistryError("policies harus berupa list tidak kosong.")

    policies = tuple(_parse_policy_record(item) for item in raw_policies)
    policy_ids = [policy.policy_id for policy in policies]
    local_files = [policy.local_file for policy in policies]
    if len(set(policy_ids)) != len(policy_ids):
        raise PolicyRegistryError("policy_id tidak boleh duplikat.")
    if len(set(local_files)) != len(local_files):
        raise PolicyRegistryError("local_file tidak boleh dipetakan ke lebih dari satu policy.")
    return PolicyRegistry(schema_version=schema_version, policies=policies)


def load_policy_registry(path: str | Path = POLICY_REGISTRY_PATH) -> PolicyRegistry:
    """Load and validate a local JSON registry without PDF parsing or ingestion."""
    registry_path = Path(path)
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise PolicyRegistryError(f"File registry tidak ditemukan: {registry_path}") from error
    except json.JSONDecodeError as error:
        raise PolicyRegistryError(f"JSON registry tidak valid: {registry_path}") from error
    return parse_policy_registry(raw)


def resolve_policy_file(
    policy: PolicyRecord,
    *,
    repository_root: str | Path = REPOSITORY_ROOT,
    require_exists: bool = True,
) -> Path:
    """Resolve one registry path safely under the repository policy directory."""
    root = Path(repository_root).resolve()
    policy_directory = (root / "data" / "policies").resolve()
    candidate = (root / Path(policy.local_file)).resolve()
    try:
        candidate.relative_to(policy_directory)
    except ValueError as error:
        raise PolicyRegistryError("local_file berada di luar data/policies/.") from error
    if require_exists and not candidate.is_file():
        raise PolicyRegistryError(f"File policy tidak ditemukan: {policy.local_file}")
    return candidate
