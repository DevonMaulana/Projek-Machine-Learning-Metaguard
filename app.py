"""Streamlit entry point for the local MetaGuard analysis pipeline."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from core.analysis_state import build_analysis_fingerprint
from core.csv_ingestion import (
    CsvIngestionError,
    CsvIngestionResult,
    CsvReadConfig,
    read_csv_with_diagnostics,
)
from core.data_profiler import profile_dataframe
from core.evidence_reviewer import review_evidence_traceability
from core.metadata_validator import validate_metadata
from core.policy_evidence import build_policy_evidence, build_policy_queries
from core.quality_checker import run_quality_checks
from core.report_builder import build_report
from core.scoring import calculate_score
from llm.gemini_client import analyze_with_gemini
from rag.retriever import retrieve_policy_chunks


@st.cache_data(max_entries=5, show_spinner=False)
def _read_uploaded_csv(
    file_bytes: bytes,
    config: CsvReadConfig,
) -> CsvIngestionResult:
    """Read uploaded bytes through structured CSV ingestion."""
    with tempfile.NamedTemporaryFile(
        suffix=".csv",
        delete=False,
    ) as temporary:
        temporary.write(file_bytes)
        temporary_path = Path(temporary.name)

    try:
        return read_csv_with_diagnostics(temporary_path, config)
    finally:
        temporary_path.unlink(missing_ok=True)


def _show_findings(
    findings: list[dict[str, Any]],
) -> None:
    """Render quality findings grouped by severity."""
    st.subheader("Hasil pemeriksaan kualitas")

    if not findings:
        st.success("Tidak ada temuan kualitas pada dataset.")
        return

    for severity in ("high", "medium", "low", "info"):
        grouped = [
            item
            for item in findings
            if item.get("severity") == severity
        ]

        if not grouped:
            continue

        st.markdown(
            f"**Severity: {severity} ({len(grouped)})**"
        )

        for item in grouped:
            column = item.get("column") or "Dataset"
            title = item.get("title", "Temuan kualitas")
            count = item.get("count", 0)
            percentage = float(item.get("percentage", 0.0))
            description = item.get("description", "")
            recommendation = item.get("recommendation", "")

            message = (
                f"{title} — kolom: {column} — jumlah: {count} "
                f"({percentage:.2f}%)"
            )

            if severity in {"high", "medium"}:
                st.warning(message)
            else:
                st.info(message)

            st.caption(
                f"{description} Rekomendasi: {recommendation}"
            )


def _show_policy_evidence(
    policy_evidence: list[dict[str, Any]],
) -> None:
    """Render retrieved policy evidence."""
    if not policy_evidence:
        st.info(
            "Belum ada evidence kebijakan. "
            "Klik tombol Cari evidence kebijakan untuk menjalankan retrieval."
        )
        return

    for evidence_group in policy_evidence:
        query = evidence_group.get("query", "")
        results = evidence_group.get("results", [])

        st.markdown(f"**Query:** {query}")

        if not results:
            st.warning(
                "Tidak ditemukan evidence yang relevan untuk query ini."
            )
            continue

        for result in results:
            source = result.get(
                "source",
                "Sumber tidak diketahui",
            )
            page = result.get("page", "-")
            chunk_id = result.get("chunk_id", "-")
            distance = float(result.get("distance", 0.0))
            text = result.get("text", "")

            with st.expander(
                f"{source} — halaman {page}"
            ):
                st.caption(
                    f"Chunk ID: {chunk_id} · "
                    f"Distance: {distance:.4f}"
                )
                st.write(text)


def _show_gemini_analysis(
    gemini_analysis: dict[str, Any],
) -> None:
    """Render structured Gemini analysis."""
    if not gemini_analysis:
        return

    summary = gemini_analysis.get("summary", "")

    if summary:
        st.markdown("### Ringkasan")
        st.write(summary)

    metadata_assessment = gemini_analysis.get(
        "metadata_assessment",
        [],
    )

    if metadata_assessment:
        st.markdown("### Penilaian metadata")

        for item in metadata_assessment:
            st.write(f"- {item}")

    data_quality_assessment = gemini_analysis.get(
        "data_quality_assessment",
        [],
    )

    if data_quality_assessment:
        st.markdown("### Penilaian kualitas data")

        for item in data_quality_assessment:
            st.write(f"- {item}")

    priority_actions = gemini_analysis.get(
        "priority_actions",
        [],
    )

    if priority_actions:
        st.markdown("### Tindakan prioritas")

        for action in priority_actions:
            priority = action.get(
                "priority",
                "Prioritas",
            )
            action_text = action.get(
                "action",
                "Tindakan",
            )
            reason = action.get(
                "reason",
                "",
            )

            with st.expander(
                f"{priority} — {action_text}"
            ):
                st.write(reason)

    evidence_references = gemini_analysis.get(
        "evidence_references",
        [],
    )

    if evidence_references:
        st.markdown("### Referensi evidence")

        for reference in evidence_references:
            source = reference.get("source", "-")
            page = reference.get("page", "-")
            chunk_id = reference.get("chunk_id", "-")
            relevance = reference.get("relevance", "")

            st.write(
                f"- **{source}**, halaman {page} "
                f"({chunk_id}) — {relevance}"
            )

    limitations = gemini_analysis.get(
        "limitations",
        [],
    )

    if limitations:
        st.markdown("### Keterbatasan")

        for limitation in limitations:
            st.write(f"- {limitation}")


def _show_evidence_review(
    evidence_review: dict[str, Any],
) -> None:
    """Render deterministic evidence traceability review."""
    if not evidence_review:
        return

    st.subheader("Review Traceability")

    traceability_score = float(
        evidence_review.get(
            "traceability_score",
            0.0,
        )
    )
    review_status = evidence_review.get(
        "status",
        "unknown",
    )

    metrics = st.columns(3)

    metrics[0].metric(
        "Traceability score",
        f"{traceability_score:.2f}",
    )
    metrics[1].metric(
        "Referensi valid",
        evidence_review.get(
            "valid_reference_count",
            0,
        ),
    )
    metrics[2].metric(
        "Referensi tidak valid",
        evidence_review.get(
            "invalid_reference_count",
            0,
        ),
    )

    if review_status == "valid":
        st.success(
            "Seluruh referensi Gemini dapat ditelusuri "
            "ke policy evidence."
        )
    elif review_status == "partially_valid":
        st.warning(
            "Sebagian referensi Gemini tidak dapat "
            "divalidasi terhadap policy evidence."
        )
    elif review_status == "invalid":
        st.error(
            "Referensi Gemini tidak dapat divalidasi "
            "terhadap policy evidence."
        )
    elif review_status == "no_references":
        st.info(
            "Gemini tidak menyertakan referensi evidence."
        )
    else:
        st.info(
            "Status review traceability belum diketahui."
        )

    invalid_references = evidence_review.get(
        "invalid_references",
        [],
    )

    if invalid_references:
        st.markdown("### Referensi tidak valid")

        for invalid_reference in invalid_references:
            chunk_id = invalid_reference.get(
                "chunk_id",
                "-",
            )
            reason = invalid_reference.get(
                "reason",
                "",
            )

            st.warning(
                f"{chunk_id} — {reason}"
            )

    unsupported_sections = evidence_review.get(
        "unsupported_sections",
        [],
    )

    if unsupported_sections:
        st.markdown(
            "### Bagian tanpa dukungan evidence"
        )

        for unsupported_section in unsupported_sections:
            st.warning(unsupported_section)


def main() -> None:
    """Render the MetaGuard local dataset analysis workflow."""
    st.set_page_config(
        page_title="MetaGuard",
        layout="wide",
    )

    st.title("MetaGuard")
    st.write(
        "Validasi awal kualitas dataset OPD secara lokal, "
        "deterministik, dan didukung analisis berbasis evidence."
    )

    if "policy_evidence" not in st.session_state:
        st.session_state.policy_evidence = []

    if "gemini_analysis" not in st.session_state:
        st.session_state.gemini_analysis = {}

    if "active_file_signature" not in st.session_state:
        st.session_state.active_file_signature = None

    if "analysis_fingerprint" not in st.session_state:
        st.session_state.analysis_fingerprint = None

    if "analysis_state_reset" not in st.session_state:
        st.session_state.analysis_state_reset = False

    uploaded_file = st.file_uploader(
        "Unggah satu file CSV",
        type=["csv"],
        accept_multiple_files=False,
    )

    if uploaded_file is None:
        st.info("Unggah file CSV untuk memulai analisis.")
        return

    file_bytes = uploaded_file.getvalue()

    file_signature = (
        uploaded_file.name,
        len(file_bytes),
    )

    if (
        st.session_state.active_file_signature
        != file_signature
    ):
        st.session_state.active_file_signature = file_signature
        st.session_state.policy_evidence = []
        st.session_state.gemini_analysis = {}
        st.session_state.analysis_fingerprint = None
        st.session_state.analysis_state_reset = False

    st.caption(
        f"File: {uploaded_file.name} · "
        f"Ukuran: {len(file_bytes):,} byte"
    )

    with st.expander("Pengaturan parsing CSV"):
        encoding_choice = st.selectbox(
            "Encoding",
            ["Otomatis", "utf-8-sig", "utf-8", "cp1252", "latin-1"],
        )
        delimiter_choice = st.selectbox(
            "Delimiter",
            ["Otomatis", "Koma (,)", "Titik koma (;)", "Tab", "Pipe (|)"],
        )
        quote_character = st.text_input(
            "Quote character",
            value='"',
            max_chars=1,
        )
        parsing_mode = st.selectbox(
            "Penanganan baris malformed",
            ["strict", "warn"],
        )
        analysis_mode = st.selectbox(
            "Mode analisis",
            ["exact", "chunked", "sampled"],
        )

    delimiters = {
        "Otomatis": None,
        "Koma (,)": ",",
        "Titik koma (;)": ";",
        "Tab": "\t",
        "Pipe (|)": "|",
    }
    ingestion_config = CsvReadConfig(
        encoding=None if encoding_choice == "Otomatis" else encoding_choice,
        delimiter=delimiters[delimiter_choice],
        quote_character=quote_character or '"',
        parsing_mode=parsing_mode,
        analysis_mode=analysis_mode,
    )

    try:
        ingestion_result = _read_uploaded_csv(file_bytes, ingestion_config)
        dataframe = ingestion_result.dataframe
        ingestion = ingestion_result.diagnostics
    except CsvIngestionError as error:
        st.error(str(error))
        return
    except (OSError, ValueError) as error:
        st.error(
            f"File tidak dapat dibaca: {error}"
        )
        return

    if dataframe.shape[1] == 0:
        st.error("Dataset tidak memiliki kolom.")
        return

    st.subheader("Ringkasan ingestion")
    ingestion_metrics = st.columns(4)
    ingestion_metrics[0].metric("Status", ingestion["status"])
    ingestion_metrics[1].metric("Encoding", ingestion["encoding"])
    ingestion_metrics[2].metric("Delimiter", repr(ingestion["delimiter"]))
    ingestion_metrics[3].metric("Baris malformed", ingestion["malformed_rows"])
    st.caption(
        f"Mode: {ingestion['mode']} · Scope: {ingestion['analysis_scope']} · "
        f"Strategi memori: {ingestion['memory_strategy']} · "
        f"Baris dimuat: {ingestion['rows_loaded']:,} · "
        f"Kolom: {ingestion['columns_loaded']:,}"
    )
    if ingestion["sampled_rows"]:
        st.warning(
            f"Analisis sampled menggunakan {ingestion['sampled_rows']:,} dari "
            f"{ingestion['total_rows']:,} baris."
        )
    for warning in ingestion["warnings"]:
        st.warning(warning)

    st.subheader("Preview dataset")
    st.dataframe(
        dataframe.head(10),
        hide_index=True,
        width="stretch",
    )

    profile = profile_dataframe(dataframe)
    findings = run_quality_checks(dataframe)
    score = calculate_score(findings)

    st.subheader("Ringkasan profil")

    metrics = st.columns(4)

    metrics[0].metric(
        "Jumlah baris",
        profile["row_count"],
    )
    metrics[1].metric(
        "Jumlah kolom",
        profile["column_count"],
    )
    metrics[2].metric(
        "Baris duplikat",
        profile["duplicate_rows"],
    )
    metrics[3].metric(
        "Kolom seluruhnya kosong",
        len(profile["fully_empty_columns"]),
    )

    st.subheader("Informasi kolom")

    st.dataframe(
        pd.DataFrame(
            profile["column_details"]
        ),
        hide_index=True,
        width="stretch",
    )

    _show_findings(findings)

    st.subheader("Skor kualitas")

    st.metric(
        "Score",
        score["score"],
    )

    st.write(
        f"Grade: **{score['grade']}** · "
        f"Total temuan: {score['total_findings']}"
    )

    st.json(
        score["findings_by_severity"]
    )

    st.subheader("Metadata dataset")

    with st.form("metadata_form"):
        title = st.text_input(
            "Judul dataset"
        )

        description = st.text_area(
            "Deskripsi dataset"
        )

        producer_opd = st.text_input(
            "OPD produsen data"
        )

        data_period = st.text_input(
            "Periode data"
        )

        geographic_scope = st.text_input(
            "Cakupan wilayah"
        )

        measurement_unit = st.text_input(
            "Satuan pengukuran"
        )

        update_frequency = st.selectbox(
            "Frekuensi pembaruan",
            [
                "",
                "Harian",
                "Mingguan",
                "Bulanan",
                "Triwulanan",
                "Tahunan",
                "Lainnya",
            ],
        )

        responsible_unit = st.text_input(
            "Penanggung jawab atau unit pengelola"
        )

        publication_purpose = st.text_area(
            "Tujuan publikasi"
        )

        submitted = st.form_submit_button(
            "Validasi metadata",
            type="primary",
        )

    metadata = {
        "title": title,
        "description": description,
        "producer_opd": producer_opd,
        "data_period": data_period,
        "geographic_scope": geographic_scope,
        "measurement_unit": measurement_unit,
        "update_frequency": update_frequency,
        "responsible_unit": responsible_unit,
        "publication_purpose": publication_purpose,
    }

    current_fingerprint = build_analysis_fingerprint(
        file_name=uploaded_file.name,
        file_bytes=file_bytes,
        metadata=metadata,
        ingestion_config={
            "encoding": ingestion_config.encoding,
            "delimiter": ingestion_config.delimiter,
            "quote_character": ingestion_config.quote_character,
            "parsing_mode": ingestion_config.parsing_mode,
            "analysis_mode": ingestion_config.analysis_mode,
        },
    )

    previous_fingerprint = (
        st.session_state.analysis_fingerprint
    )

    if (
        previous_fingerprint is not None
        and previous_fingerprint != current_fingerprint
    ):
        had_previous_results = bool(
            st.session_state.policy_evidence
            or st.session_state.gemini_analysis
        )

        st.session_state.policy_evidence = []
        st.session_state.gemini_analysis = {}
        st.session_state.analysis_state_reset = (
            had_previous_results
        )

    st.session_state.analysis_fingerprint = (
        current_fingerprint
    )

    if st.session_state.analysis_state_reset:
        st.warning(
            "Input CSV atau metadata telah berubah. "
            "Evidence kebijakan dan analisis Gemini sebelumnya "
            "telah dihapus. Jalankan kembali proses evidence "
            "dan analisis Gemini."
        )
        st.session_state.analysis_state_reset = False

    metadata_validation = validate_metadata(
        metadata
    )

    metadata_has_value = any(
        str(value).strip()
        for value in metadata.values()
    )

    if submitted or metadata_has_value:
        st.metric(
            "Skor kelengkapan metadata",
            f"{metadata_validation['completeness_score']:.2f}",
        )

        st.write(
            f"Status: **{metadata_validation['status']}**"
        )

        missing_fields = metadata_validation[
            "missing_fields"
        ]

        if missing_fields:
            st.warning(
                "Field belum lengkap: "
                + ", ".join(missing_fields)
            )
        else:
            st.success(
                "Seluruh field metadata wajib telah diisi."
            )

        for item in metadata_validation[
            "findings"
        ]:
            st.info(
                f"{item['field']}: "
                f"{item['issue']} "
                f"{item['recommendation']}"
            )

    st.subheader("Evidence Kebijakan")

    st.caption(
        "Evidence diambil dari dokumen kebijakan lokal "
        "yang telah diproses melalui knowledge base MetaGuard."
    )

    if st.button(
        "Cari evidence kebijakan",
        type="secondary",
    ):
        policy_queries = build_policy_queries(
            metadata_validation=metadata_validation,
            quality_findings=findings,
        )

        try:
            with st.spinner(
                "Mencari evidence pada dokumen kebijakan..."
            ):
                st.session_state.policy_evidence = (
                    build_policy_evidence(
                        queries=policy_queries,
                        retriever=retrieve_policy_chunks,
                        top_k=3,
                    )
                )

            st.session_state.gemini_analysis = {}

        except (OSError, RuntimeError, ValueError):
            st.session_state.policy_evidence = []
            st.session_state.gemini_analysis = {}

            st.error(
                "Knowledge base belum siap atau retrieval gagal. "
                "Jalankan `python -m rag.ingest` terlebih dahulu."
            )

    policy_evidence: list[dict[str, Any]] = (
        st.session_state.policy_evidence
    )

    _show_policy_evidence(
        policy_evidence
    )

    st.subheader("Analisis dengan Gemini")

    st.caption(
        "Gemini menganalisis hasil validasi lokal dan evidence "
        "kebijakan. Analisis ini bukan keputusan hukum dan tidak "
        "menggantikan pemeriksaan manusia."
    )

    if not policy_evidence:
        st.info(
            "Cari evidence kebijakan terlebih dahulu sebelum "
            "menjalankan analisis Gemini."
        )
    else:
        if st.button(
            "Analisis dengan Gemini",
            type="primary",
        ):
            try:
                with st.spinner(
                    "Gemini sedang menganalisis hasil MetaGuard..."
                ):
                    st.session_state.gemini_analysis = (
                        analyze_with_gemini(
                            profile=profile,
                            findings=findings,
                            metadata=metadata,
                            metadata_validation=metadata_validation,
                            policy_evidence=policy_evidence,
                            ingestion=ingestion,
                        )
                    )

            except ValueError as error:
                st.session_state.gemini_analysis = {}
                st.warning(str(error))

            except RuntimeError as error:
                st.session_state.gemini_analysis = {}
                st.error(str(error))

            except Exception:
                st.session_state.gemini_analysis = {}

                st.error(
                    "Analisis Gemini gagal dijalankan. "
                    "Periksa konfigurasi API, koneksi internet, "
                    "dan kuota Free Tier."
                )

    gemini_analysis: dict[str, Any] = (
        st.session_state.gemini_analysis
    )

    _show_gemini_analysis(
        gemini_analysis
    )

    evidence_review: dict[str, Any] = {}

    if gemini_analysis:
        evidence_review = review_evidence_traceability(
            policy_evidence=policy_evidence,
            gemini_analysis=gemini_analysis,
        )

        _show_evidence_review(
            evidence_review
        )

    st.subheader("Laporan JSON")

    report = build_report(
        profile=profile,
        findings=findings,
        score=score,
        source={
            "file_name": uploaded_file.name,
            "size_bytes": len(file_bytes),
        },
        metadata=metadata,
        metadata_validation=metadata_validation,
        policy_evidence=policy_evidence,
        gemini_analysis=gemini_analysis,
        evidence_review=evidence_review,
        ingestion=ingestion,
    )

    st.download_button(
        "Unduh laporan JSON",
        data=json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        file_name="metaguard_report.json",
        mime="application/json",
    )


if __name__ == "__main__":
    main()
