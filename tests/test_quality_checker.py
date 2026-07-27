import copy
import json

import pandas as pd

import pytest

from core.quality_checker import SEVERITIES, _finding, run_quality_checks


def test_quality_checks_detect_expected_findings_and_do_not_mutate():
    frame = pd.DataFrame({"text": [" A", "a ", ""], "constant": ["x", None, None], "empty": [None, None, None]})
    before = copy.deepcopy(frame)
    findings = run_quality_checks(frame)
    ids = {item["check_id"] for item in findings}
    assert {"whitespace", "empty_strings", "category_variation", "constant_column", "empty_column"} <= ids
    assert all(item["severity"] in {"info", "low", "medium", "high"} for item in findings)
    json.dumps(findings)
    pd.testing.assert_frame_equal(frame, before)


def test_clean_data_has_no_findings():
    assert run_quality_checks(pd.DataFrame({"a": ["one", "two"], "b": [1, 2]})) == []


def test_constant_column_requires_one_unique_non_null_value():
    repeated = run_quality_checks(pd.DataFrame({"a": ["x", "x", "x"]}))
    empty = run_quality_checks(pd.DataFrame({"a": [None, None]}))
    varied = run_quality_checks(pd.DataFrame({"a": ["x", "y"]}))
    assert any(item["check_id"] == "constant_column" for item in repeated)
    assert not any(item["check_id"] == "constant_column" for item in empty)
    assert not any(item["check_id"] == "constant_column" for item in varied)


def test_numeric_column_has_no_text_findings():
    findings = run_quality_checks(pd.DataFrame({"number": [1, 2, 3]}))
    assert not {item["check_id"] for item in findings} & {"whitespace", "empty_strings", "category_variation"}


def test_duplicate_columns_are_supported():
    findings = run_quality_checks(pd.DataFrame([[1, 2]], columns=["value", "value"]))
    assert any(item["check_id"] == "duplicate_columns" for item in findings)


def test_invalid_severity_is_rejected():
    assert SEVERITIES == {"info", "low", "medium", "high"}
    with pytest.raises(ValueError):
        _finding("x", "x", "x", "critical", None, 1, 1, [], "x")
