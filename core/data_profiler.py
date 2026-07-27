"""Deterministic, JSON-safe profiling for pandas DataFrames."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd


def _json_value(value: Any) -> Any:
    """Convert common pandas/scalar values to JSON-safe values."""
    missing = pd.isna(value)
    if isinstance(missing, bool) and missing:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def profile_dataframe(dataframe: pd.DataFrame) -> dict[str, Any]:
    """Return a compact JSON-serializable profile without mutating the input."""
    row_count, column_count = dataframe.shape
    details: list[dict[str, Any]] = []
    for position in range(column_count):
        name = dataframe.columns[position]
        series = dataframe.iloc[:, position]
        missing = int(series.isna().sum())
        details.append({
            "position": position,
            "name": str(name),
            "dtype": str(series.dtype),
            "missing_values": missing,
            "missing_percentage": missing / row_count * 100 if row_count else 0.0,
            "unique_values": int(series.nunique(dropna=True)),
            "fully_empty": bool(series.isna().all()),
        })
    samples = []
    for _, row in dataframe.head(5).iterrows():
        sample: dict[str, Any] = {}
        for position, value in enumerate(row.tolist()):
            sample[f"{position}:{dataframe.columns[position]}"] = _json_value(value)
        samples.append(sample)
    return {
        "row_count": int(row_count), "column_count": int(column_count),
        "columns": [str(column) for column in dataframe.columns],
        "column_details": details,
        "dtypes": [item["dtype"] for item in details],
        "missing_values": [item["missing_values"] for item in details],
        "missing_percentages": [item["missing_percentage"] for item in details],
        "unique_values": [item["unique_values"] for item in details],
        "duplicate_rows": int(dataframe.duplicated().sum()),
        "fully_empty_columns": [item["name"] for item in details if item["fully_empty"]],
        "sample_rows": samples,
    }
