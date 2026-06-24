# Changelog

## v0.4 Demo Hardening

- Added Docker Compose local demo support for backend, frontend, and SQLite volume.
- Added reviewer docs for demo workflow and architecture.
- Added GitHub Actions CI for backend tests and frontend build.
- Improved dashboard empty states, example queries, backend-unavailable errors, and QA status context.
- Added job step inspection and failed summary-step retry support.
- Added security and robustness tests for upload safety, local CORS defaults, redaction, and logging hygiene.
- Aligned project metadata and README with the current v0.4 local workbench scope.

## v0.3 Retrieval And QA Workbench

- Added local vector-style retrieval, retrieval fusion, evidence packets, citation mapping, and deterministic extractive QA.
- Added frontend QA and evidence inspection panels.

## v0.2 Processing Pipeline

- Added upload controls, jobs, job steps, deterministic local summaries, checkpointing, and summary-aware search.

## v0.1 Backend And Frontend Slice

- Added FastAPI backend, SQLite persistence, text and EPUB ingest, deterministic records, BM25 source search, and the initial React/Vite inspection dashboard.
