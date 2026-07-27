import json

from core.metadata_validator import METADATA_FIELDS, validate_metadata


def complete_metadata() -> dict[str, str]:
    return {field: f"Nilai {field} yang cukup" for field in METADATA_FIELDS}


def test_complete_metadata():
    result = validate_metadata(complete_metadata())
    assert result["completeness_score"] == 100
    assert result["status"] == "Lengkap"
    assert result["missing_fields"] == []
    json.dumps(result)


def test_empty_and_whitespace_metadata():
    result = validate_metadata({field: "   " for field in METADATA_FIELDS})
    assert result["completeness_score"] == 0
    assert result["status"] == "Belum Lengkap"
    assert len(result["missing_fields"]) == len(METADATA_FIELDS)


def test_short_title_and_description():
    metadata = complete_metadata()
    metadata["title"] = "Abc"
    metadata["description"] = "Terlalu singkat"
    findings = validate_metadata(metadata)["findings"]
    assert {item["field"] for item in findings} == {"title", "description"}


def test_score_and_status_thresholds():
    metadata = complete_metadata()
    metadata["title"] = ""
    assert validate_metadata(metadata)["status"] == "Cukup Lengkap"
    metadata["title"] = "Judul valid"
    metadata["description"] = ""
    result = validate_metadata(metadata)
    assert 0 <= result["completeness_score"] <= 100
    assert result["status"] == "Cukup Lengkap"
