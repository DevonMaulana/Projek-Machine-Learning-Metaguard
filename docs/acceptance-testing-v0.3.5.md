# Acceptance Testing MetaGuard v0.3.5

## 1. Tujuan

Dokumen ini merangkum acceptance testing final MetaGuard v0.3.5 pada kombinasi domain dan governance context utama. Fokusnya adalah bukti bahwa workflow deterministic review, policy evidence, human approval, Gemini guard, traceability, dan report berjalan sesuai scope prototype.

Dokumen ini bukan test specification lengkap, sertifikasi formal, legal/compliance testing, maupun production qualification.

## 2. Baseline Sistem

| Item | Baseline |
| --- | --- |
| Version | v0.3.5 |
| Automated regression | 364 passed |
| Known warnings | 137 |
| Report schema | 1.1 |
| Policy corpus collection | metaguard_policies_v3 |
| Domain IDs | generic, healthcare, education, environment, other |
| Governance contexts | government_public, generic_non_government |

Baseline ini merujuk pada source, registry, test suite, README, dan technical architecture documentation yang tersedia pada repository v0.3.5.

## 3. Acceptance Matrix

| ID | Scenario | Expected | Result | Status |
| --- | --- | --- | --- | --- |
| AC-01 | Healthcare + Government/Public | Healthcare rule pack dan policy route sektoral terisolasi. | Kontrak rule, routing, evidence, approval, dan traceability tercakup oleh test/source. | PASS |
| AC-02 | Education + Government/Public | Education pilot heuristic aktif dan tidak menjalankan pack lain. | Kontrak concept resolution, rule, provenance, dan isolation tercakup. | PASS |
| AC-03 | Environment + Government/Public | Environment pilot heuristic memakai konsep measurement generik dan terisolasi. | Kontrak resolver, rule, provenance, dan routing environment tercakup. | PASS |
| AC-04 | Generic + Government/Public | Generic checks aktif tanpa pack sektoral; evidence governance dapat dirutekan. | Kontrak generic fallback, governance route, dan report tercakup. | PASS |
| AC-05 | Generic + Non-Government | Evidence pemerintah tidak dipaksakan; all NOT_APPLICABLE selesai deterministik. | Kontrak router, workflow, agent terminal state, report, dan Gemini guard tercakup. | PASS |

Tidak ada angka finding manual yang dicantumkan karena acceptance fixture tidak diposisikan sebagai satu dataset produksi tetap. Result di atas menyatakan kontrak behavior yang diuji, bukan jumlah finding dari data operasional tertentu.

## 4. AC-01 — Healthcare + Government/Public

### Expected behavior

- selected_domain healthcare mengaktifkan healthcare_core.
- HEALTH-BED-CAPACITY-001 dievaluasi bila occupied_beds dan inpatient_capacity berhasil di-resolve.
- HEALTH-INTERNET-BANDWIDTH-001 dievaluasi bila internet_status dan bandwidth_mbps tersedia.
- Generic quality checks tetap aktif.
- Domain semantic evidence healthcare dapat eligible pada government_public.
- Education/environment rule tidak berjalan.
- Evidence readiness dan approval mengontrol Gemini.
- Citation traceability hanya memakai evidence supplied yang eligible.

### Hasil

Kontrak di atas tercakup oleh test domain rule engine, contextual validation, policy router/retrieval v3, product evidence, traceability, dan report provenance. Status acceptance: **PASS**.

### Catatan

HEALTH-BED-CAPACITY-001 berprovenance DETERMINISTIC_INVARIANT. HEALTH-INTERNET-BANDWIDTH-001 berprovenance HEURISTIC dan membutuhkan human review; keduanya bukan verdict compliance.

## 5. AC-02 — Education + Government/Public

### Expected behavior

- selected_domain education mengaktifkan education_core.
- EDU-STUDENT-TEACHER-001 dapat mengevaluasi student_count dan teacher_count.
- EDU-STUDENT-CLASSROOM-001 dapat mengevaluasi student_count dan classroom_count.
- Alias education seperti jumlah_siswa dan jumlah_ruang_kelas dapat di-resolve secara exact-normalized.
- Kedua rule merupakan HEURISTIC dengan human_review_required.
- Healthcare/environment rule tidak berjalan.
- domain_semantic_support education dapat dirutekan ke policy pack education sesuai registry.

