"""Streamlit entry point for the local MetaGuard analysis pipeline."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from core.analysis_state import (
    build_analysis_fingerprint,
    reset_analysis_results,
)
from core.agent_models import AgentAction, AgentAuditEvent, AgentDecision, AgentStage
from core.agent_orchestrator import execute_decision
from core.agent_state_builder import append_audit_event, refresh_agent_review
from core.agent_tools import AgentExecutionContext
from core.csv_ingestion import (
    CsvIngestionError,
    CsvIngestionResult,
    CsvReadConfig,
    build_csv_read_config,
    read_csv_with_diagnostics,
)
from core.contextual_validation import run_contextual_validation
from core.data_profiler import profile_dataframe
from core.metadata_validator import validate_metadata
from core.policy_evidence import build_policy_evidence, build_policy_queries
from core.quality_checker import run_quality_checks
from core.report_builder import build_report
from core.scoring import calculate_score
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


def _show_agentic_review(
    decision: AgentDecision,
    audit: list[AgentAuditEvent],
) -> None:
    """Render the lightweight, state-aware agent recommendation."""
    st.subheader("Agentic Review")
    with st.container(border=True):
        st.write(f"**Current stage:** `{decision.current_stage.value}`")
        st.write(f"**Recommended next action:** `{decision.next_action.value}`")
        st.write(f"**Reason:** {decision.decision_reason}")
        if decision.blocking_condition:
            st.warning(f"Blocking condition: {decision.blocking_condition}")
        else:
            st.write("**Blocking condition:** Tidak ada.")
        approval = "Diperlukan" if decision.requires_human_action else "Tidak diperlukan"
        st.write(f"**Human action required:** {approval}")

    with st.expander("Agent Decision Log"):
        if not audit:
            st.info("Belum ada decision atau action yang dicatat.")
            return
        for event in audit:
            st.write(
                f"Langkah {event.step} · `{event.stage.value}` · "
                f"`{event.action.value}` · {event.outcome}"
            )
            st.caption(event.reason)
            if event.error:
                st.caption(f"Keterangan: {event.error}")


def _show_contextual_validation(
    validation: dict[str, Any],
    *,
    completed: bool,
) -> None:
    """Render compact, human-reviewable deterministic contextual findings."""
    st.subheader("Validasi Kontekstual")
    if not completed:
        st.info("Validasi kontekstual akan dijalankan setelah metadata divalidasi.")
        return

    status = validation.get("status", "not_evaluable")
    count = int(validation.get("finding_count", 0))
    labels = {
        "consistent": "Konsisten",
        "potential_inconsistency": "Perlu Verifikasi",
        "not_evaluable": "Belum dapat dievaluasi",
    }
    st.write(f"Status: **{labels.get(status, status)}**")
    st.metric("Jumlah temuan kontekstual", count)
    if not count:
        st.info("Tidak ada potensi inkonsistensi dari rule kontekstual yang dapat dievaluasi.")
        return

    for finding in validation.get("findings", []):
        title = finding.get("title", "Temuan kontekstual")
        with st.expander(title):
            st.write(f"Severity: **{finding.get('severity', 'medium')}**")
            affected = finding.get("affected_rows")
            percentage = finding.get("percentage")
            if affected is not None:
                suffix = f" ({float(percentage or 0):.2f}%)"
                if validation.get("analysis_scope") == "sampled":
                    st.write(
                        "Baris terdampak pada sampel: "
                        f"{affected} dari {validation.get('rows_evaluated', 0):,} "
                        f"baris yang dianalisis ({validation.get('total_rows', 0):,} total){suffix}"
                    )
                else:
                    st.write(f"Baris terdampak: {affected}{suffix}")
            st.write(finding.get("description", ""))
            st.caption(f"Rekomendasi: {finding.get('recommendation', '')}")


def _next_agent_step(audit: list[AgentAuditEvent]) -> int:
    """Return the next monotonic audit step for the active session."""
    return audit[-1].step + 1 if audit else 1


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

    if "policy_evidence_retrieval_completed" not in st.session_state:
        st.session_state.policy_evidence_retrieval_completed = False

    if "metadata_validation_completed" not in st.session_state:
        st.session_state.metadata_validation_completed = False

    if "contextual_validation_completed" not in st.session_state:
        st.session_state.contextual_validation_completed = False

    if "contextual_validation" not in st.session_state:
        st.session_state.contextual_validation = {}

    if "gemini_analysis" not in st.session_state:
        st.session_state.gemini_analysis = {}

    if "evidence_review" not in st.session_state:
        st.session_state.evidence_review = {}

    if "report_payload" not in st.session_state:
        st.session_state.report_payload = {}

    if "active_file_signature" not in st.session_state:
        st.session_state.active_file_signature = None

    if "analysis_fingerprint" not in st.session_state:
        st.session_state.analysis_fingerprint = None

    if "analysis_state_reset" not in st.session_state:
        st.session_state.analysis_state_reset = False

    if "agent_state" not in st.session_state:
        st.session_state.agent_state = None

    if "agent_decision" not in st.session_state:
        st.session_state.agent_decision = None

    if "agent_audit" not in st.session_state:
        st.session_state.agent_audit = []

    uploaded_file = st.file_uploader(
        "Unggah satu file CSV",
        type=["csv"],
        accept_multiple_files=False,
    )

    if uploaded_file is None:
        _, decision = refresh_agent_review(
            st.session_state,
            fingerprint=None,
        )
        _show_agentic_review(decision, st.session_state.agent_audit)
        _show_contextual_validation({}, completed=False)
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
        reset_analysis_results(st.session_state)
        st.session_state.analysis_fingerprint = None
        st.session_state.analysis_state_reset = False

    st.caption(
        f"File: {uploaded_file.name} · "
        f"Ukuran: {len(file_bytes):,} byte"
    )

    with st.expander("Pengaturan parsing CSV"):
        default_csv_config = CsvReadConfig()
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
        chunk_size: int | None = None
        sample_size: int | None = None
        sample_seed: int | None = None
        if analysis_mode == "chunked":
            chunk_size = int(st.number_input(
                "Chunk size",
                min_value=500,
                max_value=100_000,
                value=default_csv_config.chunk_size,
                step=500,
                help=(
                    "Jumlah baris yang dibaca pada setiap chunk. Pada versi ini "
                    "seluruh chunk masih digabung menjadi satu DataFrame untuk "
                    "pemeriksaan global."
                ),
            ))
        elif analysis_mode == "sampled":
            sample_size = int(st.number_input(
                "Sample size",
                min_value=100,
                max_value=1_000_000,
                value=default_csv_config.sample_size,
                step=100,
                help="Jumlah maksimum baris yang dipilih menggunakan reservoir sampling deterministik.",
            ))
            sample_seed = int(st.number_input(
                "Sample seed",
                min_value=0,
                max_value=2_147_483_647,
                value=default_csv_config.sample_seed,
                step=1,
                help="Seed memastikan file dan konfigurasi yang sama menghasilkan sampel yang sama.",
            ))

    delimiters = {
        "Otomatis": None,
        "Koma (,)": ",",
        "Titik koma (;)": ";",
        "Tab": "\t",
        "Pipe (|)": "|",
    }
    ingestion_config = build_csv_read_config(
        encoding=None if encoding_choice == "Otomatis" else encoding_choice,
        delimiter=delimiters[delimiter_choice],
        quote_character=quote_character or '"',
        parsing_mode=parsing_mode,
        analysis_mode=analysis_mode,
        chunk_size=chunk_size,
        sample_size=sample_size,
        sample_seed=sample_seed,
        base_config=default_csv_config,
    )

    try:
        ingestion_result = _read_uploaded_csv(file_bytes, ingestion_config)
        dataframe = ingestion_result.dataframe
        ingestion = ingestion_result.diagnostics
    except CsvIngestionError as error:
        _, decision = refresh_agent_review(
            st.session_state,
            fingerprint=None,
            ingestion=error.diagnostics,
            error_message=str(error),
        )
        _show_agentic_review(decision, st.session_state.agent_audit)
        st.error(str(error))
        return
    except (OSError, ValueError) as error:
        _, decision = refresh_agent_review(
            st.session_state,
            fingerprint=None,
            ingestion={"status": "failed"},
            error_message=str(error),
        )
        _show_agentic_review(decision, st.session_state.agent_audit)
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
    ingestion_caption = (
        f"Mode: {ingestion['mode']} · Scope: {ingestion['analysis_scope']} · "
        f"Strategi memori: {ingestion['memory_strategy']} · "
        f"Baris dimuat: {ingestion['rows_loaded']:,} · "
        f"Kolom: {ingestion['columns_loaded']:,}"
    )
    if ingestion["mode"] == "chunked":
        ingestion_caption += f" · Chunk size: {ingestion['chunk_size_requested']:,}"
    st.caption(ingestion_caption)
    if ingestion["mode"] == "sampled":
        if ingestion["sampling_applied"]:
            st.warning(
                f"Analisis sampled menggunakan {ingestion['sampled_rows']:,} dari "
                f"{ingestion['total_rows']:,} baris · Sample size diminta: "
                f"{ingestion['sample_size_requested']:,} · Seed: "
                f"{ingestion['sample_seed']:,}."
            )
        else:
            st.info(
                f"Mode sampled mencakup seluruh {ingestion['total_rows']:,} baris · "
                f"Sample size diminta: {ingestion['sample_size_requested']:,} · "
                f"Seed: {ingestion['sample_seed']:,}."
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
            "header_row": ingestion_config.header_row,
            "missing_value_tokens": ingestion_config.missing_value_tokens,
            "chunk_size": ingestion_config.chunk_size,
            "sample_size": ingestion_config.sample_size,
            "sample_seed": ingestion_config.sample_seed,
        },
    )

    previous_fingerprint = (
        st.session_state.analysis_fingerprint
    )

    if (
        previous_fingerprint is not None
        and previous_fingerprint != current_fingerprint
    ):
        had_previous_results = reset_analysis_results(st.session_state)
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

    if submitted:
        st.session_state.metadata_validation_completed = True
        st.session_state.agent_audit = append_audit_event(
            st.session_state.agent_audit,
            fingerprint=current_fingerprint,
            stage=AgentStage.METADATA_REQUIRED,
            action=AgentAction.VALIDATE_METADATA,
            reason="Pengguna menjalankan validasi metadata.",
            outcome="success",
        )
        st.session_state.contextual_validation = run_contextual_validation(
            dataframe,
            metadata,
            profile="healthcare",
            ingestion=ingestion,
        )
        st.session_state.contextual_validation_completed = True
        st.session_state.agent_audit = append_audit_event(
            st.session_state.agent_audit,
            fingerprint=current_fingerprint,
            stage=AgentStage.CONTEXTUAL_VALIDATION_REQUIRED,
            action=AgentAction.RUN_CONTEXTUAL_VALIDATION,
            reason="Validasi kontekstual deterministik dijalankan setelah metadata divalidasi.",
            outcome="success",
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

    _show_contextual_validation(
        st.session_state.contextual_validation,
        completed=st.session_state.contextual_validation_completed,
    )

    agent_state, agent_decision = refresh_agent_review(
        st.session_state,
        fingerprint=current_fingerprint,
        ingestion=ingestion,
        profile=profile,
        findings=findings,
        score=score,
        metadata_validation=metadata_validation,
        metadata_validation_completed=st.session_state.metadata_validation_completed,
        contextual_validation=st.session_state.contextual_validation,
        contextual_validation_completed=st.session_state.contextual_validation_completed,
        policy_evidence=st.session_state.policy_evidence,
        policy_evidence_retrieval_completed=(
            st.session_state.policy_evidence_retrieval_completed
        ),
        gemini_analysis=st.session_state.gemini_analysis,
        evidence_review=st.session_state.evidence_review,
        report_payload=st.session_state.report_payload,
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
            st.session_state.evidence_review = {}
            st.session_state.report_payload = {}
            st.session_state.policy_evidence_retrieval_completed = True
            st.session_state.agent_audit = append_audit_event(
                st.session_state.agent_audit,
                fingerprint=current_fingerprint,
                stage=AgentStage.EVIDENCE_REQUIRED,
                action=AgentAction.RETRIEVE_POLICY_EVIDENCE,
                reason="Pengguna menjalankan retrieval policy evidence.",
                outcome="success",
            )

        except (OSError, RuntimeError, ValueError) as error:
            st.session_state.policy_evidence = []
            st.session_state.gemini_analysis = {}
            st.session_state.evidence_review = {}
            st.session_state.report_payload = {}
            st.session_state.policy_evidence_retrieval_completed = False
            st.session_state.agent_audit = append_audit_event(
                st.session_state.agent_audit,
                fingerprint=current_fingerprint,
                stage=AgentStage.EVIDENCE_REQUIRED,
                action=AgentAction.RETRIEVE_POLICY_EVIDENCE,
                reason="Retrieval policy evidence gagal dijalankan.",
                outcome="failed",
                error=str(error)[:300],
            )

            st.error(
                "Knowledge base belum siap atau retrieval gagal. "
                "Jalankan `python -m rag.ingest` terlebih dahulu."
            )

    policy_evidence: list[dict[str, Any]] = (
        st.session_state.policy_evidence
    )

    agent_state, agent_decision = refresh_agent_review(
        st.session_state,
        fingerprint=current_fingerprint,
        ingestion=ingestion,
        profile=profile,
        findings=findings,
        score=score,
        metadata_validation=metadata_validation,
        metadata_validation_completed=st.session_state.metadata_validation_completed,
        contextual_validation=st.session_state.contextual_validation,
        contextual_validation_completed=st.session_state.contextual_validation_completed,
        policy_evidence=policy_evidence,
        policy_evidence_retrieval_completed=(
            st.session_state.policy_evidence_retrieval_completed
        ),
        gemini_analysis=st.session_state.gemini_analysis,
        evidence_review=st.session_state.evidence_review,
        report_payload=st.session_state.report_payload,
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

    gemini_allowed = (
        agent_decision.current_stage is AgentStage.ANALYSIS_READY
        and agent_decision.next_action is AgentAction.RUN_GEMINI_ANALYSIS
        and agent_state.evidence_count > 0
    )

    if not gemini_allowed:
        st.info(
            agent_decision.blocking_condition
            or "Lengkapi tahap yang direkomendasikan agent sebelum menjalankan Gemini."
        )
    if st.button(
        "Analisis dengan Gemini",
        type="primary",
        disabled=not gemini_allowed,
    ):
        with st.spinner("Gemini sedang menganalisis hasil MetaGuard..."):
            execution = execute_decision(
                agent_decision,
                agent_state,
                AgentExecutionContext(
                    ingestion=ingestion,
                    profile=profile,
                    findings=findings,
                    metadata=metadata,
                    metadata_validation=metadata_validation,
                    policy_evidence=policy_evidence,
                ),
                approved=True,
                step=_next_agent_step(st.session_state.agent_audit),
            )
        if execution.audit_event is not None:
            st.session_state.agent_audit = [
                *st.session_state.agent_audit,
                execution.audit_event,
            ]
        if execution.success:
            st.session_state.gemini_analysis = execution.output
            st.session_state.evidence_review = {}
            st.session_state.report_payload = {}
        else:
            st.session_state.gemini_analysis = {}
            st.session_state.evidence_review = {}
            st.session_state.report_payload = {}
            st.error(
                execution.error
                or "Analisis Gemini gagal dijalankan. Periksa konfigurasi API, koneksi internet, dan kuota Free Tier."
            )

    gemini_analysis: dict[str, Any] = (
        st.session_state.gemini_analysis
    )

    _show_gemini_analysis(
        gemini_analysis
    )

    evidence_review: dict[str, Any] = st.session_state.evidence_review

    if gemini_analysis and not evidence_review:
        trace_state, trace_decision = refresh_agent_review(
            st.session_state,
            fingerprint=current_fingerprint,
            ingestion=ingestion,
            profile=profile,
            findings=findings,
            score=score,
            metadata_validation=metadata_validation,
            metadata_validation_completed=st.session_state.metadata_validation_completed,
            contextual_validation=st.session_state.contextual_validation,
            contextual_validation_completed=st.session_state.contextual_validation_completed,
            policy_evidence=policy_evidence,
            policy_evidence_retrieval_completed=(
                st.session_state.policy_evidence_retrieval_completed
            ),
            gemini_analysis=gemini_analysis,
            evidence_review=evidence_review,
            report_payload=st.session_state.report_payload,
        )
        if st.button("Jalankan review traceability", type="secondary"):
            execution = execute_decision(
                trace_decision,
                trace_state,
                AgentExecutionContext(
                    policy_evidence=policy_evidence,
                    gemini_analysis=gemini_analysis,
                ),
                step=_next_agent_step(st.session_state.agent_audit),
            )
            if execution.audit_event is not None:
                st.session_state.agent_audit = [
                    *st.session_state.agent_audit,
                    execution.audit_event,
                ]
            if execution.success:
                st.session_state.evidence_review = execution.output
                evidence_review = execution.output
                st.session_state.report_payload = {}
            else:
                st.error(execution.error or "Review traceability gagal dijalankan.")

    if evidence_review:
        _show_evidence_review(evidence_review)

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
        contextual_validation=st.session_state.contextual_validation,
        policy_evidence=policy_evidence,
        gemini_analysis=gemini_analysis,
        evidence_review=evidence_review,
        ingestion=ingestion,
    )
    report_ready = bool(evidence_review)
    if not report_ready:
        st.info("Selesaikan review traceability sebelum membuat laporan JSON.")
    if report_ready:
        st.session_state.report_payload = report
    st.download_button(
        "Unduh laporan JSON",
        data=json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        file_name="metaguard_report.json",
        mime="application/json",
        disabled=not report_ready,
    )
    if report_ready:
        st.session_state.agent_audit = append_audit_event(
            st.session_state.agent_audit,
            fingerprint=current_fingerprint,
            stage=AgentStage.REPORT_REQUIRED,
            action=AgentAction.BUILD_REPORT,
            reason="Payload laporan JSON berhasil dibangun.",
            outcome="success",
        )

    final_agent_state, final_agent_decision = refresh_agent_review(
        st.session_state,
        fingerprint=current_fingerprint,
        ingestion=ingestion,
        profile=profile,
        findings=findings,
        score=score,
        metadata_validation=metadata_validation,
        metadata_validation_completed=st.session_state.metadata_validation_completed,
        contextual_validation=st.session_state.contextual_validation,
        contextual_validation_completed=st.session_state.contextual_validation_completed,
        policy_evidence=st.session_state.policy_evidence,
        policy_evidence_retrieval_completed=(
            st.session_state.policy_evidence_retrieval_completed
        ),
        gemini_analysis=st.session_state.gemini_analysis,
        evidence_review=st.session_state.evidence_review,
        report_payload=st.session_state.report_payload,
    )
    if (
        final_agent_state.traceability_review_completed
        and final_agent_state.traceability_status != "valid"
    ):
        st.warning(
            "Traceability telah ditinjau, tetapi statusnya "
            f"`{final_agent_state.traceability_status}`. Periksa hasil review sebelum menggunakan laporan."
        )
    if final_agent_state.contextual_requires_human_review:
        st.warning("Temuan kontekstual memerlukan verifikasi manusia atau domain.")
    _show_agentic_review(final_agent_decision, st.session_state.agent_audit)


if __name__ == "__main__":
    main()
