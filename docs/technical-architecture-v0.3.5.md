# Arsitektur Teknis MetaGuard v0.3.5

## 1. Tujuan Dokumen

Dokumen ini menjelaskan cara kerja internal MetaGuard v0.3.5: aliran data, pemeriksaan deterministik, resolusi konsep, eksekusi rule domain, workflow evidence kebijakan, orchestrator, Gemini guard, traceability, dan report JSON.

Dokumen ini bukan README kedua. README berfokus pada tujuan dan penggunaan; dokumen ini berfokus pada kontrak komponen, batas tanggung jawab, dan alasan desain agar hasil review dapat diaudit.

## 2. Prinsip Arsitektur

- Deterministic-first: quality check, metadata validation, contextual validation, dan domain rule menghasilkan finding melalui kode Python terkontrol. Gemini bukan sumber finding teknis.
- Explicit context: selected_domain dan governance_context adalah enum tervalidasi, bukan hasil inferensi CSV atau LLM.
- Bounded AI: evidence retrieval maksimal dua attempt per evidence need; Gemini memerlukan readiness dan approval manusia eksplisit.
- Policy-grounded evidence: policy registry menentukan corpus lokal; router dan retrieval hanya memakai metadata tervalidasi.
- Provenance dan traceability: finding rule menyimpan rule/konsep/kolom/provenance; citation Gemini diperiksa terhadap evidence supplied.
- Safe failure: missing concept, ambiguous concept, empty retrieval, stale corpus, dan not-applicable dinyatakan sebagai state eksplisit.
- No arbitrary tool loop: orchestrator menentukan action dari AgentState dan allowlist statis; registry tidak dapat mendefinisikan executable Python atau raw Chroma filter.

## 3. High-Level Architecture

~~~mermaid
flowchart TD
    U[User / Streamlit] --> I[CSV ingestion]
    I --> P[Profiling dan generic quality checks]
    P --> M[Metadata validation]
    M --> C[Explicit analysis context]
    C --> S[Concept resolution]
    S --> R[Contextual dan domain rule engine]
    R --> EP[Evidence planning dan policy router]
    EP --> CR[Chroma v3 retrieval]
    CR --> EA[Sufficiency dan alignment]
    EA -->|READY| HA[Human approval]
    HA --> G[Gemini opsional]
    EA -->|NOT_APPLICABLE| DR[Deterministic completion/report]
    EA -->|Belum ready| ER[Evidence review / bounded retry]
    ER -->|Retry tersedia| CR
    ER -->|Tetap belum ready| HR[Evidence review required, bukan COMPLETE]
    G --> T[Traceability review]
    T --> DR
~~~

app.py menangani UI Streamlit dan session state. Business logic berada pada core, rag, dan llm sehingga dapat diuji tanpa UI.

## 4. Layer dan Tanggung Jawab Komponen

### 4.1 Presentation / Streamlit Layer

app.py menerima upload CSV, konfigurasi ingestion, selector domain/governance, dan approval. Ia membangun AnalysisContext, mengelola fingerprint/session state, lalu merender findings, evidence workflow, agentic review, Gemini result, dan report.

UI tidak mengevaluasi rule atau membuat raw filter Chroma. UI meneruskan snapshot state ke build_agent_state() dan build_report().

### 4.2 Ingestion Layer

core/csv_ingestion.py menyediakan CsvReadConfig, preflight_csv(), dan read_csv_with_diagnostics().

Preflight memeriksa bytes CSV, encoding, delimiter, quote character, header, malformed row, duplicate header, dan unnamed header. Bila encoding tidak di-override, fallback yang dicoba adalah utf-8-sig, utf-8, cp1252, dan latin-1. Parsing menggunakan Pandas dengan mode strict atau warn.

| Mode | Implementasi | Scope |
| --- | --- | --- |
| exact | Satu DataFrame dari seluruh file. | full |
| chunked | Membaca bertahap lalu menggabungkan chunk untuk pemeriksaan global. | full |
| sampled | Reservoir sampling deterministik dengan sample_seed. | sampled bila sample lebih kecil dari total row |