### Hasil

Test registry, domain rule engine, contextual validation, router, report provenance, dan cross-domain acceptance mencakup kontrak tersebut. Status acceptance: **PASS**.

## 6. AC-03 — Environment + Government/Public

### Expected behavior

- selected_domain environment mengaktifkan environment_core.
- ENV-SENSOR-MEASUREMENT-001 memakai sensor_status serta salah satu measurement concept optional yang ter-resolve.
- environment_measurement dapat meresolusikan nilai_pengukuran tanpa menyatakan kolom generik tersebut sebagai pH.
- Status offline, nonaktif, atau tidak aktif dengan pengukuran numerik pada baris sama dapat menghasilkan finding heuristic.
- Healthcare/education rule tidak berjalan.
- domain_semantic_support environment dapat dirutekan ke policy pack environment sesuai registry.

### Hasil

Test concept registry, domain rule engine, contextual validation, router, report provenance, dan cross-domain acceptance mencakup kontrak tersebut. Status acceptance: **PASS**.

### Catatan limitation

Duplicate identifier adalah heuristic generic berbasis nama kolom. Entity/reference ID seperti id_sensor dalam dataset time-series dapat berulang secara valid namun masih berpotensi ditandai. Limitation ini terpisah dari evaluasi ENV-SENSOR-MEASUREMENT-001.

## 7. AC-04 — Generic + Government/Public

### Expected behavior

- Tidak ada rule pack healthcare, education, atau environment yang aktif.
- Generic deterministic quality checks tetap aktif.
- Evidence governance yang eligible dapat dirutekan ke government_generic.
- Tidak ada leakage rule atau evidence sektoral.
- Deterministic report dapat dibangun.
- Gemini tetap opsional dan hanya boleh berjalan jika evidence ready serta approval terpenuhi.

### Hasil

Domain profile, router, cross-domain acceptance, report provenance, product evidence, dan approval-guard test mencakup behavior tersebut. Status acceptance: **PASS**.

## 8. AC-05 — Generic + Non-Government

### Expected behavior

- Tidak ada domain-specific rule pack yang aktif; generic quality checks tetap aktif.
- Kebijakan pemerintah tidak dipaksakan untuk generic_non_government.
- Evidence need pemerintah dapat seluruhnya berstatus NOT_APPLICABLE.
- Tidak ada policy retrieval yang applicable.
- Gemini tidak executable.
- Deterministic report tetap dapat dibangun.
- Agent decision adalah COMPLETE dengan next action NONE.
- Tidak ada blocking condition dan human action tidak diperlukan.

### Hasil

Test policy router dan evidence workflow membuktikan NOT_APPLICABLE tanpa retrieval. Test final hardening v0.3.5 membuktikan aggregate all-NOT_APPLICABLE menjadi COMPLETE/NONE, tidak memanggil mock Gemini, dan report tetap buildable. Status acceptance: **PASS**.

NOT_APPLICABLE berbeda dari retrieval failure. State ini menyatakan evidence kebijakan tidak tepat diterapkan pada context tersebut, bukan evidence kurang atau data valid.

## 9. Cross-Domain Isolation

Acceptance mencakup isolasi berikut:

| Selected domain | Pack yang boleh aktif | Pack yang tidak boleh aktif |
| --- | --- | --- |
| healthcare | healthcare_core | education_core, environment_core |
| education | education_core | healthcare_core, environment_core |
| environment | environment_core | healthcare_core, education_core |
| generic | tidak ada pack sektoral | seluruh pack sektoral |
| other | tidak ada pack sektoral | seluruh pack sektoral |

Domain dipilih eksplisit oleh pengguna. Tidak ada inferensi domain otomatis oleh LLM atau fallback fuzzy lintas-domain.

## 10. Evidence Workflow Acceptance

Evidence workflow memisahkan routing applicability, retrieval outcome, sufficiency/alignment, dan readiness.

