import copy
import json

import pandas as pd
import pytest

from core.quality_checker import (
    SEVERITIES,
    _finding,
    run_quality_checks,
)


def _finding_ids(
    findings: list[dict],
) -> set[str]:
    return {
        item["check_id"]
        for item in findings
    }


def _find_by_id(
    findings: list[dict],
    check_id: str,
) -> dict:
    return next(
        item
        for item in findings
        if item["check_id"] == check_id
    )


def test_quality_checks_detect_expected_findings_and_do_not_mutate():
    frame = pd.DataFrame(
        {
            "text": [
                " A",
                "a ",
                "",
            ],
            "constant": [
                "x",
                None,
                None,
            ],
            "empty": [
                None,
                None,
                None,
            ],
        }
    )

    before = copy.deepcopy(frame)

    findings = run_quality_checks(
        frame
    )

    ids = _finding_ids(
        findings
    )

    assert {
        "whitespace",
        "empty_strings",
        "category_variation",
        "constant_column",
        "empty_column",
    } <= ids

    assert all(
        item["severity"]
        in {
            "info",
            "low",
            "medium",
            "high",
        }
        for item in findings
    )

    json.dumps(
        findings
    )

    pd.testing.assert_frame_equal(
        frame,
        before,
    )


def test_clean_data_has_no_findings():
    frame = pd.DataFrame(
        {
            "name": [
                "one",
                "two",
            ],
            "value": [
                1,
                2,
            ],
        }
    )

    assert run_quality_checks(
        frame
    ) == []


def test_constant_column_requires_one_unique_non_null_value():
    repeated = run_quality_checks(
        pd.DataFrame(
            {
                "a": [
                    "x",
                    "x",
                    "x",
                ]
            }
        )
    )

    empty = run_quality_checks(
        pd.DataFrame(
            {
                "a": [
                    None,
                    None,
                ]
            }
        )
    )

    varied = run_quality_checks(
        pd.DataFrame(
            {
                "a": [
                    "x",
                    "y",
                ]
            }
        )
    )

    assert any(
        item["check_id"]
        == "constant_column"
        for item in repeated
    )

    assert not any(
        item["check_id"]
        == "constant_column"
        for item in empty
    )

    assert not any(
        item["check_id"]
        == "constant_column"
        for item in varied
    )


def test_numeric_column_has_no_text_findings():
    findings = run_quality_checks(
        pd.DataFrame(
            {
                "number": [
                    1,
                    2,
                    3,
                ]
            }
        )
    )

    assert not (
        _finding_ids(findings)
        & {
            "whitespace",
            "empty_strings",
            "category_variation",
        }
    )


def test_duplicate_columns_are_supported():
    findings = run_quality_checks(
        pd.DataFrame(
            [
                [
                    1,
                    2,
                ]
            ],
            columns=[
                "value",
                "value",
            ],
        )
    )

    assert (
        "duplicate_columns"
        in _finding_ids(findings)
    )


def test_invalid_severity_is_rejected():
    assert SEVERITIES == {
        "info",
        "low",
        "medium",
        "high",
    }

    with pytest.raises(
        ValueError
    ):
        _finding(
            "x",
            "x",
            "x",
            "critical",
            None,
            1,
            1,
            [],
            "x",
        )


def test_negative_numeric_values_are_detected():
    frame = pd.DataFrame(
        {
            "jumlah_dokter": [
                5,
                6,
                -1,
                7,
                8,
            ]
        }
    )

    findings = run_quality_checks(
        frame
    )

    finding = _find_by_id(
        findings,
        "negative_numeric",
    )

    assert finding["severity"] == "high"
    assert finding["count"] == 1
    assert finding["evidence"] == [-1]


def test_percentage_out_of_range_is_detected():
    frame = pd.DataFrame(
        {
            "persentase_imunisasi": [
                80.0,
                90.0,
                105.0,
                75.0,
                88.0,
            ]
        }
    )

    findings = run_quality_checks(
        frame
    )

    finding = _find_by_id(
        findings,
        "percentage_out_of_range",
    )

    assert finding["severity"] == "high"
    assert finding["count"] == 1
    assert finding["evidence"] == [105.0]


def test_valid_percentage_has_no_range_finding():
    frame = pd.DataFrame(
        {
            "persentase_imunisasi": [
                0,
                25,
                50,
                75,
                100,
            ]
        }
    )

    findings = run_quality_checks(
        frame
    )

    assert (
        "percentage_out_of_range"
        not in _finding_ids(findings)
    )


