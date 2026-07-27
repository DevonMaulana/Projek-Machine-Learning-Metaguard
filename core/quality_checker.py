"""Deterministic data-quality checks."""

from __future__ import annotations

from typing import Any

import pandas as pd
from pandas.api.types import is_object_dtype, is_string_dtype

SEVERITIES = {"info", "low", "medium", "high"}


def _finding(check_id: str, title: str, description: str, severity: str,
             column: str | None, count: int, percentage: float,
             evidence: list[Any], recommendation: str) -> dict[str, Any]:
    if severity not in SEVERITIES:
        raise ValueError(f"Severity tidak dikenal: {severity}")
    return {"check_id": check_id, "title": title, "description": description,
            "severity": severity, "column": column, "count": int(count),
            "percentage": float(percentage), "evidence": evidence[:5],
            "recommendation": recommendation}


def run_quality_checks(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    """Run lightweight deterministic checks and return JSON-safe findings."""
    findings: list[dict[str, Any]] = []
    rows = len(dataframe)
    for index in range(dataframe.shape[1]):
        series = dataframe.iloc[:, index]
        name = str(dataframe.columns[index])
        missing = int(series.isna().sum())
        if missing:
            findings.append(_finding("missing_values", "Missing values", f"Kolom {name} memiliki nilai kosong.", "medium", name, missing, missing / rows * 100 if rows else 0, [], "Tinjau penanganan nilai kosong."))
        is_text = is_object_dtype(series) or is_string_dtype(series) or isinstance(series.dtype, pd.CategoricalDtype)
        if is_text:
            text = series.dropna().astype(str)
            whitespace = text[text != text.str.strip()]
            if len(whitespace):
                findings.append(_finding("whitespace", "Whitespace pada teks", f"Kolom {name} memiliki spasi di awal/akhir.", "low", name, len(whitespace), len(whitespace) / rows * 100 if rows else 0, whitespace.tolist(), "Normalisasi whitespace bila sesuai konteks."))
            empty = text[text.str.strip() == ""]
            if len(empty):
                findings.append(_finding("empty_strings", "String kosong", f"Kolom {name} memiliki string kosong setelah trim.", "medium", name, len(empty), len(empty) / rows * 100 if rows else 0, empty.tolist(), "Tinjau string kosong sebagai missing."))
            normalized = text.str.strip().str.casefold()
            if len(text) and normalized.nunique() < text.nunique():
                findings.append(_finding("category_variation", "Variasi kategori", f"Kolom {name} memiliki variasi kapitalisasi atau spasi.", "low", name, int(text.nunique() - normalized.nunique()), 0.0, text.tolist(), "Standarkan kategori."))
        non_null = series.dropna()
        if len(non_null) > 0 and series.nunique(dropna=True) == 1:
            findings.append(_finding("constant_column", "Nilai konstan", f"Kolom {name} hanya memiliki satu nilai unik non-null.", "info", name, int(len(non_null)), 100.0, [str(non_null.iloc[0])], "Pastikan kolom konstan diperlukan."))
        if series.isna().all():
            findings.append(_finding("empty_column", "Kolom seluruhnya kosong", f"Kolom {name} seluruh nilainya kosong.", "high", name, rows, 100.0, [], "Isi atau dokumentasikan kolom tersebut."))
    duplicate = int(dataframe.duplicated().sum())
    if duplicate:
        findings.append(_finding("duplicate_rows", "Baris duplikat", "Dataset memiliki baris duplikat.", "medium", None, duplicate, duplicate / rows * 100 if rows else 0, [], "Tinjau duplikasi."))
    if dataframe.columns.duplicated().any():
        duplicated_names = [str(c) for c, flag in zip(dataframe.columns, dataframe.columns.duplicated()) if flag]
        findings.append(_finding("duplicate_columns", "Nama kolom duplikat", "Terdapat nama kolom yang berulang.", "high", None, len(duplicated_names), 0.0, duplicated_names, "Beri nama kolom unik."))
    return findings