Mode chunked bukan true out-of-core karena seluruh chunk tetap digabungkan ke memori. Diagnostics JSON-safe menyimpan status, encoding, delimiter, scope, rows loaded/total, malformed row, dan warning.

### 4.3 Profiling dan Generic Quality Layer

core/data_profiler.py menghasilkan profile JSON-safe: jumlah baris/kolom, dtype, missing values, unique values, fully empty columns, duplicate rows, dan sample rows terbatas.

core/quality_checker.py menghasilkan finding deterministik untuk:

- missing values;
- whitespace dan empty strings;
- category variation;
- duplicate identifier;
- invalid date dan inconsistent date format;
- negative numeric, dengan pengecualian nama koordinat yang dikenal;
- percentage di luar rentang 0–100;
- numeric outlier IQR;
- constant/empty column;
- duplicate rows dan duplicate column names.

core/scoring.py menghitung quality score dari finding. Score ini adalah indikator kualitas MetaGuard, bukan score legal atau compliance.

### 4.4 Metadata dan Context Layer

core/metadata_validator.py memvalidasi sembilan metadata wajib: title, description, producer OPD, data period, geographic scope, measurement unit, update frequency, responsible unit, dan publication purpose. Output memuat completeness score, status Lengkap/Cukup Lengkap/Belum Lengkap, serta missing fields.

core/analysis_context.py membangun AnalysisContext immutable dari selected_domain, governance_context, DomainProfile, dan fingerprint Concept/Rule/Policy Registry. AnalysisContext.fingerprint() memakai canonical JSON dan SHA-256.

core/analysis_state.py menggabungkan fingerprint input CSV/metadata dan analysis-context fingerprint untuk menentukan stale-state invalidation.

### 4.5 Semantic Concept Resolution

data/concept_registry.json adalah source of truth deklaratif. core/concept_registry.py memuat ConceptRecord immutable dan menolak concept ID atau alias collision dalam domain yang sama.

normalize_column_name() melakukan casefold, trim, serta normalisasi separator menjadi underscore. Resolusi memakai exact normalized alias atau canonical name; tidak ada substring matching atau fuzzy matching.

Contoh registry:

~~~text
education: jumlah_siswa       -> student_count
education: jumlah_ruang_kelas -> classroom_count
environment: nilai_pengukuran -> environment_measurement
~~~

map_dataframe_columns() menyimpan posisi kolom sumber dan mendeteksi normalized duplicate columns. Konsep yang tidak ditemukan menghasilkan skipped_missing_concept; konsep ambiguous menghasilkan skipped_ambiguous_concept.

### 4.6 Domain Rule Engine

data/rule_registry.json menyimpan metadata rule. core/rule_registry.py memvalidasi rule ID, domain, pack, severity, evaluator ID, provenance, dan keterkaitan konsep.

core/domain_rule_engine.py:

1. memvalidasi selected_domain;
2. meresolusikan concept ID ke kolom aktual;
3. mengambil rule hanya untuk domain itu;
4. memakai evaluator dari EVALUATOR_ALLOWLIST statis;
5. mengembalikan DomainRuleExecutionSummary dan RuleExecutionResult.

State rule adalah evaluated, skipped_missing_concept, skipped_ambiguous_concept, not_applicable, atau error. Finding diperkaya dengan rule ID, rule pack, domain, provenance, konsep, resolved columns, human review, policy requirement, dan interpretation note.

| Provenance | Arti implementasi |
| --- | --- |
| DETERMINISTIC_INVARIANT | Relasi konsistensi yang diperlakukan MetaGuard sebagai invariant data. |
| POLICY_SUPPORTED | Kategori untuk rule dengan dukungan policy yang benar-benar diverifikasi. |
| TECHNICAL_STANDARD | Kategori untuk rule dengan dukungan standard teknis yang diverifikasi. |
| HEURISTIC | Sinyal review MetaGuard; bukan regulasi atau pelanggaran otomatis. |

Pada baseline ini, HEALTH-BED-CAPACITY-001 memakai DETERMINISTIC_INVARIANT. Rule internet/bandwidth serta pilot education/environment memakai HEURISTIC dan membutuhkan human review.

