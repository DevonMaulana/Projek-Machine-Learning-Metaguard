# MetaGuard v0.2 Release Preparation

Dokumen ini adalah checklist release preparation, bukan pengumuman release.
Tidak ada merge, tag, atau push pada milestone dokumentasi ini.

## Release candidate scope

v0.2 mencakup robust CSV ingestion, quality scoring proporsional, metadata,
contextual validation, controlled agentic review, policy-grounded RAG,
deterministic evidence sufficiency, bounded retrieval retry, human-approved
Gemini analysis, deterministic traceability, dan JSON report.

## Not in scope

- Framework multi-agent, web search, atau Gemini query rewriting.
- Automatic CSV repair atau automatic compliance conclusion.
- Authentication, database/history, deployment, dan general chatbot.
- True out-of-core processing.

## Verified milestones

- [x] Agentic core dan tool allowlist.
- [x] Streamlit Agentic Review integration.
- [x] Automated agent acceptance dan AppTest.
- [x] Contextual validation.
- [x] Evidence-aware RAG dan bounded retry.
- [x] Final hardening serta real E2E acceptance.
- [x] Semantic bugfix koordinat dan geographic hierarchy.
- [x] Documentation consistency audit.

## Final release checklist

- [ ] Working tree clean setelah documentation review.
- [ ] Final pytest green.
- [ ] Compileall green.
- [ ] `git diff --check` green.
- [ ] Secret scan clear.
- [ ] README updated.
- [ ] `testing-v0.2.md` reviewed.
- [ ] Architecture documentation reviewed.
- [ ] Limitations reviewed.
- [ ] No `.env` tracked.
- [ ] No generated vector DB tracked.
- [ ] Semantic fixes committed.
- [ ] Branch reviewed.
- [ ] Merge to `main` approved and performed by a human.
- [ ] Tests rerun on `main`.
- [ ] Tag `v0.2.0` created after approval.
- [ ] `main` pushed after approval.
- [ ] Tag pushed after approval.

## Suggested release commands

Jalankan perintah berikut hanya setelah approval manusia dan audit branch.
Perintah ini adalah dokumentasi dan tidak dijalankan oleh Codex di milestone ini.

```powershell
git switch main
git merge --no-ff feature/agentic-review-v0.2
python -m pytest -q
python -m compileall app.py core llm rag tests
git tag -a v0.2.0 -m "MetaGuard v0.2.0"
git push origin main
git push origin v0.2.0
```

Pastikan `main` dan remote telah diaudit sebelum menjalankan urutan tersebut.
