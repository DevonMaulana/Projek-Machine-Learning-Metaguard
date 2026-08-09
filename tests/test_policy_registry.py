import copy
import json
from pathlib import Path

import pytest

from core.policy_registry import (
    POLICY_REGISTRY_PATH,
    PolicyRegistryError,
    load_policy_registry,
    parse_policy_registry,
    resolve_policy_file,
)


def _payload() -> dict:
    return json.loads(POLICY_REGISTRY_PATH.read_text(encoding="utf-8"))


def test_registry_loads_the_six_verified_initial_policies() -> None:
    registry = load_policy_registry()

    assert registry.schema_version == "1.0"
    assert {policy.policy_id for policy in registry.policies} == {
        "GOV-SDI-PERPRES-39-2019",
        "BPS-STANDARD-DATA-4-2020",
        "BPS-METADATA-5-2020",
        "HEALTH-SATU-DATA-18-2022",
        "EDU-SATU-DATA-31-2022",
        "ENV-SATU-DATA-25-2021",
    }
    assert all(policy.classification == "ESSENTIAL" for policy in registry.policies)


def test_registry_preserves_pack_and_local_file_mappings() -> None:
    registry = load_policy_registry()

    assert registry.get("GOV-SDI-PERPRES-39-2019").policy_pack == (
        "government_generic"
    )
    assert registry.get("BPS-STANDARD-DATA-4-2020").policy_pack == (
        "government_generic"
    )
    assert registry.get("BPS-METADATA-5-2020").policy_pack == "government_generic"
    assert registry.get("HEALTH-SATU-DATA-18-2022").policy_pack == "healthcare"
    assert registry.get("EDU-SATU-DATA-31-2022").policy_pack == "education"
    environment = registry.get("ENV-SATU-DATA-25-2021")
    assert environment.policy_pack == "environment"
    assert environment.local_file == (
        "data/policies/PermenLHKNo25-Tahun2021-SatuDataKLHK.pdf"
    )


def test_registry_rejects_duplicate_or_empty_policy_id() -> None:
    duplicate = _payload()
    duplicate["policies"][1]["policy_id"] = duplicate["policies"][0]["policy_id"]
    with pytest.raises(PolicyRegistryError, match="policy_id tidak boleh duplikat"):
        parse_policy_registry(duplicate)

    empty = _payload()
    empty["policies"][0]["policy_id"] = " "
    with pytest.raises(PolicyRegistryError, match="policy_id"):
        parse_policy_registry(empty)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("domain_id", "unknown_domain", "Domain tidak didukung"),
        ("policy_pack", "unknown_pack", "policy_pack tidak didukung"),
        ("classification", "UNSUPPORTED", "classification tidak didukung"),
        ("effective_status", "revoked", "effective_status tidak didukung"),
        ("topics", "not-a-list", "topics harus berupa list"),
    ],
)
def test_registry_rejects_invalid_controlled_values(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = _payload()
    payload["policies"][0][field] = value

    with pytest.raises(PolicyRegistryError, match=message):
        parse_policy_registry(payload)


def test_registry_rejects_missing_or_duplicate_local_file_mapping() -> None:
    missing = _payload()
    del missing["policies"][0]["local_file"]
    with pytest.raises(PolicyRegistryError, match="local_file"):
        parse_policy_registry(missing)

    duplicate = _payload()
    duplicate["policies"][1]["local_file"] = duplicate["policies"][0]["local_file"]
    with pytest.raises(PolicyRegistryError, match="local_file tidak boleh"):
        parse_policy_registry(duplicate)


def test_registry_resolves_verified_local_files_and_rejects_unsafe_paths(
    tmp_path: Path,
) -> None:
    registry = load_policy_registry()
    for policy in registry.policies:
        resolved = resolve_policy_file(policy)
        assert resolved.is_file()
        assert resolved.name == Path(policy.local_file).name

    payload = _payload()
    payload["policies"][0]["local_file"] = "../outside.pdf"
    with pytest.raises(PolicyRegistryError, match="data/policies"):
        parse_policy_registry(payload)

    missing = copy.deepcopy(registry.get("GOV-SDI-PERPRES-39-2019"))
    object.__setattr__(missing, "local_file", "data/policies/missing.pdf")
    with pytest.raises(PolicyRegistryError, match="File policy tidak ditemukan"):
        resolve_policy_file(missing, repository_root=tmp_path)


def test_registry_snapshot_and_fingerprint_are_deterministic_and_json_safe() -> None:
    first = _payload()
    second = _payload()
    second["policies"].reverse()

    first_registry = parse_policy_registry(first)
    second_registry = parse_policy_registry(second)

    assert first_registry.canonical_snapshot() == second_registry.canonical_snapshot()
    assert first_registry.fingerprint() == second_registry.fingerprint()
    serialized = json.dumps(first_registry.to_dict(), ensure_ascii=False)
    assert json.loads(serialized)["schema_version"] == "1.0"