## 5. Domain Isolation

Isolation bergantung pada DomainId, bukan kemiripan nama kolom:

- healthcare hanya menjalankan healthcare_core;
- education hanya menjalankan education_core;
- environment hanya menjalankan environment_core;
- generic dan other tidak menjalankan pack sektoral.

run_domain_rule_validation() memanggil rules_for_domain(domain_id) sebelum evaluator dijalankan. Kolom healthcare pada dataset education tidak dapat mengaktifkan rule healthcare. Generic contextual checks tetap tersedia karena terpisah dari domain rule pack.

## 6. Policy Registry dan Corpus v3

data/policy_registry.json adalah source of truth untuk policy yang dapat menjadi corpus. Registry memuat policy ID, domain, pack, document type, classification, effective status, verification state, topics, scope, dan file PDF lokal. Eligibility memakai metadata tersebut; statusnya adalah status dalam registry/corpus lokal MetaGuard, bukan jaminan legal-currentness eksternal.

| Policy ID | Domain / pack |
| --- | --- |
| GOV-SDI-PERPRES-39-2019 | generic / government_generic |
| BPS-STANDARD-DATA-4-2020 | generic / government_generic |
| BPS-METADATA-5-2020 | generic / government_generic |
| HEALTH-SATU-DATA-18-2022 | healthcare / healthcare |
| EDU-SATU-DATA-31-2022 | education / education |
| ENV-SATU-DATA-25-2021 | environment / environment |

rag/policy_corpus_v3.py membangun corpus secara eksplisit, tidak pada import atau rerun UI. Collection fixed adalah metaguard_policies_v3; manifest lokal bernama metaguard_policies_v3_manifest.json.

Pipeline corpus v3:

1. memvalidasi registry dan file lokal;
2. mengekstrak PDF per halaman melalui rag/document_loader.py;
3. melakukan chunking deterministik melalui rag/chunker.py;
4. membangun chunk ID stabil dari policy, page, ordinal, text, dan konfigurasi chunk;
5. meng-embed text memakai sentence-transformers/all-MiniLM-L6-v2;
6. menyimpan metadata scalar ke Chroma;
7. memverifikasi collection lalu menulis manifest secara atomik.

Fingerprint corpus mencakup checksum PDF, metadata registry relevan, embedding model, konfigurasi/version chunking, dan collection schema version. Perubahan file, registry, model, config, manifest, atau collection dapat membuat corpus stale. Rebuild hanya menargetkan collection v3 dan merupakan tindakan maintenance eksplisit.

## 7. Evidence Planning dan Routing

core/product_evidence_v3.py merencanakan evidence need secara deterministik. core/policy_router.py menerima evidence need berikut:

~~~text
metadata_governance
data_quality
accountability
domain_semantic_support
technical_standard_support
~~~

route_policy_evidence() menerima domain, governance context, evidence need, optional topic, dan Policy Registry tervalidasi. Outputnya adalah PolicyRoutingResult, bukan raw Chroma filter dari caller.

| Applicability state | Kontrak |
| --- | --- |
| APPLICABLE | Ada policy yang eligible menurut effective status, verification state, domain, pack, dan scope pada registry lokal. |
| NOT_APPLICABLE | Evidence kebijakan tidak diterapkan untuk context itu. |
| NO_ELIGIBLE_POLICY | Input valid, tetapi registry/routing scope tidak menyediakan policy eligible. |

Untuk government_public, governance need dirutekan ke government_generic; domain_semantic_support hanya ke pack domain terpilih. Untuk generic_non_government, router menghasilkan NOT_APPLICABLE tanpa query Chroma kebijakan pemerintah.

build_chroma_where() membangun metadata filter scalar dari routing tervalidasi. Tidak ada raw filter injection, LLM query rewriting, atau fallback lintas-domain.

## 8. Retrieval, Sufficiency, dan Alignment

rag/policy_retrieval_v3.py selalu menargetkan metaguard_policies_v3 dan memeriksa kesesuaian corpus/manifest lokal sebelum query. Evidence mempertahankan chunk ID, source, page, text, serta metadata policy/domain/pack.

