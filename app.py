"""Streamlit entry point for the local MetaGuard analysis pipeline."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from core.csv_reader import CsvReadError, read_csv_file
from core.data_profiler import profile_dataframe
from core.metadata_validator import validate_metadata
from core.quality_checker import run_quality_checks
from core.report_builder import build_report
from core.scoring import calculate_score


def _read_uploaded_csv(uploaded_file: st.runtime.uploaded_file_manager.UploadedFile) -> pd.DataFrame:
    """Read an uploaded CSV through the shared core CSV reader."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as temporary:
        temporary.write(uploaded_file.getvalue())
        temporary_path = Path(temporary.name)
    try:
        return read_csv_file(temporary_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _show_findings(findings: list[dict[str, object]]) -> None:
    """Render quality findings grouped by severity."""
    st.subheader("Hasil pemeriksaan kualitas")
    if not findings:
        st.success("Tidak ada temuan kualitas pada dataset.")
        return
    for severity in ("high", "medium", "low", "info"):
        grouped = [item for item in findings if item["severity"] == severity]
        if not grouped:
            continue
        st.markdown(f"**Severity: {severity} ({len(grouped)})**")
        for item in grouped:
            column = item["column"] or "Dataset"
            st.warning(
                f"{item['title']} — kolom: {column} — jumlah: {item['count']} "
                f"({item['percentage']:.2f}%)"
            ) if severity in {"high", "medium"} else st.info(
                f"{item['title']} — kolom: {column} — jumlah: {item['count']} "
                f"({item['percentage']:.2f}%)"
            )
            st.caption(f"{item['description']} Rekomendasi: {item['recommendation']}")


def main() -> None:
    """Render the MetaGuard local dataset analysis workflow."""
    st.set_page_config(page_title="MetaGuard", layout="wide")
    st.title("MetaGuard")
    st.write("Validasi awal kualitas dataset OPD secara lokal, deterministik, dan tanpa AI.")

    uploaded_file = st.file_uploader("Unggah satu file CSV", type=["csv"], accept_multiple_files=False)
    if uploaded_file is None:
        st.info("Unggah file CSV untuk memulai analisis.")
        return

    st.caption(f"File: {uploaded_file.name} · Ukuran: {len(uploaded_file.getvalue()):,} byte")
    try:
        dataframe = _read_uploaded_csv(uploaded_file)
    except CsvReadError as error:
        st.error(str(error))
        return
    except (OSError, ValueError) as error:
        st.error(f"File tidak dapat dibaca: {error}")
        return

    if dataframe.shape[1] == 0:
        st.error("Dataset tidak memiliki kolom.")
        return

    st.subheader("Preview dataset")
    st.dataframe(dataframe.head(10), hide_index=True)

    profile = profile_dataframe(dataframe)
    findings = run_quality_checks(dataframe)
    score = calculate_score(findings)

    st.subheader("Ringkasan profil")
    metrics = st.columns(4)
    metrics[0].metric("Jumlah baris", profile["row_count"])
    metrics[1].metric("Jumlah kolom", profile["column_count"])
    metrics[2].metric("Baris duplikat", profile["duplicate_rows"])
    metrics[3].metric("Kolom seluruhnya kosong", len(profile["fully_empty_columns"]))

    st.subheader("Informasi kolom")
    st.dataframe(pd.DataFrame(profile["column_details"]), hide_index=True)
    _show_findings(findings)

    st.subheader("Skor kualitas")
    st.metric("Score", score["score"])
    st.write(f"Grade: **{score['grade']}** · Total temuan: {score['total_findings']}")
    st.json(score["findings_by_severity"])

    st.subheader("Metadata dataset")
    with st.form("metadata_form"):
        title = st.text_input("Judul dataset")
        description = st.text_area("Deskripsi dataset")
        producer_opd = st.text_input("OPD produsen data")
        data_period = st.text_input("Periode data")
        geographic_scope = st.text_input("Cakupan wilayah")
        measurement_unit = st.text_input("Satuan pengukuran")
        update_frequency = st.selectbox("Frekuensi pembaruan", ["", "Harian", "Mingguan", "Bulanan", "Triwulanan", "Tahunan", "Lainnya"])
        responsible_unit = st.text_input("Penanggung jawab atau unit pengelola")
        publication_purpose = st.text_area("Tujuan publikasi")
        submitted = st.form_submit_button("Validasi metadata", type="primary")

    metadata = {
        "title": title, "description": description, "producer_opd": producer_opd,
        "data_period": data_period, "geographic_scope": geographic_scope,
        "measurement_unit": measurement_unit, "update_frequency": update_frequency,
        "responsible_unit": responsible_unit, "publication_purpose": publication_purpose,
    }
    metadata_validation = validate_metadata(metadata)
    if submitted or any(str(value).strip() for value in metadata.values()):
        st.metric("Skor kelengkapan metadata", f"{metadata_validation['completeness_score']:.2f}")
        st.write(f"Status: **{metadata_validation['status']}**")
        if metadata_validation["missing_fields"]:
            st.warning("Field belum lengkap: " + ", ".join(metadata_validation["missing_fields"]))
        for item in metadata_validation["findings"]:
            st.info(f"{item['field']}: {item['issue']} {item['recommendation']}")

    st.subheader("Laporan JSON")
    report = build_report(
        profile, findings, score,
        {"file_name": uploaded_file.name, "size_bytes": len(uploaded_file.getvalue())},
        metadata, metadata_validation,
    )
    st.download_button("Unduh laporan JSON", data=json.dumps(report, ensure_ascii=False, indent=2), file_name="metaguard_report.json", mime="application/json")


if __name__ == "__main__":
    main()