def test_invalid_date_is_detected():
    frame = pd.DataFrame(
        {
            "tanggal_pembaruan": [
                "2026-07-01",
                "2026-13-02",
                "2026-07-03",
            ]
        }
    )

    findings = run_quality_checks(
        frame
    )

    finding = _find_by_id(
        findings,
        "invalid_date",
    )

    assert finding["severity"] == "medium"
    assert finding["count"] == 1
    assert (
        "2026-13-02"
        in finding["evidence"]
    )


def test_inconsistent_date_format_is_detected():
    frame = pd.DataFrame(
        {
            "tanggal_pembaruan": [
                "2026-07-01",
                "31/07/2026",
                "2026/08/01",
            ]
        }
    )

    findings = run_quality_checks(
        frame
    )

    finding = _find_by_id(
        findings,
        "inconsistent_date_format",
    )

    assert finding["severity"] == "low"
    assert finding["count"] == 3

    assert set(
        finding["evidence"]
    ) == {
        "YYYY-MM-DD",
        "DD/MM/YYYY",
        "YYYY/MM/DD",
    }


def test_valid_iso_dates_have_no_date_findings():
    frame = pd.DataFrame(
        {
            "tanggal_pembaruan": [
                "2026-07-01",
                "2026-07-02",
                "2026-07-03",
            ]
        }
    )

    findings = run_quality_checks(
        frame
    )

    ids = _finding_ids(
        findings
    )

    assert "invalid_date" not in ids
    assert (
        "inconsistent_date_format"
        not in ids
    )


def test_duplicate_identifier_is_detected():
    frame = pd.DataFrame(
        {
            "id_puskesmas": [
                "PKM001",
                "PKM002",
                "PKM001",
                "PKM003",
            ],
            "nama": [
                "A",
                "B",
                "C",
                "D",
            ],
        }
    )

    findings = run_quality_checks(
        frame
    )

    finding = _find_by_id(
        findings,
        "duplicate_identifier",
    )

    assert finding["severity"] == "high"
    assert finding["count"] == 2
    assert "PKM001" in finding["evidence"]


def test_identifier_matching_normalizes_case_and_whitespace():
    frame = pd.DataFrame(
        {
            "kode_fasilitas": [
                "PKM001",
                " pkm001 ",
                "PKM002",
            ]
        }
    )

    findings = run_quality_checks(
        frame
    )

    finding = _find_by_id(
        findings,
        "duplicate_identifier",
    )

    assert finding["count"] == 2


def test_iqr_numeric_outlier_is_detected():
    frame = pd.DataFrame(
        {
            "jumlah_pasien": [
                100,
                105,
                110,
                115,
                120,
                5000,
            ]
        }
    )

    findings = run_quality_checks(
        frame
    )

    finding = _find_by_id(
        findings,
        "numeric_outlier",
    )

    assert finding["severity"] == "medium"
    assert finding["count"] == 1
    assert finding["evidence"] == [5000]


def test_small_numeric_sample_skips_outlier_check():
    frame = pd.DataFrame(
        {
            "jumlah_pasien": [
                100,
                105,
                5000,
                110,
            ]
        }
    )

    findings = run_quality_checks(
        frame
    )

    assert (
        "numeric_outlier"
        not in _finding_ids(findings)
    )


def test_boolean_column_skips_numeric_checks():
    frame = pd.DataFrame(
        {
            "aktif": [
                True,
                False,
                True,
                False,
                True,
            ]
        }
    )

    findings = run_quality_checks(
        frame
    )

    ids = _finding_ids(
        findings
    )

    assert "negative_numeric" not in ids
    assert (
        "percentage_out_of_range"
        not in ids
    )
    assert "numeric_outlier" not in ids


def test_advanced_findings_are_json_safe():
    frame = pd.DataFrame(
        {
            "id_puskesmas": [
                "PKM001",
                "PKM001",
                "PKM002",
                "PKM003",
                "PKM004",
                "PKM005",
            ],
            "persentase_imunisasi": [
                80.0,
                82.0,
                84.0,
                86.0,
                88.0,
                105.0,
            ],
            "tanggal_pembaruan": [
                "2026-07-01",
                "2026-07-02",
                "2026-07-03",
                "31/07/2026",
                "2026/08/01",
                "2026-13-02",
            ],
        }
    )

    findings = run_quality_checks(
        frame
    )

    encoded = json.dumps(
        findings,
        ensure_ascii=False,
    )

    assert "duplicate_identifier" in encoded
    assert "percentage_out_of_range" in encoded
    assert "invalid_date" in encoded