| Retrieval state | Makna |
| --- | --- |
| SUCCESS | Ada chunk eligible setelah deduplikasi chunk ID. |
| EMPTY | Routing applicable tetapi tidak ada chunk eligible. |
| NOT_APPLICABLE | Routing tidak applicable; Chroma tidak di-query. |
| CORPUS_STALE | Corpus/manifest lokal tidak sesuai expected state; rebuild eksplisit diperlukan. |

core/evidence_sufficiency.py menggunakan formula:

~~~text
score = coverage_ratio × 60
      + unique_evidence_adequacy × 30
      + source_diversity × 10
~~~

- SUFFICIENT_THRESHOLD = 85;
- PARTIAL_THRESHOLD = 40;
- MIN_UNIQUE_EVIDENCE_FOR_SUFFICIENT = 2;
- source diversity penuh memerlukan minimal dua source.

Score ini adalah heuristic kesiapan evidence MetaGuard, bukan compliance score. Duplicate chunk ID tidak meningkatkan unique count, coverage, diversity, atau readiness.

core/evidence_alignment.py menilai policy-pack alignment dan domain alignment terpisah dari score. Evidence dengan policy ID di luar eligible_policy_ids tidak boleh meningkatkan sufficiency/readiness.

~~~mermaid
flowchart TD
    A[Validated request] --> B[Deterministic router]
    B -->|NOT_APPLICABLE| C[Terminal NOT_APPLICABLE]
    B -->|NO_ELIGIBLE_POLICY| J[Terminal evidence-need state]
    B -->|APPLICABLE| D{Corpus lokal sesuai manifest?}
    D -->|No| E[CORPUS_STALE]
    D -->|Yes| F[Retrieve and assess]
    F -->|READY| G[Stop READY]
    F -->|Retry recommended and attempt less than 2| H[Deterministic retry query]
    H --> F
    F -->|Otherwise| I[Stop NOT_READY]
~~~

core/evidence_workflow_v3.py menjalankan satu workflow per evidence need. Satu workflow memiliki maksimum dua retrieval attempt total; evidence antar-attempt digabung kumulatif dan dideduplikasi sebelum assessment ulang. Router dan eligibility tidak melebar pada retry.

## 9. Human Approval dan Gemini Guard

Product aggregate hanya ready bila setiap workflow applicable READY, terdapat evidence pool eligible, dan tidak ada blocker seperti corpus stale. NOT_APPLICABLE tidak dinilai insufficient.

Approval disimpan melalui gemini_approval_fingerprint, yaitu fingerprint analysis saat pengguna menyetujui penggunaan Gemini. Bila dataset/input atau analysis context berubah, reset_analysis_results() membersihkan evidence workflow v3, evidence pool, readiness, Gemini evidence, approval fingerprint, Gemini result, traceability, report, dan state turunan yang stale.

core/evidence_sanitizer.py membatasi Gemini-facing evidence:

- maksimum 5 item;
- maksimum 300 karakter per string;
- chunk ID, source, dan page tetap tersedia;
- item dideduplikasi dan harus eligible.

execute_decision() menolak Gemini bila action/stage tidak valid, approval belum ada, policy evidence kosong, sufficiency legacy belum sufficient, atau workflow v3 belum ready. UI menjaga result pada fingerprint yang sama agar rerun tidak memanggil Gemini berulang.

## 10. Gemini Responsibility Boundary

llm/gemini_client.py memakai schema GeminiAnalysis untuk output terstruktur.

Gemini boleh:

- merangkum profile, metadata, dan finding yang diberikan;
- menjelaskan prioritas dan rekomendasi human review;
- membedakan finding deterministik dari interpretasi;
- menggunakan citation supplied dengan chunk ID, source, dan page.

Gemini tidak boleh:

- menghasilkan finding authoritative baru;
- mengubah severity, count, percentage, atau wording ketidakpastian finding;
- menyatakan rule pack tidak aktif bila payload menunjukkan aktif;
- menyatakan evidence domain tidak tersedia bila supplied evidence memuat domain yang sama;
- membuat legal/compliance verdict;
- membuat rule runtime, melakukan CSV repair, atau memanggil retrieval;
- memperlakukan policy evidence atau sufficiency sebagai proof of compliance.

