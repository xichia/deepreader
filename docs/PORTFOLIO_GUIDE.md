# DeepReader Portfolio & Reviewer Guide

This guide is designed for portfolio reviewers evaluating DeepReader. It provides a high-level pitch, architectural rationale, evaluation pathways, honest limitations, and the v0.9 release notes.

---

## 1. Project Overview & Pitch

### GitHub Project Description
> **DeepReader** is an inspection-first RAG (Retrieval-Augmented Generation) workbench and document intelligence engine. Instead of wrapping an LLM behind an opaque chat interface, DeepReader exposes stable record hashing, multi-stage retrieval scores, checkpointed summarization job steps, and evidence provenance panels to make the entire ingestion-to-QA pipeline auditable and reproducible.

### Why this project exists
Most RAG templates hide intermediate pipeline steps behind a single "black box" prompt. DeepReader is built for engineers and reviewers who need to see **exactly** how a system arrived at a given answer. By exposing stable record IDs, retrieval methods, component scores, and used/available evidence side-by-side, it brings transparency and determinism back to document intelligence.

---

## 2. Reviewer Evaluation Pathway

To evaluate the system offline in under 5 minutes:

1. **Start the Stack**: Run `docker compose up --build` or follow the local quickstart in the [README.md](../README.md).
2. **Ingest**: Upload `examples/simple_manual.txt`. Notice the immediate generation of stable record IDs derived from source content hashes.
3. **Inspect Search Provenance**: Search for `what causes low flow?`. Inspect the result cards—they display the retrieval method (e.g., `bm25_source_text`), location metadata (section/page/chapter), and component score breakdown.
4. **Generate Summaries**: Click "Generate summaries". Watch the Job Panel track the execution of individual steps, accounting for completed, failed, or skipped items.
5. **Inspect QA Evidence**: Ask `What causes low flow?` in the QA workbench. Rather than generating a hallucinated LLM response, the system returns a deterministic extractive answer paired with an **Evidence Provenance Panel** that shows exactly which source records were *used in the answer* versus which were merely *available*.

---

## 3. Engineering Decisions & Honest Limitations

DeepReader is a focused RAG workbench, not a production search engine. We have intentionally chosen simple local defaults to keep the repository clone-and-run without API keys.

| Feature Area | Production Approach | DeepReader Portfolio Choice & Rationale |
|---|---|---|
| **Summarization** | LLM-based Summaries | **Local Extractive Summarizer (`local_extractive_v1`)**: Selects deterministic sentences to support reproducible tests and local validation without network overhead. |
| **QA Engine** | LLM Answer Generation | **Extractive Deterministic QA**: Retrieves exact source paragraphs and matches answers without model hallucinations or API usage. |
| **Vector Retrieval** | Dense Embeddings (e.g., Ada) | **Lexical Vector Approximation**: Simulates vector-style scores and fusion logic without requiring embedding model downloads or API keys. |
| **Database** | PostgreSQL / Vector DB | **SQLite**: Relies on a single file database to make setup instant and clean. |
| **Asynchronous Jobs** | Celery / Redis | **Synchronous Backend + Asynchronous Service**: The main backend polls a lightweight, in-memory paragraph service to keep the dependency footprint minimal. |
| **Provider Validation** | Production-ready LLM calls | **Optional Gemini Opt-in**: The Gemini provider is validation-only and capped to prevent accidental quota exhaustion. |
| **OpenStax Validation** | Full-scale dataset validation | **Intentionally Deferred**: OpenStax dataset validation plans are documented but deferred to keep evaluation lightweight. |

---

## 4. Milestone History & v0.9 Release Notes

DeepReader has evolved through structured, test-driven milestones:

### Release History
- **v0.1 – Ingestion & Search Foundation**: Implemented text/EPUB parsing, stable record hashing, and BM25 search.
- **v0.2 – Summaries & Job Checkpointing**: Added local summaries, SQLite checkpointing, and job step tracking.
- **v0.3 – Retrieval & QA Workbench**: Built evidence packets, used/available evidence separation, extractive QA, and stable-ID citations.
- **v0.4 – CI & Reliability**: Added Docker Compose support, GitHub Actions CI, and empty-state guidance.
- **v0.5 – Security & Ingestion Polish**: Added filename safety validation, streaming PDF ingestion, and duplicate record safety.
- **v0.6 – Cancel & Retry Hardening**: Hardened job step lifecycles, added skipped-step accounting, and implemented retry logic for cancelled/failed steps.
- **v0.7 – Search Provenance Polish**: Redesigned search/QA panels to display retrieval methods, location metadata, and score chips.
- **v0.8 – Demo Assets Polish**: Standardized README/walkthrough screenshots around composite viewport capture and simplified the asset footprint.

### v0.9 Release Notes (Current Release)
The **v0.9-portfolio-polish** release focuses on portfolio readiness, reviewer navigation, and code-base documentation:
- **Created a Dedicated Portfolio Guide**: Consolidated evaluation paths, architectural decisions, and honest limitations for reviewers.
- **Improved Project Onboarding**: Refined the README to highlight evaluation checklist items and clear up-front design trade-offs.
- **Documented Offline Defaults**: Clarified that the default reviewer path runs locally/offline and keeps external provider validation opt-in.
