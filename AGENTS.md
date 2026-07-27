# MetaGuard Repository Instructions

## Project Identity

MetaGuard adalah project original untuk membantu validasi kualitas dataset dan metadata OPD.

DesignGuard dan Agentic-DesignGuard hanya menjadi referensi konseptual. Jangan menyalin source code, prompt, nama class, tampilan, struktur laporan, atau struktur folder dari repository tersebut.

## Prototype Scope

Implementasikan hanya milestone yang sedang diminta.

Jangan menambahkan:

- autentikasi;
- database pengguna;
- deployment;
- dukungan Excel;
- web scraping;
- model LLM lokal;
- autonomous agent loop;
- LangGraph;
- CrewAI;
- AutoGen;
- MCP;
- ekspor PDF atau Word;

kecuali diminta secara eksplisit.

## Architecture Rules

- Pisahkan UI dari business logic.
- Gunakan Pandas untuk pemeriksaan objektif.
- Jangan memakai LLM untuk pemeriksaan yang dapat dilakukan secara deterministik.
- Pisahkan modul RAG dan modul LLM.
- Gunakan output terstruktur.
- Simpan final report sebagai JSON.
- Maksimal dua panggilan LLM untuk satu analisis.
- Setiap temuan AI harus mempunyai evidence atau sumber dokumen.
- API key tidak boleh ditulis di source code.

## Code Quality

- Gunakan type hints.
- Berikan docstring pada fungsi publik.
- Tangani error dengan pesan yang jelas.
- Tambahkan unit test untuk pemeriksaan deterministik.
- Jalankan test setiap selesai milestone.
- Jangan menambahkan dependency yang tidak diperlukan.

## Hardware Constraint

Aplikasi dikembangkan untuk laptop AMD Athlon Silver 2-core.

Prioritaskan implementasi ringan dan hindari proses lokal yang berat.