API key dibaca dari environment hanya saat Gemini dipanggil; API key tidak disimpan di source atau report.

## 11. Citation dan Traceability

core/evidence_reviewer.py menjalankan review_evidence_traceability() setelah Gemini mengembalikan citations.

~~~text
Gemini citation
    -> chunk ID diperiksa terhadap supplied eligible evidence
    -> source/page dibandingkan dengan identity chunk
    -> valid_references atau invalid_references
    -> traceability_score dan status review
~~~

Citation valid harus menggunakan chunk ID supplied dengan identity source/page yang cocok. Citation unknown, missing identity, atau ineligible dicatat sebagai invalid. Traceability memverifikasi hubungan citation ke evidence yang tersedia, bukan kebenaran legal atau substansi interpretasi Gemini.

## 12. Agent State Machine

core/agent_models.py mendefinisikan stage berikut.

| Stage | Arti | Kondisi umum | Next action umum |
| --- | --- | --- | --- |
| INGESTION_REQUIRED | CSV belum tersedia. | Belum ingestion. | NONE |
| QUALITY_REQUIRED | Profil/check/score belum lengkap. | Ingestion sukses. | RUN_QUALITY_PIPELINE |
| METADATA_REQUIRED | Metadata belum lengkap/divalidasi. | Quality selesai. | VALIDATE_METADATA atau NONE |
| CONTEXTUAL_VALIDATION_REQUIRED | Contextual validation belum dijalankan. | Metadata Lengkap. | RUN_CONTEXTUAL_VALIDATION |
| EVIDENCE_REQUIRED | Evidence belum diretrieve atau retry tersedia. | Contextual selesai. | RETRIEVE_POLICY_EVIDENCE / RETRY_POLICY_RETRIEVAL |
| EVIDENCE_REVIEW_REQUIRED | Evidence applicable belum siap. | Insufficient, not-ready, atau error. | EVALUATE_EVIDENCE atau NONE |
| ANALYSIS_READY | Evidence siap tetapi membutuhkan approval. | V3 ready. | RUN_GEMINI_ANALYSIS |
| TRACEABILITY_REQUIRED | Gemini selesai, traceability belum direview. | Gemini ada. | REVIEW_TRACEABILITY |
| REPORT_REQUIRED | Report belum dibangun. | Traceability selesai. | BUILD_REPORT |
| COMPLETE | Workflow selesai. | Report selesai atau all v3 workflow NOT_APPLICABLE. | NONE |
| ERROR | Ada error eksplisit. | error_message terisi. | NONE |

Perubahan v0.3.5 pada plan_next_action() menetapkan COMPLETE + NONE bila evidence_workflow_v3_completed=true dan state aggregate yang diteruskan adalah NOT_APPLICABLE. Tidak ada blocking condition atau human action; Gemini tidak executable karena tidak ada action Gemini maupun evidence eligible. Deterministic report tetap dapat dibangun tanpa Gemini.

Hal ini berbeda dari applicable evidence yang EMPTY, NOT_READY, CORPUS_STALE, insufficient/partial, atau READY tetapi belum approved. State tersebut bukan COMPLETE. NO_ELIGIBLE_POLICY juga terminal untuk evidence need/workflow, tetapi tidak dipropagasikan sebagai all-NOT_APPLICABLE dan tidak otomatis menjadikan keseluruhan agent COMPLETE.

~~~mermaid
stateDiagram-v2
    [*] --> INGESTION_REQUIRED
    INGESTION_REQUIRED --> QUALITY_REQUIRED
    QUALITY_REQUIRED --> METADATA_REQUIRED
    METADATA_REQUIRED --> CONTEXTUAL_VALIDATION_REQUIRED
    CONTEXTUAL_VALIDATION_REQUIRED --> EVIDENCE_REQUIRED
    EVIDENCE_REQUIRED --> EVIDENCE_REVIEW_REQUIRED
    EVIDENCE_REVIEW_REQUIRED --> ANALYSIS_READY: evidence ready
    EVIDENCE_REVIEW_REQUIRED --> COMPLETE: all NOT_APPLICABLE
    ANALYSIS_READY --> TRACEABILITY_REQUIRED: approved Gemini completed
    TRACEABILITY_REQUIRED --> REPORT_REQUIRED
    REPORT_REQUIRED --> COMPLETE
