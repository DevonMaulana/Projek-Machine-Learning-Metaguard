# Panduan Demo MetaGuard v0.3.5

## 1. Tujuan Demo

Tujuan demo bukan memperlihatkan semua detail implementation. Tujuannya adalah menunjukkan cara kerja dan alasan desain MetaGuard:

- finding utama berasal dari pemeriksaan deterministik;
- domain dan governance context dipilih eksplisit;
- evidence kebijakan dirutekan secara terkendali;
- Gemini bersifat optional dan dibatasi;
- human approval serta traceability menjaga penggunaan AI.

Gunakan demo sebagai cerita workflow, bukan sebagai tur source code atau pembacaan seluruh report JSON.

## 2. Pesan Utama yang Harus Dipahami Penguji

Sampaikan tujuh pesan berikut:

1. Finding kualitas utama tidak dibuat Gemini.
2. Domain dan governance context dipilih pengguna, bukan ditebak LLM.
3. RAG memakai corpus policy lokal dan router yang terbatas.
4. Evidence ditemukan tidak otomatis berarti evidence cukup.
5. Gemini hanya tersedia setelah readiness dan approval manusia.
6. Citation Gemini diperiksa kembali oleh traceability reviewer.
7. MetaGuard tahu kapan evidence kebijakan atau Gemini tidak applicable.

## 3. Dataset Demo Utama

Gunakan skenario Healthcare + Government/Public sebagai demo utama karena healthcare memiliki rule pack dengan dua provenance berbeda dan policy pack sektoral.

Nama data_dummy_puskesmas_super_kompleks_v2.csv dapat dipakai sebagai nama dataset demo acceptance bila file tersebut sudah disiapkan lokal. Nama tersebut tidak tersedia sebagai file repository pada baseline dokumentasi ini; jangan membuat link file palsu.

Alternatifnya, gunakan fixture healthcare lokal dengan kolom yang dapat menunjukkan:

- tempat_tidur_terisi;
- kapasitas_rawat_inap;
- status_internet;
- bandwidth_mbps.

Siapkan metadata yang lengkap bila ingin mendemonstrasikan alur evidence sampai Gemini.

## 4. Persiapan Sebelum Demo

Checklist:

- virtual environment aktif;
- aplikasi Streamlit dapat dijalankan;
- corpus v3 lokal tersedia dan tidak stale;
- dataset demo tersedia lokal;
- metadata demo telah disiapkan;
- browser sudah membuka aplikasi;
- screenshot fallback tersedia;
- Gemini API key tersedia hanya jika demo live Gemini memang diinginkan;
- file .env dan API key tidak ditampilkan.

Command untuk menjalankan aplikasi dari root repository:

~~~powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
~~~

Saat demo, jangan melakukan rebuild corpus. Jika corpus stale, jelaskan bahwa rebuild adalah tindakan maintenance eksplisit, bukan langkah normal pengguna.

## 5. Alur Demo Utama

### A. Pilih Domain dan Governance

**Apa yang dilakukan**

Pilih domain Healthcare dan governance context Government/Public.

**Apa yang ditunjukkan**

Selector Domain dan Konteks tata kelola.

**Apa yang dijelaskan**

Domain menentukan rule pack dan policy pack yang boleh digunakan. Governance context menentukan apakah policy pemerintah dapat dirutekan.

**Pesan untuk dosen**

Ini adalah pilihan eksplisit pengguna, bukan hasil tebak LLM dari nama kolom.

**Tidak perlu dibahas terlalu jauh**

Jangan mulai dari detail enum atau source registry.

### B. Upload dan Ingestion

**Apa yang dilakukan**

Upload dataset demo.

**Apa yang ditunjukkan**

Status ingestion, encoding, delimiter, jumlah row/column, serta warning parsing bila ada.

**Apa yang dijelaskan**

MetaGuard memastikan CSV terbaca dengan benar sebelum menilai isinya.

**Pesan untuk dosen**

Sistem tidak langsung mengirim file ke Gemini.

