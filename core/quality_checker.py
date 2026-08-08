"""Deterministic data-quality checks."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_numeric_dtype,
    is_object_dtype,
    is_string_dtype,
)
from core.evidence_sanitizer import sanitize_evidence

SEVERITIES = {
    "info",
    "low",
    "medium",
    "high",
}

IDENTIFIER_NAMES = {
    "id",
    "identifier",
}

PERCENTAGE_KEYWORDS = {
    "percentage",
    "percent",
    "persentase",
    "persen",
}

DATE_KEYWORDS = {
    "date",
    "tanggal",
    "tgl",
}

COORDINATE_COLUMN_NAMES = {
    "latitude",
    "longitude",
    "lat",
    "lon",
    "lng",
}


def _finding(
    check_id: str,
    title: str,
    description: str,
    severity: str,
    column: str | None,
    count: int,
    percentage: float,
    evidence: list[Any],
    recommendation: str,
) -> dict[str, Any]:
    """Build a standardized JSON-safe quality finding."""
    if severity not in SEVERITIES:
        raise ValueError(
            f"Severity tidak dikenal: {severity}"
        )

    safe_evidence = sanitize_evidence(evidence)

    return {
        "check_id": check_id,
        "title": title,
        "description": description,
        "severity": severity,
        "column": column,
        "count": int(count),
        "percentage": float(percentage),
        "evidence": safe_evidence,
        "recommendation": recommendation,
    }


def _percentage(
    count: int,
    rows: int,
) -> float:
    """Calculate a safe percentage."""
    if rows == 0:
        return 0.0

    return count / rows * 100


def _normalized_column_name(
    column_name: str,
) -> str:
    """Normalize a column name for deterministic rule matching."""
    return re.sub(
        r"[^a-z0-9]+",
        "_",
        column_name.strip().casefold(),
    ).strip("_")


def _is_identifier_column(
    column_name: str,
) -> bool:
    """Return whether a column name likely represents an identifier."""
    normalized = _normalized_column_name(
        column_name
    )

    return (
        normalized in IDENTIFIER_NAMES
        or normalized.startswith("id_")
        or normalized.endswith("_id")
    )


def _is_percentage_column(
    column_name: str,
) -> bool:
    """Return whether a column name likely stores percentages."""
    normalized = _normalized_column_name(
        column_name
    )

    return any(
        keyword in normalized
        for keyword in PERCENTAGE_KEYWORDS
    )


def _is_date_column(
    column_name: str,
) -> bool:
    """Return whether a column name likely stores dates."""
    normalized = _normalized_column_name(
        column_name
    )

    return any(
        keyword in normalized
        for keyword in DATE_KEYWORDS
    )


def _is_coordinate_column(
    column_name: str,
) -> bool:
    """Return whether a column is an explicitly named coordinate field.

    Negative values are valid for latitude and longitude, so these exact
    normalized names are excluded from the generic negative-number rule.
    """
    return (
        _normalized_column_name(column_name)
        in COORDINATE_COLUMN_NAMES
    )


def _classify_date_format(
    value: str,
) -> str:
    """Classify supported textual date formats."""
    stripped = value.strip()

    if re.fullmatch(
        r"\d{4}-\d{2}-\d{2}",
        stripped,
    ):
        return "YYYY-MM-DD"

    if re.fullmatch(
        r"\d{2}/\d{2}/\d{4}",
        stripped,
    ):
        return "DD/MM/YYYY"

    if re.fullmatch(
        r"\d{4}/\d{2}/\d{2}",
        stripped,
    ):
        return "YYYY/MM/DD"

    return "unknown"


def _is_valid_date(
    value: str,
    date_format: str,
) -> bool:
    """Validate a date value using its classified format."""
    format_mapping = {
        "YYYY-MM-DD": "%Y-%m-%d",
        "DD/MM/YYYY": "%d/%m/%Y",
        "YYYY/MM/DD": "%Y/%m/%d",
    }

    python_format = format_mapping.get(
        date_format
    )

    if python_format is None:
        return False

    try:
        datetime.strptime(
            value.strip(),
            python_format,
        )
    except ValueError:
        return False

    return True


def _check_text_column(
    series: pd.Series,
    column_name: str,
    rows: int,
) -> list[dict[str, Any]]:
    """Run deterministic checks for text-like columns."""
    findings: list[dict[str, Any]] = []

    text = series.dropna().astype(str)

    whitespace = text[
        text != text.str.strip()
    ]

    if len(whitespace):
        findings.append(
            _finding(
                check_id="whitespace",
                title="Whitespace pada teks",
                description=(
                    f"Kolom {column_name} memiliki "
                    "spasi di awal/akhir."
                ),
                severity="low",
                column=column_name,
                count=len(whitespace),
                percentage=_percentage(
                    len(whitespace),
                    rows,
                ),
                evidence=whitespace.tolist(),
                recommendation=(
                    "Normalisasi whitespace bila sesuai konteks."
                ),
            )
        )

    empty = text[
        text.str.strip() == ""
    ]

    if len(empty):
        findings.append(
            _finding(
                check_id="empty_strings",
                title="String kosong",
                description=(
                    f"Kolom {column_name} memiliki "
                    "string kosong setelah trim."
                ),
                severity="medium",
                column=column_name,
                count=len(empty),
                percentage=_percentage(
                    len(empty),
                    rows,
                ),
                evidence=empty.tolist(),
                recommendation=(
                    "Tinjau string kosong sebagai missing."
                ),
            )
        )

    normalized = (
        text.str.strip()
        .str.casefold()
    )

    if (
        len(text)
        and normalized.nunique()
        < text.nunique()
    ):
        variation_count = int(
            text.nunique()
            - normalized.nunique()
        )

        findings.append(
            _finding(
                check_id="category_variation",
                title="Variasi kategori",
                description=(
                    f"Kolom {column_name} memiliki variasi "
                    "kapitalisasi atau spasi."
                ),
                severity="low",
                column=column_name,
                count=variation_count,
                percentage=_percentage(
                    variation_count,
                    rows,
                ),
                evidence=text.tolist(),
                recommendation=(
                    "Standarkan kapitalisasi dan penulisan kategori."
                ),
            )
        )

    return findings


def _check_identifier_column(
    series: pd.Series,
    column_name: str,
    rows: int,
) -> list[dict[str, Any]]:
    """Detect duplicated values in likely identifier columns."""
    non_null = series.dropna()

    if non_null.empty:
        return []

    normalized = (
        non_null.astype(str)
        .str.strip()
        .str.casefold()
    )

    duplicate_mask = normalized.duplicated(
        keep=False
    )

    duplicated_values = normalized[
        duplicate_mask
    ]

    if duplicated_values.empty:
        return []

    evidence = (
        non_null.loc[
            duplicated_values.index
        ]
        .astype(str)
        .drop_duplicates()
        .tolist()
    )

    return [
        _finding(
            check_id="duplicate_identifier",
            title="Identifier duplikat",
            description=(
                f"Kolom identifier {column_name} memiliki "
                "nilai yang digunakan pada lebih dari satu baris."
            ),
            severity="high",
            column=column_name,
            count=len(duplicated_values),
            percentage=_percentage(
                len(duplicated_values),
                rows,
            ),
            evidence=evidence,
            recommendation=(
                "Pastikan setiap identifier unik atau "
                "dokumentasikan aturan penggunaan identifier."
            ),
        )
    ]


def _check_date_column(
    series: pd.Series,
    column_name: str,
    rows: int,
) -> list[dict[str, Any]]:
    """Detect invalid dates and inconsistent textual date formats."""
    findings: list[dict[str, Any]] = []

    text = (
        series.dropna()
        .astype(str)
        .str.strip()
    )

    text = text[
        text != ""
    ]

    if text.empty:
        return findings

    formats = text.map(
        _classify_date_format
    )

    validity = pd.Series(
        [
            _is_valid_date(
                value=value,
                date_format=date_format,
            )
            for value, date_format in zip(
                text.tolist(),
                formats.tolist(),
                strict=True,
            )
        ],
        index=text.index,
        dtype=bool,
    )

    invalid_values = text[
        ~validity
    ]

    if len(invalid_values):
        findings.append(
            _finding(
                check_id="invalid_date",
                title="Tanggal tidak valid",
                description=(
                    f"Kolom {column_name} memiliki tanggal "
                    "yang tidak valid atau format tidak dikenali."
                ),
                severity="medium",
                column=column_name,
                count=len(invalid_values),
                percentage=_percentage(
                    len(invalid_values),
                    rows,
                ),
                evidence=invalid_values.tolist(),
                recommendation=(
                    "Gunakan tanggal kalender yang valid "
                    "dengan format YYYY-MM-DD."
                ),
            )
        )

    valid_formats = formats[
        validity
    ]

    recognized_formats = {
        value
        for value in valid_formats.tolist()
        if value != "unknown"
    }

    if len(recognized_formats) > 1:
        findings.append(
            _finding(
                check_id="inconsistent_date_format",
                title="Format tanggal tidak konsisten",
                description=(
                    f"Kolom {column_name} menggunakan "
                    "lebih dari satu format tanggal."
                ),
                severity="low",
                column=column_name,
                count=len(recognized_formats),
                percentage=0.0,
                evidence=sorted(
                    recognized_formats
                ),
                recommendation=(
                    "Standarkan seluruh tanggal menggunakan "
                    "format ISO YYYY-MM-DD."
                ),
            )
        )

    return findings


def _check_numeric_column(
    series: pd.Series,
    column_name: str,
    rows: int,
) -> list[dict[str, Any]]:
    """Run deterministic validity and outlier checks for numeric columns."""
    findings: list[dict[str, Any]] = []

    if is_bool_dtype(series):
        return findings

    numeric = pd.to_numeric(
        series,
        errors="coerce",
    ).dropna()

    if numeric.empty:
        return findings

    negative = numeric[
        numeric < 0
    ]

    if len(negative) and not _is_coordinate_column(column_name):
        findings.append(
            _finding(
                check_id="negative_numeric",
                title="Nilai numerik negatif",
                description=(
                    f"Kolom {column_name} memiliki nilai negatif "
                    "yang perlu diperiksa berdasarkan konteks data."
                ),
                severity="high",
                column=column_name,
                count=len(negative),
                percentage=_percentage(
                    len(negative),
                    rows,
                ),
                evidence=negative.tolist(),
                recommendation=(
                    "Periksa sumber data dan koreksi nilai negatif "
                    "yang tidak sesuai dengan definisi variabel."
                ),
            )
        )

    if _is_percentage_column(
        column_name
    ):
        outside_range = numeric[
            (numeric < 0)
            | (numeric > 100)
        ]

        if len(outside_range):
            findings.append(
                _finding(
                    check_id="percentage_out_of_range",
                    title="Persentase di luar rentang",
                    description=(
                        f"Kolom {column_name} memiliki nilai "
                        "persentase di luar rentang 0–100."
                    ),
                    severity="high",
                    column=column_name,
                    count=len(outside_range),
                    percentage=_percentage(
                        len(outside_range),
                        rows,
                    ),
                    evidence=outside_range.tolist(),
                    recommendation=(
                        "Pastikan nilai persentase berada "
                        "dalam rentang 0 sampai 100."
                    ),
                )
            )

    if len(numeric) < 5:
        return findings

    first_quartile = float(
        numeric.quantile(0.25)
    )
    third_quartile = float(
        numeric.quantile(0.75)
    )
    interquartile_range = (
        third_quartile
        - first_quartile
    )

    if interquartile_range <= 0:
        return findings

    lower_bound = (
        first_quartile
        - 1.5 * interquartile_range
    )
    upper_bound = (
        third_quartile
        + 1.5 * interquartile_range
    )

    outliers = numeric[
        (numeric < lower_bound)
        | (numeric > upper_bound)
    ]

    if len(outliers):
        findings.append(
            _finding(
                check_id="numeric_outlier",
                title="Outlier numerik",
                description=(
                    f"Kolom {column_name} memiliki nilai "
                    "di luar batas IQR "
                    f"({lower_bound:.2f}–{upper_bound:.2f})."
                ),
                severity="medium",
                column=column_name,
                count=len(outliers),
                percentage=_percentage(
                    len(outliers),
                    rows,
                ),
                evidence=outliers.tolist(),
                recommendation=(
                    "Verifikasi nilai outlier terhadap sumber data "
                    "dan konteks operasional."
                ),
            )
        )

    return findings


def run_quality_checks(
    dataframe: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Run deterministic checks and return JSON-safe findings."""
    findings: list[dict[str, Any]] = []
    rows = len(dataframe)

    for index in range(
        dataframe.shape[1]
    ):
        series = dataframe.iloc[
            :,
            index,
        ]
        column_name = str(
            dataframe.columns[index]
        )

        missing = int(
            series.isna().sum()
        )

        if missing:
            findings.append(
                _finding(
                    check_id="missing_values",
                    title="Missing values",
                    description=(
                        f"Kolom {column_name} memiliki "
                        "nilai kosong."
                    ),
                    severity="medium",
                    column=column_name,
                    count=missing,
                    percentage=_percentage(
                        missing,
                        rows,
                    ),
                    evidence=[],
                    recommendation=(
                        "Tinjau penanganan nilai kosong."
                    ),
                )
            )

        is_text = (
            is_object_dtype(series)
            or is_string_dtype(series)
            or isinstance(
                series.dtype,
                pd.CategoricalDtype,
            )
        )

        if is_text:
            findings.extend(
                _check_text_column(
                    series=series,
                    column_name=column_name,
                    rows=rows,
                )
            )

        if _is_identifier_column(
            column_name
        ):
            findings.extend(
                _check_identifier_column(
                    series=series,
                    column_name=column_name,
                    rows=rows,
                )
            )

        if _is_date_column(
            column_name
        ):
            findings.extend(
                _check_date_column(
                    series=series,
                    column_name=column_name,
                    rows=rows,
                )
            )

        if is_numeric_dtype(
            series
        ):
            findings.extend(
                _check_numeric_column(
                    series=series,
                    column_name=column_name,
                    rows=rows,
                )
            )

        non_null = series.dropna()

        if (
            len(non_null) > 0
            and series.nunique(
                dropna=True
            ) == 1
        ):
            findings.append(
                _finding(
                    check_id="constant_column",
                    title="Nilai konstan",
                    description=(
                        f"Kolom {column_name} hanya memiliki "
                        "satu nilai unik non-null."
                    ),
                    severity="info",
                    column=column_name,
                    count=len(non_null),
                    percentage=100.0,
                    evidence=[
                        non_null.iloc[0]
                    ],
                    recommendation=(
                        "Pastikan kolom konstan diperlukan."
                    ),
                )
            )

        if series.isna().all():
            findings.append(
                _finding(
                    check_id="empty_column",
                    title="Kolom seluruhnya kosong",
                    description=(
                        f"Kolom {column_name} seluruh "
                        "nilainya kosong."
                    ),
                    severity="high",
                    column=column_name,
                    count=rows,
                    percentage=100.0,
                    evidence=[],
                    recommendation=(
                        "Isi atau dokumentasikan kolom tersebut."
                    ),
                )
            )

    duplicate_rows = int(
        dataframe.duplicated().sum()
    )

    if duplicate_rows:
        findings.append(
            _finding(
                check_id="duplicate_rows",
                title="Baris duplikat",
                description=(
                    "Dataset memiliki baris duplikat."
                ),
                severity="medium",
                column=None,
                count=duplicate_rows,
                percentage=_percentage(
                    duplicate_rows,
                    rows,
                ),
                evidence=[],
                recommendation=(
                    "Tinjau dan hapus duplikasi yang "
                    "tidak diperlukan."
                ),
            )
        )

    if dataframe.columns.duplicated().any():
        duplicated_names = [
            str(column)
            for column, duplicated
            in zip(
                dataframe.columns,
                dataframe.columns.duplicated(),
                strict=True,
            )
            if duplicated
        ]

        findings.append(
            _finding(
                check_id="duplicate_columns",
                title="Nama kolom duplikat",
                description=(
                    "Terdapat nama kolom yang berulang."
                ),
                severity="high",
                column=None,
                count=len(
                    duplicated_names
                ),
                percentage=0.0,
                evidence=duplicated_names,
                recommendation=(
                    "Beri nama unik untuk setiap kolom."
                ),
            )
        )

    return findings
