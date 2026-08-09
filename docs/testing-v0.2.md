# MetaGuard v0.2 Testing & Acceptance

## 1. Tujuan pengujian

Pengujian v0.2 menggabungkan regression test deterministik, mock/fake integrasi
eksternal, Streamlit AppTest, dan real end-to-end acceptance.

## 2. Automated test strategy

Kategori suite meliputi ingestion, profiling, quality checker, scoring,
metadata, contextual validation, agent state/planner/tool executor, evidence
sufficiency, bounded retrieval, Gemini guard, traceability, report builder,
RAG unit tests, Streamlit AppTest, dan final agent acceptance. Automated suite
tidak memanggil Gemini nyata atau network.

## 3. Final automated result

```powershell
python -m pytest -q
```

Hasil final setelah validasi milestone dokumentasi: **212 passed**.

## 4. Real E2E acceptance

Dataset `data_dummy_puskesmas_super_kompleks_v2.csv` adalah data uji
synthetic/simulated, bukan data kesehatan nyata.

- `mode=sampled`, `sample_size=10000`, `sample_seed=42`.
- `total_rows=12000`, `rows_loaded=10000`, 50 kolom,
  `analysis_scope=sampled`.
- Encoding `utf-8-sig`, delimiter semicolon, malformed rows 0.
- Policy retrieval: PASS.
- Evidence sufficiency: `sufficient`, score 100, delapan evidence unik, dua
  sumber, satu duplicate ignored, dan coverage `metadata_governance`,
  `data_quality`, serta `accountability`; selesai pada attempt pertama.
- Gemini: PASS; menyatakan scope sampled, tidak mengklaim angka sampel sebagai
  exact seluruh dataset, tidak membuat kesimpulan hukum, dan memakai
  `chunk_id`, source, serta page evidence.
- Traceability: score 100, tiga valid references, nol invalid references.
- Agent final stage: `COMPLETE`; JSON report berhasil dibuat.

## 5. Bugs discovered during real acceptance

### A. False positive `negative_numeric` pada latitude

Latitude negatif sebelumnya ditandai pada 10000 dari 10000 baris sampel.
Allowlist exact normalized coordinate column name kini mencegah nilai koordinat
negatif valid menjadi negative-number finding.

### B. False positive hierarchy geografis

Metadata `Kabupaten Temanggung` sebelumnya membuat `kecamatan` dan
`kode_kecamatan` ditandai mismatch. Perbaikan membandingkan level administratif
yang kompatibel dan melewati kolom kode tanpa mapping eksplisit.

## 6. Post-fix real verification

| Metrik | Sebelum | Setelah |
| --- | ---: | ---: |
| High | 15 | 14 |
| Medium | 24 | 24 |
| Low | 11 | 11 |
| Info | 2 | 2 |
| Total finding | 52 | 51 |
| Score | 21.11 | 33.11 |

Score berubah karena false positive latitude tidak lagi dihitung. Contextual
validation pasca-perbaikan memiliki tiga finding: mismatch geografis level
kabupaten, occupied beds exceed capacity, serta status internet dengan bandwidth
positif. False positive `kecamatan` dan `kode_kecamatan` tidak lagi muncul.

## 7. What was mocked vs real

Automated suite memakai mock/fake untuk Gemini dan integrasi eksternal tanpa
network. Real E2E memakai vector knowledge base lokal, policy retrieval lokal,
Gemini API nyata, traceability nyata, dan pembuatan JSON report nyata.

## 8. Remaining testing limitations

- Hanya satu konfigurasi real E2E sampled.
- Tidak ada benchmark produksi, concurrency/load, multi-user session, atau
  deployment test.
- Kebenaran semantik evidence kebijakan tetap memerlukan human review.
