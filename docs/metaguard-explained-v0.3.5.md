# Memahami MetaGuard v0.3.5

## 1. MetaGuard dalam Satu Kalimat

MetaGuard adalah sistem review awal kualitas data berbasis deterministic-first: ia memeriksa dataset CSV, memakai konteks domain yang dipilih pengguna, menghubungkan hasil dengan evidence kebijakan lokal yang relevan, lalu menggunakan Gemini secara terbatas setelah approval manusia.

AI bukan sumber utama finding. Finding teknis utama berasal dari pemeriksaan kode dan rule deterministik.

## 2. Masalah Apa yang Ingin Diselesaikan?

Sebuah CSV dapat terlihat rapi, tetapi tetap mempunyai masalah:

- kolom penting kosong;
- nilai persentase di luar rentang yang wajar;
- tanggal tidak dapat dikenali;
- baris atau identifier berulang;
- metadata tidak lengkap;
- data tampak normal secara umum, tetapi tidak konsisten dalam konteks domain;
- evidence kebijakan dipakai tanpa batas atau tanpa diketahui asalnya;
- AI diminta menyimpulkan sesuatu tanpa kontrol.

MetaGuard membantu melakukan review awal sebelum data digunakan lebih lanjut. Ia bukan pengganti auditor, pemilik data, atau reviewer domain.

## 3. Gambaran Cara Kerja Paling Sederhana

Alur sederhananya adalah:

~~~text
Dataset
  -> Bisa dibaca?
  -> Ada masalah teknis?
  -> Konteks/domain data apa?
  -> Ada masalah domain-specific?
  -> Evidence kebijakan apa yang relevan?
  -> Evidence cukup untuk review?
  -> Manusia menyetujui penggunaan AI?
  -> Gemini menjelaskan
  -> Citation dapat ditelusuri?
  -> Report atau completion
~~~

Setiap pertanyaan memiliki fungsi berbeda:

| Pertanyaan | Jawaban diberikan oleh |
| --- | --- |
| Bisa dibaca? | CSV ingestion dan diagnostics |
| Ada masalah teknis? | Generic quality checks deterministik |
| Konteksnya apa? | Pilihan domain dan governance pengguna |
| Ada masalah domain? | Concept resolution dan domain rule engine |
| Evidence apa yang relevan? | Policy router dan corpus lokal |
| Evidence cukup? | Sufficiency dan alignment |
| Boleh memakai AI? | Evidence readiness dan approval manusia |
| Citation benar-benar berasal dari evidence? | Traceability reviewer |

## 4. Lima Lapisan MetaGuard

~~~mermaid
flowchart TD
    A[Dataset CSV] --> B[1. Data Quality Engine]
    B --> C[2. Context dan Domain]
    C --> D[3. Policy-Grounded RAG]
    D --> E[4. Controlled AI]
    E --> F[5. Audit dan Reporting]
    G[Agent Orchestrator] -. mengatur tahap .-> B
    G -. mengatur tahap .-> C
    G -. mengatur tahap .-> D
    G -. mengatur tahap .-> E
    G -. mengatur tahap .-> F
~~~

| Lapisan | Input | Output | Siapa yang menentukan hasil utama? |
| --- | --- | --- | --- |
| Data Quality Engine | CSV | Finding teknis dan score | Kode deterministik |
| Context dan Domain | Metadata, domain, governance | Context dan rule yang aktif | Pengguna + registry |
| Policy-Grounded RAG | Evidence need dan context | Evidence kebijakan eligible | Router dan retrieval terkontrol |
| Controlled AI | Finding deterministik + evidence siap | Interpretasi terstruktur | Gemini, setelah approval |
| Audit dan Reporting | Semua state yang relevan | Traceability dan report JSON | Reviewer deterministik + builder |

Agent Orchestrator adalah pengatur workflow. Ia bukan AI yang bebas memutuskan tindakan; ia bekerja seperti koordinator yang hanya memilih langkah dari daftar action yang diizinkan.

## 5. Tahap 1 — CSV Ingestion

Setelah CSV di-upload, MetaGuard belum memanggil Gemini. Sistem terlebih dahulu memeriksa apakah berkas dapat diterima dengan aman.

Yang diperiksa antara lain:

- encoding;
- delimiter;
- quote character;
- header;
- jumlah field antarbaris;
- malformed row;
- duplicate atau unnamed header;
- jumlah row dan column hasil parsing.

