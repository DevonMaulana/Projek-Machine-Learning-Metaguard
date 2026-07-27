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

## Originalitas

MetaGuard dikembangkan dari nol. DesignGuard dan Agentic-DesignGuard hanya digunakan sebagai referensi konseptual untuk memahami RAG dan workflow berbasis agent.