**Tidak perlu dibahas terlalu jauh**

Tidak perlu menjelaskan semua fallback encoding kecuali ditanya.

### C. Generic Quality Findings

**Apa yang dilakukan**

Tampilkan beberapa finding generic dan quality score.

**Apa yang ditunjukkan**

Contoh missing value, duplicate identifier, date issue, percentage range, negative numeric, outlier, atau duplicate row bila ada pada dataset demo.

**Apa yang dijelaskan**

Finding ini dibuat kode deterministik. Score adalah indikator kualitas MetaGuard, bukan status compliance.

**Pesan untuk dosen**

Gemini tidak menentukan severity, count, atau percentage finding ini.

**Tidak perlu dibahas terlalu jauh**

Jangan membaca semua finding satu per satu.

### D. Metadata

**Apa yang dilakukan**

Tampilkan metadata validation.

**Apa yang ditunjukkan**

Completeness score, status, dan field metadata utama.

**Apa yang dijelaskan**

Metadata memberi arti bagi angka serta ruang lingkup dataset. Misalnya, data period dan measurement unit membantu reviewer memahami temuan.

**Pesan untuk dosen**

Metadata yang lengkap menjadi salah satu prerequisite sebelum workflow dapat melanjutkan ke validasi kontekstual dan tahap evidence; metadata lengkap tidak otomatis membuktikan data benar.

**Tidak perlu dibahas terlalu jauh**

Jangan membaca seluruh form metadata bila penguji tidak memintanya.

### E. Contextual dan Domain Validation

**Apa yang dilakukan**

Jalankan atau tampilkan contextual validation.

**Apa yang ditunjukkan**

Active rule pack healthcare_core dan hasil rule:

- HEALTH-BED-CAPACITY-001;
- HEALTH-INTERNET-BANDWIDTH-001.

**Apa yang dijelaskan**

Bed/capacity adalah DETERMINISTIC_INVARIANT. Internet/bandwidth adalah HEURISTIC: temuan perlu diperiksa manusia dan bukan putusan regulasi.

**Pesan untuk dosen**

Rule bekerja melalui concept resolution dan kolom aktual, bukan hanya satu nama kolom yang dipaksa.

**Tidak perlu dibahas terlalu jauh**

Jangan menyebut finding heuristic sebagai pelanggaran.

### F. Evidence Workflow

**Apa yang dilakukan**

Tampilkan workflow evidence v3 setelah planning/routing.

**Apa yang ditunjukkan**

Evidence need, routing state, policy pack/policy ID eligible bila tersedia, attempt count, dan workflow state.

**Apa yang dijelaskan**

Policy evidence dipilih berdasarkan context serta need. Ini bukan pencarian web bebas atau retrieval tanpa batas.

**Pesan untuk dosen**

Healthcare tidak boleh menerima policy education atau environment sebagai evidence domain.

**Tidak perlu dibahas terlalu jauh**

Tidak perlu membuka detail filter Chroma kecuali penguji bertanya teknis.

### G. Evidence Sufficiency

**Apa yang dilakukan**

Tampilkan status sufficiency, score, evidence unik, dan source unik.

**Apa yang ditunjukkan**

Status READY atau alasan evidence belum ready.

**Apa yang dijelaskan**

Evidence ditemukan tidak selalu cukup. MetaGuard menilai coverage, unique evidence, source diversity, serta alignment. Retrieval dibatasi maksimal dua attempt per evidence need.

**Pesan untuk dosen**

Sufficiency adalah heuristic kesiapan review, bukan bukti compliance.

**Tidak perlu dibahas terlalu jauh**

Tidak perlu menghitung formula 60/30/10 secara manual kecuali diminta.

### H. Human Approval Gate

**Apa yang dilakukan**

Tampilkan Agentic Review saat evidence ready.

**Apa yang ditunjukkan**

ANALYSIS_READY dan RUN_GEMINI_ANALYSIS, serta control approval manusia.

**Apa yang dijelaskan**