Analogi sederhananya adalah petugas penerimaan berkas: sebelum isi dokumen ditinjau, petugas memastikan berkas dapat dibuka dan halaman-halamannya tidak rusak.

MetaGuard mendukung tiga cara analisis:

| Mode | Penjelasan sederhana |
| --- | --- |
| exact | Seluruh data dibaca dan diperiksa. |
| chunked | Data dibaca bertahap, lalu masih digabung untuk pemeriksaan global. |
| sampled | Sampel deterministik diperiksa bila seluruh data tidak dianalisis. |

Mode chunked belum berarti pemrosesan true out-of-core. Hasil mode sampled hanya mewakili sampel yang dianalisis.

## 6. Tahap 2 — Generic Quality Check

Generic quality check berlaku untuk semua domain. Contoh pemeriksaannya:

- missing value;
- whitespace atau empty string;
- duplicate identifier;
- tanggal invalid atau format tanggal tidak konsisten;
- angka negatif;
- persentase di luar 0–100;
- outlier numerik berbasis IQR;
- duplicate row;
- constant column;
- empty column.

Finding ini dibuat oleh checker deterministik berbasis Pandas. Gemini tidak menemukan atau menghitung finding tersebut.

Quality score adalah ringkasan kualitas menurut aturan MetaGuard. Score bukan compliance score, tidak menyatakan data sah secara hukum, dan tidak menggantikan review manusia.

## 7. Tahap 3 — Metadata

Angka tanpa metadata dapat mudah disalahartikan. Nilai 150, misalnya, bisa berarti 150 pasien, 150 Mbps, 150 sekolah, atau 150 unit yang lain.

Karena itu MetaGuard memeriksa metadata seperti:

- title dan description;
- producer OPD;
- data period;
- geographic scope;
- measurement unit;
- update frequency;
- responsible unit;
- publication purpose.

Metadata membantu sistem dan reviewer memahami apa yang sedang diperiksa. Metadata lengkap bukan jaminan data benar, tetapi metadata yang tidak lengkap membuat review berikutnya kurang bermakna.

## 8. Tahap 4 — Domain dan Governance Context

Domain menjawab pertanyaan: **dataset ini berada di bidang apa?**

Governance context menjawab pertanyaan: **dataset ini digunakan dalam konteks tata kelola apa?**

Domain yang tersedia:

- generic;
- healthcare;
- education;
- environment;
- other.

Governance context yang tersedia:

- government_public;
- generic_non_government.

Keduanya dipilih pengguna secara eksplisit. MetaGuard tidak menebak domain dari nama kolom dan tidak meminta LLM untuk menebak. Hal ini mencegah rule healthcare, education, atau environment berjalan pada dataset yang salah.

## 9. Tahap 5 — Concept Resolution

Concept resolution dapat dibayangkan sebagai kamus istilah internal MetaGuard.

Satu konsep dapat mempunyai beberapa nama kolom CSV yang wajar. Contohnya:

~~~text
jumlah_siswa       -> student_count
jumlah_ruang_kelas -> classroom_count
nilai_pengukuran   -> environment_measurement
~~~

Rule bekerja pada konsep seperti student_count atau environment_measurement, bukan hanya pada satu nama kolom yang di-hard-code.

Pencocokan dilakukan secara exact setelah normalisasi sederhana, misalnya perbedaan huruf besar/kecil atau spasi/underscore. MetaGuard tidak memakai fuzzy matching, sehingga hasilnya lebih mudah diaudit. Bila konsep tidak ditemukan atau ambigu, rule di-skip secara eksplisit.

## 10. Tahap 6 — Domain Rule Engine

Generic quality check dan domain validation tidak sama.

Generic quality check bertanya: apakah ada masalah umum pada isi CSV?

Domain rule engine bertanya: apakah hubungan antar-konsep tertentu tampak tidak konsisten dalam domain yang dipilih?

Contoh healthcare:

- occupied beds tidak boleh melebihi inpatient capacity;
- status tanpa internet dengan bandwidth positif dapat menjadi potential inconsistency.

Dua provenance penting:

| Provenance | Cara membacanya |
| --- | --- |
| DETERMINISTIC_INVARIANT | Hubungan konsistensi yang diperlakukan MetaGuard sebagai invariant data. |
| HEURISTIC | Sinyal yang perlu diperiksa manusia. |

HEURISTIC berarti **perlu diperiksa**, bukan **data pasti salah** atau **melanggar aturan**.