~~~

## 13. Fingerprint dan State Invalidation

build_analysis_fingerprint() di core/analysis_state.py membangun fingerprint deterministik dari content/metadata input dan analysis-context fingerprint.

Analysis context mencakup selected domain, governance context, domain profile, concept registry fingerprint, rule registry fingerprint, serta policy registry fingerprint. Bila input atau context berubah, update_analysis_fingerprint() memanggil reset_analysis_results() sekali untuk membersihkan state turunan.

Approval valid hanya bila gemini_approval_fingerprint sama dengan current_fingerprint. Karena itu approval lama tidak dapat mengizinkan Gemini untuk dataset, context, registry semantics, atau evidence state yang sudah berubah.

## 14. Report Generation

core/report_builder.py menghasilkan report JSON schema_version 1.1. Builder menerima snapshot eksplisit: profile, findings, score, metadata validation, contextual validation, policy evidence, sufficiency, attempts, Gemini result, evidence review, ingestion, analysis context, dan v3 evidence state.

core/report_provenance.py membangun v3_metadata berisi:

- analysis context dan registry fingerprints;
- domain rule execution serta rule provenance;
- policy evidence eligible yang bounded;
- summary evidence need, applicability, stop reason, sufficiency, alignment, dan readiness;
- human approval, Gemini execution, traceability, dan limitations.

Report dapat dibangun tanpa Gemini dan tidak memuat raw PDF, embedding vector, API key, raw session state, atau DataFrame penuh. Report bukan certification report.

## 15. Error dan Safe-Failure Behavior

| Kondisi | Perilaku |
| --- | --- |
| CSV kosong/tidak dapat diparsing | CsvIngestionError dengan diagnostics jelas. |
| Malformed row | Ditolak pada strict; dapat dilewati dan dicatat pada warn. |
| Missing/ambiguous concept | Rule di-skip dengan state eksplisit. |
| NO_ELIGIBLE_POLICY | Terminal untuk evidence need/workflow tanpa policy eligible; bukan otomatis completion keseluruhan agent. |
| NOT_APPLICABLE | Chroma tidak di-query; tidak disamakan dengan insufficient. |
| EMPTY | Retrieval applicable tanpa evidence; readiness tidak tercapai dan retry dapat dipertimbangkan. |
| CORPUS_STALE | Retrieval berhenti; tidak ada auto-rebuild. |
| Insufficient/partial evidence | Gemini diblokir hingga ready atau workflow berhenti. |
| Gemini gagal/tidak tersedia | Error terstruktur; deterministic result tidak diubah. |
| Citation invalid | Dicatat sebagai invalid reference oleh reviewer deterministik. |
| Semua workflow NOT_APPLICABLE | Completion deterministik tanpa approval/Gemini path. |

Rule evaluator error ditangkap sebagai state per-rule agar satu evaluator tidak menjatuhkan generic checks. Registry/evaluator invalid ditolak deterministik, bukan dieksekusi secara dinamis.

## 16. Testing Architecture

Kategori test repository meliputi:

- unit ingestion, profiling, quality, metadata, context, registry, dan scoring;
- contract Concept/Rule/Policy Registry serta Chroma metadata;
- domain rule parity healthcare dan pilot education/environment;
- corpus manifest, routing, retrieval, assessment, dan bounded workflow;
- product evidence, approval gate, invalidation, Gemini/traceability contract, dan report provenance;
- Streamlit AppTest, cross-domain acceptance, dan final hardening v0.3.5.

Baseline v0.3.5: **364 passed** dan **137 known warnings**. Warning berasal dari deprecation/compatibility Pydantic yang dipancarkan Chroma pada test contract/ingestion/retrieval; suite tetap pass.

## 17. Manual Acceptance Matrix

