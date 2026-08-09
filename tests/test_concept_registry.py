import copy
import json

import pandas as pd
import pytest

from core.concept_registry import (
    CONCEPT_REGISTRY_PATH,
    ConceptRegistryError,
    load_concept_registry,
    map_dataframe_columns,
    normalize_column_name,
    parse_concept_registry,
    resolve_concept,
)


def _payload() -> dict:
    return json.loads(CONCEPT_REGISTRY_PATH.read_text(encoding="utf-8"))


def test_registry_loads_stable_initial_concept_ids() -> None:
    registry = load_concept_registry()

    assert {concept.concept_id for concept in registry.concepts} == {
        "occupied_beds",
        "inpatient_capacity",
        "internet_status",
        "bandwidth_mbps",
        "student_count",
        "teacher_count",
        "classroom_count",
        "attendance_percentage",
        "ph_measurement",
        "sensor_status",
        "measurement_date",
        "pm25_measurement",
        "pm10_measurement",
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" Jumlah Siswa ", "jumlah_siswa"),
        ("jumlah_siswa", "jumlah_siswa"),
        ("JUMLAH SISWA", "jumlah_siswa"),
        ("PM-25", "pm_25"),
        ("tanggal///pengukuran", "tanggal_pengukuran"),
    ],
)
def test_column_normalization_is_conservative_and_deterministic(
    raw: str,
    expected: str,
) -> None:
    assert normalize_column_name(raw) == expected


def test_healthcare_exact_concept_mappings() -> None:
    registry = load_concept_registry()

    assert registry.resolve("tempat_tidur_terisi", "healthcare").concept_id == (
        "occupied_beds"
    )
    assert registry.resolve("kapasitas_rawat_inap", "healthcare").concept_id == (
        "inpatient_capacity"
    )
    assert registry.resolve("status_internet", "healthcare").concept_id == (
        "internet_status"
    )
    assert registry.resolve("bandwidth_mbps", "healthcare").concept_id == (
        "bandwidth_mbps"
    )


def test_education_and_environment_pilot_concept_mappings() -> None:
    registry = load_concept_registry()

    assert registry.resolve("Jumlah Siswa", "education").concept_id == "student_count"
    assert registry.resolve("jml_guru", "education").concept_id == "teacher_count"
    assert registry.resolve("total_kelas", "education").concept_id == "classroom_count"
    assert registry.resolve("persentase_kehadiran", "education").concept_id == (
        "attendance_percentage"
    )
    assert registry.resolve("ph_air", "environment").concept_id == "ph_measurement"
    assert registry.resolve("status_sensor", "environment").concept_id == "sensor_status"
    assert registry.resolve("tanggal_pengukuran", "environment").concept_id == (
        "measurement_date"
    )
    assert registry.resolve("pm_25", "environment").concept_id == "pm25_measurement"
    assert registry.resolve("pm10", "environment").concept_id == "pm10_measurement"


def test_resolution_is_exact_and_does_not_leak_across_domains() -> None:
    registry = load_concept_registry()

    exact = resolve_concept("Jumlah Siswa", "education", registry)
    assert exact.normalized_column == "jumlah_siswa"
    assert exact.concept_id == "student_count"
    assert exact.matched_alias == "jumlah_siswa"

    substring = resolve_concept("jumlah_siswa_lama", "education", registry)
    assert substring.concept_id is None
    assert substring.matched_alias is None

    cross_domain = resolve_concept("status_sensor", "healthcare", registry)
    assert cross_domain.concept_id is None
    assert cross_domain.domain_id.value == "healthcare"


def test_unknown_columns_and_dataframe_column_mapping_are_safe_and_non_mutating() -> None:
    registry = load_concept_registry()
    dataframe = pd.DataFrame(columns=["Jumlah Siswa", "jumlah_siswa", "Unknown Column"])
    original_columns = dataframe.columns.copy()

    resolutions = map_dataframe_columns(dataframe.columns, "education", registry)

    assert dataframe.columns.equals(original_columns)
    assert [resolution.column for resolution in resolutions] == [
        "Jumlah Siswa",
        "jumlah_siswa",
        "Unknown Column",
    ]
    assert [resolution.concept_id for resolution in resolutions] == [
        "student_count",
        "student_count",
        None,
    ]
    assert [resolution.is_duplicate_normalized_column for resolution in resolutions] == [
        True,
        True,
        False,
    ]
    assert json.loads(json.dumps([item.to_dict() for item in resolutions]))[2][
        "concept_id"
    ] is None


def test_registry_rejects_duplicate_ids_missing_fields_and_unknown_fields() -> None:
    duplicate = _payload()
    duplicate["concepts"][1]["concept_id"] = duplicate["concepts"][0]["concept_id"]
    with pytest.raises(ConceptRegistryError, match="concept_id tidak boleh duplikat"):
        parse_concept_registry(duplicate)

    missing = _payload()
    del missing["concepts"][0]["canonical_name"]
    with pytest.raises(ConceptRegistryError, match="canonical_name"):
        parse_concept_registry(missing)

    unknown = _payload()
    unknown["concepts"][0]["callable"] = "do_not_execute"
    with pytest.raises(ConceptRegistryError, match="tidak didukung"):
        parse_concept_registry(unknown)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("concept_id", " ", "concept_id"),
        ("domain_id", "unknown_domain", "Domain tidak didukung"),
        ("aliases", [], "aliases harus berupa list"),
        ("aliases", "not-a-list", "aliases harus berupa list"),
        ("expected_data_type", "arbitrary", "expected_data_type tidak didukung"),
    ],
)
def test_registry_rejects_malformed_controlled_values(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = _payload()
    payload["concepts"][0][field] = value

    with pytest.raises(ConceptRegistryError, match=message):
        parse_concept_registry(payload)


def test_registry_rejects_normalized_duplicate_aliases_and_domain_collisions() -> None:
    duplicate_alias = _payload()
    duplicate_alias["concepts"][4]["aliases"] = ["jumlah_siswa", "Jumlah Siswa"]
    with pytest.raises(ConceptRegistryError, match="duplikat setelah normalisasi"):
        parse_concept_registry(duplicate_alias)

    collision = _payload()
    collision["concepts"][5]["aliases"].append("Jumlah Siswa")
    with pytest.raises(ConceptRegistryError, match="collision pada domain"):
        parse_concept_registry(collision)


def test_cross_domain_alias_reuse_is_allowed_when_selected_domain_disambiguates() -> None:
    payload = _payload()
    environment_copy = copy.deepcopy(payload["concepts"][9])
    environment_copy["concept_id"] = "environment_status"
    environment_copy["canonical_name"] = "status"
    environment_copy["aliases"] = ["status"]
    payload["concepts"].append(environment_copy)
    registry = parse_concept_registry(payload)

    assert registry.resolve("status", "environment").concept_id == "environment_status"
    assert registry.resolve("status", "healthcare").concept_id is None


def test_registry_snapshot_and_fingerprint_are_order_independent() -> None:
    first = _payload()
    second = _payload()
    second["concepts"].reverse()

    first_registry = parse_concept_registry(first)
    second_registry = parse_concept_registry(second)

    assert first_registry.canonical_snapshot() == second_registry.canonical_snapshot()
    assert first_registry.fingerprint() == second_registry.fingerprint()
    assert json.loads(json.dumps(first_registry.to_dict()))["schema_version"] == "1.0"