Contoh pilot lain:

- Education: siswa positif dengan guru nol, atau kelas nol.
- Environment: sensor offline/nonaktif tetapi ada pengukuran numerik pada baris yang sama.

Pilot education dan environment sengaja konservatif dan selalu meminta human review.

## 11. Tahap 7 — Policy Evidence dan RAG

RAG dapat dipahami sebagai cara mencari potongan dokumen lokal yang relevan, bukan meminta AI mengingat aturan dari internet.

Alurnya:

~~~text
PDF kebijakan lokal
  -> diekstrak per halaman
  -> dipecah menjadi chunk
  -> diubah menjadi embedding lokal
  -> disimpan di Chroma
  -> diambil hanya saat evidence need dan context sesuai
~~~

MetaGuard memakai corpus lokal v3 dengan collection metaguard_policies_v3. Policy Router menentukan policy pack dan policy ID yang eligible dari domain, governance context, dan evidence need.

Ini bukan pencarian web bebas. Router tidak menerima filter mentah dari pengguna, Gemini tidak menulis ulang query secara bebas, dan tidak ada fallback lintas-domain yang tidak terkontrol.

## 12. Tahap 8 — Evidence Sufficiency

Evidence ditemukan tidak selalu berarti evidence cukup untuk workflow.

MetaGuard menilai:

- coverage: apakah evidence need yang diperlukan tercakup;
- unique evidence: apakah chunk unik yang tersedia cukup;
- source diversity: apakah evidence berasal dari source yang cukup beragam;
- alignment: apakah policy pack dan domain evidence sesuai dengan route.

Ringkasan teknis saat ini:

~~~text
coverage: 60 poin
unique evidence: 30 poin
source diversity: 10 poin
sufficient threshold: 85
partial threshold: 40
minimum unique chunk untuk sufficient: 2
~~~

Retrieval dibatasi maksimal dua attempt per evidence need. Evidence antar-attempt digabung dan dideduplikasi berdasarkan chunk ID.

Evidence sufficiency adalah heuristic kesiapan review MetaGuard, bukan legal sufficiency atau bukti compliance.

## 13. Tahap 9 — Human Approval

Alurnya adalah:

~~~text
Evidence READY
  -> Human approval eksplisit
  -> Gemini opsional
~~~

READY tidak berarti Gemini otomatis berjalan. Approval manusia adalah langkah terpisah dan terikat pada fingerprint analysis. Bila dataset atau context berubah, approval lama tidak boleh dipakai untuk menjalankan Gemini pada state baru.

## 14. Tahap 10 — Gemini

| Gemini BOLEH | Gemini TIDAK BOLEH |
| --- | --- |
| Merangkum finding yang diberikan. | Membuat finding teknis authoritative baru. |
| Menjelaskan konteks dan prioritas. | Mengubah severity, count, atau percentage. |
| Memberi rekomendasi human review. | Membuat legal/compliance verdict. |
| Mengutip evidence yang supplied. | Membuat rule saat runtime atau memperbaiki CSV. |
| Membedakan finding dan interpretasi. | Melakukan unrestricted retrieval. |

Gemini adalah interpretation layer, bukan decision engine. Ia menerima finding deterministik dan evidence eligible yang telah dibatasi; ia tidak menerima seluruh corpus atau CSV tanpa batas.

## 15. Tahap 11 — Traceability

Setelah Gemini memberi citation, MetaGuard memeriksanya:

~~~text
Gemini citation
  -> chunk ID
  -> source dan page
  -> supplied eligible evidence
  -> valid atau invalid
~~~

Contoh konseptual: bila Gemini menyebut chunk ID yang tidak pernah diberikan kepadanya, citation tersebut invalid meskipun judul policy terdengar benar.

Traceability 100 persen **bukan** berarti jawaban Gemini 100 persen benar. Artinya citation yang dipakai dapat ditelusuri ke evidence yang memang diberikan.

## 16. Tahap 12 — Agent Orchestrator

Agent Orchestrator dapat dibayangkan sebagai koordinator workflow.

Contoh state dan action:

~~~text
ANALYSIS_READY          -> RUN_GEMINI_ANALYSIS
TRACEABILITY_REQUIRED   -> REVIEW_TRACEABILITY
COMPLETE                -> NONE
~~~

Agentic di sini tidak berarti autonomous AI. MetaGuard memakai state machine dan allowlisted actions. Orchestrator tidak dapat membuat tool baru, menjalankan shell command dari input, atau memutuskan policy route tanpa aturan.

