from pathlib import Path

import pytest

from core.csv_reader import CsvReadError, read_csv_file


def test_read_csv_file_reads_valid_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "valid.csv"
    csv_path.write_text("name,score\nalpha,10\nbeta,20\n", encoding="utf-8")

    result = read_csv_file(csv_path)

    assert list(result.columns) == ["name", "score"]
    assert result.to_dict("records") == [
        {"name": "alpha", "score": 10},
        {"name": "beta", "score": 20},
    ]


def test_read_csv_file_accepts_custom_delimiter(tmp_path: Path) -> None:
    csv_path = tmp_path / "semicolon.csv"
    csv_path.write_text("name;score\nalpha;10\n", encoding="utf-8")

    result = read_csv_file(csv_path, delimiter=";")

    assert result.to_dict("records") == [{"name": "alpha", "score": 10}]


def test_read_csv_file_raises_when_file_missing(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.csv"

    with pytest.raises(CsvReadError, match="tidak ditemukan"):
        read_csv_file(missing_path)


def test_read_csv_file_raises_when_path_is_not_file(tmp_path: Path) -> None:
    with pytest.raises(CsvReadError, match="bukan file"):
        read_csv_file(tmp_path)


def test_read_csv_file_raises_when_extension_is_not_csv(tmp_path: Path) -> None:
    txt_path = tmp_path / "dataset.txt"
    txt_path.write_text("name,score\nalpha,10\n", encoding="utf-8")

    with pytest.raises(CsvReadError, match="Ekstensi"):
        read_csv_file(txt_path)


def test_read_csv_file_raises_when_csv_is_empty(tmp_path: Path) -> None:
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("", encoding="utf-8")

    with pytest.raises(CsvReadError, match="kosong"):
        read_csv_file(csv_path)


def test_read_csv_file_raises_when_csv_cannot_be_parsed(tmp_path: Path) -> None:
    csv_path = tmp_path / "broken.csv"
    csv_path.write_text('name,score\n"alpha,10\nbeta,20\n', encoding="utf-8")

    with pytest.raises(CsvReadError, match="gagal diparsing"):
        read_csv_file(csv_path)


def test_read_csv_file_raises_when_encoding_does_not_match(tmp_path: Path) -> None:
    csv_path = tmp_path / "latin.csv"
    csv_path.write_bytes("nama,kota\nAndi,Yogyakarta\nBudi,Bandung\n".encode("utf-16"))

    with pytest.raises(CsvReadError, match="Encoding"):
        read_csv_file(csv_path, encoding="utf-8")
