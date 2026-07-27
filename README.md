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

## Originalitas

MetaGuard dikembangkan dari nol. DesignGuard dan Agentic-DesignGuard hanya digunakan sebagai referensi konseptual untuk memahami RAG dan workflow berbasis agent.
