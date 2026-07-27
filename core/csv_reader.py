"""CSV reading utilities for MetaGuard."""

from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError, ParserError


class CsvReadError(Exception):
    """Raised when MetaGuard cannot read a CSV dataset."""


def read_csv_file(
    file_path: str | Path,
    *,
    encoding: str = "utf-8",
    delimiter: str = ",",
) -> pd.DataFrame:
    """Read a single CSV file into a pandas DataFrame.

    Args:
        file_path: Path to one CSV file.
        encoding: Text encoding used to decode the file.
        delimiter: Field delimiter used by the CSV file.

    Returns:
        Parsed CSV content as a pandas DataFrame.

    Raises:
        CsvReadError: If the path is invalid or Pandas cannot read the CSV.
    """

    path = Path(file_path)

    if not path.exists():
        raise CsvReadError(f"File CSV tidak ditemukan: {path}")

    if not path.is_file():
        raise CsvReadError(f"Path bukan file CSV: {path}")

    if path.suffix.lower() != ".csv":
        raise CsvReadError(f"Ekstensi file harus .csv: {path}")

    try:
        return pd.read_csv(path, encoding=encoding, sep=delimiter)
    except EmptyDataError as exc:
        raise CsvReadError(f"File CSV kosong: {path}") from exc
    except ParserError as exc:
        raise CsvReadError(f"CSV gagal diparsing: {path}") from exc
    except UnicodeDecodeError as exc:
        raise CsvReadError(
            f"Encoding tidak sesuai untuk membaca file CSV: {encoding}"
        ) from exc