| Kelompok state | State yang dicakup | Arti acceptance |
| --- | --- | --- |
| Routing | APPLICABLE, NOT_APPLICABLE, NO_ELIGIBLE_POLICY | Eligibility berasal dari registry/context tervalidasi. |
| Retrieval | SUCCESS, EMPTY, CORPUS_STALE, NOT_APPLICABLE | Hasil retrieval tidak disamakan dengan applicability. |
| Workflow | READY, NOT_READY, NOT_APPLICABLE, CORPUS_STALE, NO_ELIGIBLE_POLICY | Stop reason dan readiness dinyatakan eksplisit. |

Contract yang diterima:

- Evidence applicable harus melalui sufficiency dan alignment sebelum ready.
- Retrieval maksimal dua attempt total per evidence need.
- Duplicate chunk ID tidak meningkatkan unique evidence, diversity, sufficiency, atau readiness.
- NOT_APPLICABLE tidak dinilai sebagai insufficient.
- NO_ELIGIBLE_POLICY adalah terminal untuk evidence need/workflow, tetapi bukan otomatis COMPLETE untuk seluruh agent.
- All evidence workflow NOT_APPLICABLE dapat menjadi completion deterministik sesuai hardening v0.3.5.

## 11. Gemini dan Human Approval Acceptance

Acceptance memastikan bahwa:

- Gemini bersifat optional.
- Evidence harus ready sebelum Gemini tersedia sebagai action.
- Explicit human approval diperlukan.
- Approval terikat pada analysis fingerprint.
- Perubahan input atau context menginvalidasi approval/result stale.
- Unchanged approved state dibatasi oleh single-call guard.
- Gemini menerima deterministic findings dan bounded eligible evidence.
- Gemini bukan sumber authoritative finding dan tidak dapat membuat compliance verdict.

Automated acceptance menggunakan mock; dokumen ini tidak mencatat atau menjalankan panggilan Gemini baru.

## 12. Traceability Acceptance

Citation Gemini diuji terhadap evidence yang benar-benar supplied:

1. chunk ID harus dikenal dan eligible;
2. source/page dibandingkan dengan identity evidence;
3. citation known dan cocok dicatat valid;
4. chunk ID tidak dikenal atau identity yang tidak cocok dicatat invalid.

Traceability score memeriksa hubungan citation dengan supplied evidence. Ia tidak membuktikan legal correctness atau substansi interpretasi Gemini.

## 13. Automated Regression

Baseline automated regression v0.3.5:

| Hasil | Nilai |
| --- | --- |
| Passed | 364 |
| Known warnings | 137 |
| Status | PASS |

Coverage dikelompokkan pada ingestion/profile/quality, metadata/context, registry, domain rules, RAG/corpus/retrieval, evidence workflow, approval/Gemini guard, traceability/report, Streamlit, cross-domain acceptance, dan final hardening.

Known warnings berasal dari deprecation/compatibility Pydantic yang dipancarkan dependency Chroma pada test contract, ingestion, dan retrieval. Warning tersebut bukan failed test.

## 14. Acceptance Result Summary

| Acceptance area | Status |
| --- | --- |
| Healthcare + Government/Public | PASS |
| Education + Government/Public | PASS |
| Environment + Government/Public | PASS |
| Generic + Government/Public | PASS |
| Generic + Non-Government | PASS |
| Automated Regression | PASS |

**Overall: PASS** untuk technical/coursework acceptance baseline MetaGuard v0.3.5.

Status ini tidak menyatakan production-ready, certified, compliant, atau correctness 100 persen.

## 15. Known Limitations Selama Acceptance

- Duplicate identifier memakai heuristic nama kolom dan dapat salah membaca entity/reference identifier.
- Numeric outlier IQR adalah signal verifikasi, bukan bukti data invalid.
- Education dan environment adalah pilot rule pack heuristic yang memerlukan human review.
- Corpus kebijakan baseline terbatas pada enam policy lokal yang terdaftar dan diverifikasi.
- Evidence sufficiency adalah heuristic MetaGuard, bukan legal score.
- Gemini membutuhkan layanan eksternal/API key bila digunakan.
- Mode chunked belum true out-of-core.
- Finding mode sampled hanya berlaku untuk scope sampel yang dianalisis.

## 16. Conclusion

Acceptance v0.3.5 menunjukkan workflow utama MetaGuard berjalan konsisten sesuai scope prototype/coursework pada domain dan governance context yang diuji. Batas deterministic review, policy evidence, human approval, Gemini, traceability, serta limitation sistem tetap eksplisit.

