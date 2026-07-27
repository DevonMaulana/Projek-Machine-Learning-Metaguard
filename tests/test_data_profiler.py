import copy
import json

import pandas as pd

from core.data_profiler import profile_dataframe


def test_profile_is_complete_json_safe_and_non_mutating():
    frame = pd.DataFrame({"name": ["A", None, "A"], "empty": [None, None, None]})
    before = copy.deepcopy(frame)
    result = profile_dataframe(frame)
    assert result["row_count"] == 3
    assert result["duplicate_rows"] == 1
    assert result["fully_empty_columns"] == ["empty"]
    assert result["column_details"][0]["missing_values"] == 1
    json.dumps(result)
    pd.testing.assert_frame_equal(frame, before)


def test_profile_empty_dataframe_is_valid():
    result = profile_dataframe(pd.DataFrame(columns=["a"]))
    assert result["row_count"] == 0
    assert result["sample_rows"] == []


def test_profile_duplicate_columns_preserves_all_positions():
    frame = pd.DataFrame([[1, 2]], columns=["value", "value"])
    result = profile_dataframe(frame)
    assert result["column_count"] == 2
    assert len(result["column_details"]) == 2
    json.dumps(result)