READY tidak memanggil Gemini otomatis. Pengguna harus menyetujui evidence untuk analysis state saat ini.

**Pesan untuk dosen**

Approval terikat fingerprint; perubahan dataset/context menginvalidasi approval lama.

**Tidak perlu dibahas terlalu jauh**

Jangan mencoba mengulang Gemini hanya untuk menunjukkan tombol bekerja.

### I. Gemini Analysis

**Apa yang dilakukan**

Jika demo live tersedia dan approval sudah diberikan, tampilkan output terstruktur Gemini secara ringkas.

**Apa yang ditunjukkan**

Summary, priority actions, limitations, dan evidence references.

**Apa yang dijelaskan**

Gemini adalah interpretation layer. Ia menerima finding deterministik dan evidence eligible yang sudah dibatasi.

**Pesan untuk dosen**

Gemini tidak boleh membuat finding authoritative baru atau legal/compliance verdict.

**Tidak perlu dibahas terlalu jauh**

Jangan membaca seluruh output Gemini atau full prompt.

### J. Evidence References

**Apa yang dilakukan**

Tampilkan references yang dipakai Gemini.

**Apa yang ditunjukkan**

Policy identity, source, page, dan chunk ID.

**Apa yang dijelaskan**

Evidence identity memungkinkan reviewer menelusuri asal citation.

**Pesan untuk dosen**

Gemini hanya boleh mengutip evidence yang diberikan.

**Tidak perlu dibahas terlalu jauh**

Tidak perlu membuka PDF penuh.

### K. Traceability Required

**Apa yang dilakukan**

Tampilkan stage setelah Gemini selesai.

**Apa yang ditunjukkan**

TRACEABILITY_REQUIRED dan REVIEW_TRACEABILITY.

**Apa yang dijelaskan**

MetaGuard belum langsung mempercayai citation Gemini. Citation perlu dibandingkan dengan supplied evidence.

**Pesan untuk dosen**

Traceability adalah pemeriksaan deterministik setelah output AI.

**Tidak perlu dibahas terlalu jauh**

Jangan menganggap citation tampak mirip sebagai otomatis valid.

### L. Traceability Result dan Completion

**Apa yang dilakukan**

Tampilkan traceability result dan final state.

**Apa yang ditunjukkan**

Jumlah valid/invalid reference, traceability score, report status, dan COMPLETE/NONE bila seluruh tahap yang diperlukan selesai.

**Apa yang dijelaskan**

Traceability memeriksa hubungan citation dengan evidence supplied, bukan menjamin jawaban Gemini benar secara hukum.

**Pesan untuk dosen**

Report dapat dibangun tanpa Gemini, tetapi bila Gemini digunakan, traceability adalah guard tambahan.

**Tidak perlu dibahas terlalu jauh**

Jangan membuka seluruh JSON report kecuali diminta.

## 6. Demo Tambahan — Generic + Non-Government

Gunakan skenario ini sebagai kontras, bukan pengganti demo healthcare.

Pilih:

~~~text
Domain: generic
Governance context: generic_non_government
~~~

Tunjukkan:

- generic quality checks tetap tersedia;
- tidak ada domain-specific rule pack;
- evidence pemerintah berstatus NOT_APPLICABLE;
- tidak ada policy retrieval yang applicable;
- Gemini tidak executable;
- Agentic Review menjadi COMPLETE dengan action NONE.

Pesan utama: MetaGuard tidak memaksakan policy pemerintah atau AI ketika tidak ada evidence kebijakan yang applicable.

NOT_APPLICABLE bukan retrieval failure dan bukan pernyataan bahwa dataset valid.

## 7. Screenshot Fallback

Jika screenshot belum berada di repository, jangan membuat relative image link. Siapkan file lokal dengan nama rekomendasi berikut:

~~~text
01-healthcare-upload-ingestion.png
02-healthcare-quality-findings.png
03-healthcare-metadata.png
04-healthcare-contextual-validation.png
05-healthcare-evidence-workflow.png
06-healthcare-evidence-sufficiency.png
07-healthcare-human-approval-gate.png
08-healthcare-gemini-analysis.png
09-healthcare-evidence-references.png
10-healthcare-traceability-required.png
11-healthcare-traceability-and-final-state.png
12-nongov-evidence-not-applicable.png
13-nongov-agent-complete.png
~~~

Screenshot sebaiknya tidak memuat .env, API key, informasi pribadi, atau full dataset tanpa kebutuhan demo.

## 8. Jika Gemini atau Internet Gagal Saat Demo

Tindakan aman:

1. Jangan melakukan debugging live terlalu lama.
2. Jelaskan bahwa Gemini merupakan dependency eksternal dan optional.
3. Gunakan screenshot dari acceptance run bila tersedia.
4. Deterministic workflow dan report tetap dapat dijelaskan tanpa Gemini. Untuk menunjukkan hasil Gemini dan traceability, gunakan screenshot dari acceptance run yang sebelumnya telah berhasil.
5. Jangan menyebut seluruh sistem rusak hanya karena layanan eksternal tidak tersedia.

Deterministic review, domain rule, routing contract, dan report tanpa Gemini tetap merupakan bagian valid dari workflow MetaGuard.

## 9. Hal yang Jangan Dilakukan Saat Demo

- Jangan membaca semua finding.
- Jangan membuka seluruh JSON report tanpa pertanyaan.
- Jangan menampilkan API key atau file .env.
- Jangan terlalu lama menjelaskan source file.
- Jangan menyatakan legal/compliance verdict.
- Jangan mengatakan AI menemukan semua finding.
- Jangan mengatakan traceability berarti correctness 100 persen.
- Jangan memaksakan Gemini pada generic_non_government.
- Jangan menganggap HEURISTIC sebagai pelanggaran.

## 10. Alur Cerita yang Mudah Diingat

~~~text
Dataset
  -> Deterministic Check
  -> Domain
  -> Evidence
  -> Approval
  -> Gemini
  -> Traceability
  -> Complete
~~~

Gunakan satu kalimat sederhana untuk setiap tahap:

| Tahap | Kalimat demo |
| --- | --- |
| Dataset | Sistem memastikan CSV bisa dibaca. |
| Deterministic Check | Finding teknis berasal dari pemeriksaan kode. |
| Domain | Pengguna memilih konteks agar rule tepat sasaran. |
| Evidence | Router memilih evidence lokal yang eligible. |
| Approval | AI tidak berjalan otomatis. |
| Gemini | AI membantu menjelaskan, bukan menentukan finding. |
| Traceability | Citation diperiksa terhadap evidence supplied. |
| Complete | Workflow selesai sesuai state, termasuk saat evidence memang tidak applicable. |

## 11. Cara Menjelaskan Jika Dosen Memotong Demo

| Pertanyaan | Arah jawaban singkat |
| --- | --- |
| Bagaimana arsitekturnya? | Jelaskan lima lapisan: quality, context, RAG, controlled AI, audit/reporting. |
| Mengapa memakai AI? | AI hanya untuk interpretasi setelah finding/evidence siap. |
| Apa peran RAG? | Router memilih evidence dari corpus lokal, Chroma mengambil chunk, sufficiency menilai kesiapan. |
| Bagaimana mengurangi hallucination? | Finding deterministik, bounded evidence, approval, dan traceability. |
| Apa limitation utama? | Heuristic identifier/outlier, corpus terbatas, pilot rule, dan Gemini external dependency. |

Panduan ini bukan bank Q&A lengkap; gunakan jawaban teknis bila penguji meminta detail lebih lanjut.

## 12. Penutup Demo

Contoh penutup:

> MetaGuard menggabungkan deterministic review, domain-aware validation, policy-grounded RAG, human approval, optional Gemini, dan traceability. Sistem ini adalah alat bantu review kualitas data, bukan pengganti reviewer manusia atau mesin sertifikasi kepatuhan.