| Skenario | Status | Komponen utama |
| --- | --- | --- |
| Healthcare + Government/Public | PASS | healthcare_core, routing healthcare, readiness, approval, traceability. |
| Education + Government/Public | PASS | education_core heuristic, concept resolution, isolation. |
| Environment + Government/Public | PASS | environment_core heuristic, generic measurement concept, isolation. |
| Generic + Government/Public | PASS | generic checks, governance routing, report tanpa pack sektoral. |
| Generic + Non-Government | PASS | all policy evidence NOT_APPLICABLE, tanpa retrieval applicable/Gemini. |

Ini adalah acceptance teknis/manual prototype, bukan certification atau qualification produksi.

## 18. Design Decisions

### Mengapa deterministic-first?

Kualitas CSV, metadata completeness, dan relasi kolom dapat diperiksa repeatable oleh Pandas dan evaluator allowlisted. Menaruhnya di LLM membuat count, severity, dan audit trail kurang stabil.

### Mengapa domain dipilih eksplisit?

Nama kolom dapat ambigu dan dataset lintas-domain dapat memiliki vocabulary serupa. DomainId eksplisit mencegah auto-detection yang tidak dapat diaudit dan mencegah rule/policy lintas-domain aktif tidak sengaja.

### Mengapa retrieval tidak unrestricted?

Router membatasi policy pada registry, pack, domain, governance context, effective status, verification state, serta metadata scalar. Ini mencegah raw filter user menjadi bagian dari execution path dan mengurangi leakage.

### Mengapa Gemini membutuhkan approval?

Evidence readiness adalah heuristic kualitas evidence, bukan izin penggunaan LLM. Approval yang terikat fingerprint mencegah state lama memberi otorisasi implisit.

### Mengapa sufficiency dan retry dibatasi?

Dua attempt membatasi biaya dan menjaga query refinement tetap deterministik serta auditable, bukan search loop tanpa batas.

### Mengapa traceability setelah Gemini?

Citation adalah output Gemini. Reviewer membandingkannya dengan exact evidence pool yang disuplai, bukan corpus global atau kemiripan judul.

### Mengapa NOT_APPLICABLE eksplisit?

Tidak adanya policy evidence yang tepat diterapkan berbeda dari retrieval gagal. All-NOT_APPLICABLE menjadi completion agar sistem tidak meminta approval yang tidak dapat membuat policy menjadi applicable, tanpa menyatakan dataset valid.

## 19. Known Technical Limitations

- Duplicate identifier memakai heuristic nama kolom. Entity/reference identifier seperti id_sensor pada data time-series dapat berulang valid tetapi masih berpotensi ditandai duplicate identifier.
- Numeric outlier IQR adalah sinyal statistik, bukan bukti otomatis nilai invalid.
- Education dan environment adalah pilot rule pack heuristic yang membutuhkan human review.
- Corpus baseline terbatas pada enam policy lokal terdaftar/terverifikasi; tidak ada policy discovery web otomatis saat runtime.
- Mode chunked belum true out-of-core dan finding sampled hanya berlaku bagi sampel.
- Tidak ada automatic CSV repair.
- Gemini memerlukan API key dan jaringan; deterministic report tetap tersedia tanpa Gemini.
- Evidence sufficiency dan traceability bukan ukuran legal sufficiency, correctness hukum, atau compliance.

## 20. Future Development

Roadmap yang tidak mengubah baseline saat ini:

- schema semantics eksplisit untuk record_key versus entity_reference;
- rule pack lebih luas dengan policy/technical standard yang benar-benar diverifikasi;
- lifecycle/version management corpus yang lebih kaya;
- analisis true out-of-core untuk dataset besar;
- explainability layer yang membaca output MetaGuard tanpa menggantikan deterministic engine.

## 21. Kesimpulan Arsitektur

MetaGuard v0.3.5 menggabungkan deterministic review engine, validasi domain-aware, RAG policy-grounded lokal, Gemini terkontrol, approval manusia, dan traceability citation. Batas antar-layer dibuat eksplisit agar finding teknis, evidence, dan interpretasi AI tidak mengambil peran yang tidak semestinya.
