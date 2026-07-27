# MetaGuard

MetaGuard adalah prototipe sistem untuk membantu pemeriksaan awal kualitas dataset dan kelengkapan metadata OPD sebelum proses publikasi data.

## Tujuan

Sistem akan menggabungkan:

- pemeriksaan kualitas dataset secara deterministik menggunakan Pandas;
- retrieval dokumen pedoman menggunakan RAG;
- analisis metadata berbantuan LLM;
- validasi evidence;
- laporan hasil terstruktur.

## Ruang Lingkup Prototype

Fitur awal:

- upload satu file CSV;
- profil dataset;
- pemeriksaan missing values dan duplicate rows;
- pemeriksaan kolom kosong dan inkonsistensi kategori sederhana;
- form metadata;
- retrieval dokumen pedoman;
- analisis metadata melalui API LLM;
- laporan Streamlit;
- penyimpanan hasil JSON.

## Status

Tahap awal: inisialisasi repository dan perancangan arsitektur.

## Menjalankan aplikasi

Gunakan Python 3.11 atau versi yang kompatibel, lalu siapkan environment lokal:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Jalankan entry point Streamlit:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Salin `.env.example` menjadi `.env` hanya ketika konfigurasi tersebut mulai
digunakan. Jangan menyimpan API key di repository.

## Dokumen kebijakan lokal

Letakkan dokumen pedoman berformat `.txt` atau `.pdf` di `data/policies/`.
TXT dibaca sebagai UTF-8 dan PDF diekstrak per halaman tanpa OCR. Jalankan
ingestion untuk membangun ulang vector store lokal:

```powershell
.\.venv\Scripts\python.exe -m rag.ingest
```

Vector store disimpan di `vector_db/` menggunakan ChromaDB dan model embedding
`sentence-transformers/all-MiniLM-L6-v2`. Milestone ini hanya menyediakan
retrieval evidence dan belum menggunakan LLM.

Contoh retrieval melalui Python:

```python
from rag.retriever import retrieve_policy_chunks

evidence = retrieve_policy_chunks("frekuensi pembaruan dataset", top_k=4)
```

## Originalitas

MetaGuard dikembangkan dari nol. DesignGuard dan Agentic-DesignGuard hanya digunakan sebagai referensi konseptual untuk memahami RAG dan workflow berbasis agent.