## 17. Mengapa Generic + Non-Government Penting?

Sistem juga harus tahu kapan AI tidak perlu digunakan.

Untuk generic + generic_non_government, evidence kebijakan pemerintah dapat seluruhnya NOT_APPLICABLE:

~~~text
Policy pemerintah tidak applicable
  -> tidak ada policy retrieval yang applicable
  -> Gemini tidak executable
  -> deterministic review tetap selesai
  -> COMPLETE / NONE
~~~

NOT_APPLICABLE tidak sama dengan retrieval failure. Artinya evidence kebijakan tersebut memang tidak tepat diterapkan otomatis pada context itu; bukan berarti sistem gagal mencari evidence atau dataset otomatis valid.

## 18. Contoh Alur Healthcare

Contoh healthcare yang aman untuk dijelaskan tanpa mengarang angka adalah:

1. Pengguna memilih healthcare dan government_public.
2. CSV dibaca dan generic quality checks dijalankan.
3. Metadata diperiksa.
4. Concept resolver mencoba menemukan occupied beds, inpatient capacity, internet status, dan bandwidth.
5. healthcare_core berjalan bila konsep yang dibutuhkan tersedia.
6. Router dapat memilih evidence healthcare untuk domain semantic support dan policy governance untuk need yang sesuai.
7. Evidence dinilai untuk sufficiency serta alignment.
8. Jika READY, pengguna dapat memberi approval eksplisit.
9. Gemini dapat menginterpretasi finding dan evidence supplied.
10. Citation Gemini direview sebelum report final.

Bila konsep yang diperlukan tidak tersedia, rule tidak dipaksakan; state skip memberi tahu reviewer alasan rule tidak dievaluasi.

## 19. Apa yang Membuat MetaGuard Berbeda dari Chatbot?

| Chatbot biasa | MetaGuard |
| --- | --- |
| User memberi prompt. | User memberi dataset dan context eksplisit. |
| LLM dapat langsung menjawab. | Deterministic checks berjalan lebih dahulu. |
| Evidence dapat tidak jelas. | Evidence dirutekan dari corpus lokal yang terdaftar. |
| AI dapat berjalan langsung. | Approval manusia dan readiness menjadi guard. |
| Citation bisa hanya teks. | Citation diperiksa terhadap chunk ID supplied. |

MetaGuard bukan chatbot. Gemini hanya satu komponen opsional di dalam workflow review yang lebih besar.

## 20. Known Limitations dengan Bahasa Sederhana

- Duplicate identifier memakai heuristic nama kolom. ID entity seperti id_sensor pada data time-series bisa berulang secara valid tetapi masih dapat ditandai.
- Outlier IQR adalah sinyal untuk dicek, bukan bukti nilai pasti salah.
- Rule education dan environment masih pilot heuristic.
- Corpus kebijakan lokal terbatas; tidak ada discovery policy otomatis dari web.
- Mode chunked belum true out-of-core dan hasil sampled hanya berlaku untuk sampel.
- Gemini membutuhkan layanan eksternal/API key bila digunakan.
- MetaGuard tidak memperbaiki CSV secara otomatis.

## 21. Analogi MetaGuard

Bayangkan MetaGuard sebagai tim pemeriksa berkas:

| Peran analogi | Komponen MetaGuard |
| --- | --- |
| Penerima berkas | CSV ingestion |
| Auditor data | Generic quality checks |
| Petugas bidang | Domain dan governance context |
| Kamus internal | Concept Registry |
| Spesialis bidang | Domain Rule Engine |
| Petugas dokumentasi | Policy RAG dan Router |
| Supervisor evidence | Sufficiency dan alignment |
| Manusia penanggung jawab | Human approval |
| Konsultan | Gemini |
| Auditor akhir | Traceability reviewer |
| Koordinator | Agent Orchestrator |

Intinya: MetaGuard tidak meminta satu AI melakukan semuanya; setiap tahap memiliki peran dan batas yang jelas.

## 22. Ringkasan yang Harus Diingat

Mental model MetaGuard:

~~~text
Deterministic
  -> Domain
  -> Evidence
  -> Approval
  -> Gemini
  -> Traceability
~~~

MetaGuard adalah alat bantu review kualitas data yang menempatkan finding deterministik, context eksplisit, evidence terkontrol, dan penilaian manusia sebelum interpretasi AI.

