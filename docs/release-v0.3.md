# MetaGuard v0.3 Release Candidate

MetaGuard v0.3 adalah release candidate untuk review kualitas data berbasis
aturan deterministik, konteks domain eksplisit, dan evidence kebijakan lokal.
Dokumen ini mencatat implementasi aktual; status final tetap bergantung pada
full regression lokal sebelum tag dibuat.

## Yang diimplementasikan

- Domain `generic`, `healthcare`, `education`, `environment`, dan `other`,
  terpisah dari governance context `government_public` atau
  `generic_non_government`.
- Registry konsep, domain rule, dan enam policy terverifikasi; corpus Chroma
  `metaguard_policies_v3` memakai manifest, checksum, stable chunk ID, dan
  metadata scalar untuk retrieval terfilter.
- Rule healthcare yang kompatibel dengan v0.2; pilot education/environment
  bersifat `HEURISTIC`, conservative, dan selalu meminta human review.
- Router kebijakan deterministik, evidence assessment/alignment, serta
  EvidenceWorkflowV3 dengan maksimum dua retrieval attempt per evidence need.
- Gemini interpretif bersifat opsional dan hanya setelah evidence ready serta
  persetujuan manusia eksplisit; maksimal satu call per state yang tidak berubah.
- Citation reviewer deterministik dan report schema `1.1` dengan
  `v3_metadata` untuk context, provenance, evidence, approval, traceability,
  dan limitations.

## Corpus awal

Corpus v3 terdiri dari enam policy registry initial: Perpres 39/2019, BPS
4/2020, BPS 5/2020, Permenkes 18/2022, Permendikbudristek 31/2022, dan Permen
LHK 25/2021. Runtime tidak melakukan web discovery atau download policy.

## Batasan release candidate

- Ini prototype/coursework, bukan sertifikasi legal atau compliance checker.
- Evidence readiness dan traceability mengukur kontrak review MetaGuard, bukan
  kebenaran faktual Gemini atau pemenuhan regulasi.
- Education/environment hanya mempunyai pilot rule terbatas; generic/other
  terutama memakai pemeriksaan generik.
- Cold start embedding MiniLM pada laptop lokal terukur sekitar 26 detik;
  aggregate warm sekitar 0.99 detik. Chroma 0.6.3 tetap dipakai sesuai
  `chromadb>=0.5,<1.0`; warning Pydantic internal adalah technical debt
  non-blocking yang tidak diubah pada release candidate.

## Acceptance dan rilis

Focused acceptance mencakup registry, parity healthcare, isolasi domain,
router/retrieval, assessment, approval/Gemini mock guard, traceability, dan
report provenance. Baseline sebelum M12 adalah 350 test lulus. Jalankan final
gate lokal sebelum release:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Jangan tag/merge/push sebelum gate tersebut lulus dan review manusia selesai.
