# Pengujian MetaGuard Functional Research Prototype v0.1

Dokumen ini mencatat cakupan pengujian untuk MetaGuard v0.1 berdasarkan repository saat ini. Pengujian Gemini menggunakan mock; automated test tidak memanggil API Gemini.

## 1. Lingkungan dan Perintah

Repository tidak memiliki `pytest.ini`, sehingga pytest menggunakan discovery bawaan. Perintah yang digunakan untuk validasi otomatis adalah:

```powershell
python -m pytest
python -m compileall app.py core llm rag tests
git diff --check
git status
```

Pada validasi terakhir sebelum dokumentasi ini dibuat, `python -m pytest` mengumpulkan dan meluluskan **122 test**. `compileall` berhasil dan `git diff --check` tidak melaporkan error.

## 2. Cakupan Automated Test

| Area | Cakupan utama |
| --- | --- |
| CSV reader dan ingestion | File kosong, encoding UTF-8/BOM/fallback, delimiter koma/titik koma/tab/pipe, quoted delimiter, escaped quote, newline dalam quoted field, header duplikat, kolom tanpa nama, malformed row, missing tokens, teks panjang, banyak kolom/baris, exact/chunked/sampled, diagnostics, dan integrasi CSV ke report. |
| Data profile dan quality checker | JSON safety, input tidak dimutasi, missing value, duplicate row, kolom kosong/konstan, nama kolom duplikat, whitespace, string kosong, variasi kategori, identifier duplikat, angka negatif, persentase, tanggal, dan outlier. |
| Scoring dan metadata | Rentang skor, severity, dampak persentase, grade, rekap severity, validasi field metadata, batas panjang judul/deskripsi, kelengkapan, dan status metadata. |
| State dan report | Fingerprint file/metadata/konfigurasi aktif, reset hasil turunan, schema report, ingestion diagnostics, serialisasi JSON, serta perilaku overwrite saat menyimpan report. |
| RAG | Loader TXT/PDF, normalisasi, chunking, filtering, deduplikasi, ingestion summary, vector store, dan retrieval evidence. |
| Gemini dan traceability | Payload terstruktur, error konfigurasi, sampled/full scope instruction, mock Gemini, validasi `chunk_id`/`source`/`page`, dan score traceability. |
| Evidence sanitizer | Batas lima evidence, pemotongan string setelah 300 karakter, Unicode, nilai numerik, dan non-mutasi DataFrame. |

## 3. Skenario Manual v0.1

Skenario berikut adalah prosedur pemeriksaan manual untuk Streamlit. Jalankan tanpa mengirim API Gemini kecuali memang ingin memverifikasi konfigurasi Gemini pada environment yang aman.

| Skenario | Langkah | Hasil yang diharapkan |
| --- | --- | --- |
| CSV exact | Unggah CSV kecil ber-delimiter koma dan pilih `exact`. | Diagnostics menunjukkan scope `full`; preview, profil, finding, skor, metadata, dan report JSON tampil. |
| Override delimiter | Unggah CSV titik koma, pilih `Titik koma (;)`. | Kolom terbaca sesuai delimiter; diagnostics mencatat `;`. |
| Malformed strict/warn | Uji CSV dengan field berlebih pada mode `strict`, lalu `warn`. | Strict menampilkan error ramah; warn mencatat warning dan jumlah row yang dilewati. |
| Chunked | Pilih `chunked`, ubah Chunk size, lalu unggah CSV. | Scope `full`, strategi `combined_dataframe`, dan `chunk_size_requested` tampil; UI menjelaskan chunk masih digabung ke memori. |
| Sampled nyata | Pilih `sampled` dengan sample lebih kecil dari total. | Scope `sampled`, `sampling_applied=true`, jumlah sampel dan seed tampil; warning menyatakan hasil memakai sampel deterministik. |
| Sampled mencakup seluruh dataset | Pilih `sampled` dengan sample sama atau lebih besar dari total row. | Scope `full`, `sampling_applied=false`, seluruh row dimuat, dan warning menyatakan seluruh baris dianalisis. |
| Metadata | Isi sebagian lalu seluruh sembilan field metadata. | Field kosong, finding, completeness score, dan status berubah secara deterministik. |
| Evidence kebijakan | Pastikan `data/policies/` telah di-ingest dengan `python -m rag.ingest`, lalu tekan tombol retrieval. | Evidence menampilkan source, page, chunk ID, distance, dan teks; tidak ada jawaban generatif dari retrieval. |
| Gemini dan traceability | Setelah evidence tersedia dan `.env` valid, tekan tombol Gemini sekali. | Analisis terstruktur tampil; referensi ditinjau terhadap `chunk_id`, `source`, dan `page`; tidak ada keputusan hukum. |
| Reset state | Ubah file, metadata, delimiter, mode aktif, chunk size aktif, sample size aktif, atau seed aktif. | Policy evidence, analisis Gemini, review evidence, dan report payload lama dihapus. |
| Report JSON | Unduh report setelah analisis lokal. | JSON memuat profile, findings, score, metadata, ingestion, serta evidence/analysis/review bila telah tersedia. |

## 4. Batasan Pengujian

- Automated test tidak mengunduh model embedding atau melakukan network request untuk unit test yang memakai fake/mocked dependency.
- Automated test tidak memanggil API Gemini. Uji Gemini manual memerlukan `GEMINI_API_KEY`, `GEMINI_MODEL`, koneksi internet, dan policy evidence.
- Mode chunked diuji untuk kesetaraan hasil dengan exact pada fixture, tetapi bukan implementasi out-of-core.
- Hasil sampled harus dibaca berdasarkan `analysis_scope` efektif pada ingestion diagnostics, bukan hanya nilai mode yang dipilih.
- File sumber CSV tidak boleh dimodifikasi oleh proses ingestion maupun pengujian.
