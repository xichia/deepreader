# DeepReader Agent Instructions

DeepReader is a serious AI document intelligence and RAG workbench portfolio project.

Build it as a reliable engineering system, not a generic chatbot or beginner AI wrapper.

## Current milestone

The v0.1 backend/frontend slice is complete.

The v0.2 processing pipeline is complete: uploads, jobs, job steps, deterministic local summaries, checkpointing, summary-aware BM25 search, and frontend summary/job panels.

The v0.3 retrieval and QA workbench is complete: local vector-style retrieval, fusion, evidence packets, stable-ID citations, deterministic extractive QA, persisted answers, and frontend QA/citation inspection.

The current milestone is v0.4 demo hardening, reviewer workflow, Docker, CI, and reliability polish.

Read:

- README.md
- docs/V0.1_ACCEPTANCE.md
- examples/README.md
- backend/src/deepreader
- frontend/src
- backend/tests

## Allowed in this milestone

Add v0.4 reliability and demo polish:

- Docker Compose local demo support
- reviewer demo documentation
- frontend empty-state and workflow guidance
- job detail inspection and local retry for failed summary steps
- upload/security regression tests
- API/schema consistency polish
- lightweight backend logging and error handling
- GitHub Actions CI
- architecture and changelog documentation

The project must continue to work locally with no API keys.

## Do not overbuild

Do not add:

- new AI capabilities beyond hardening existing local behaviour
- real external LLM providers
- OpenAI, Gemini, Anthropic, or paid API calls
- required API keys
- authentication
- multi-user permissions
- cloud deployment
- PostgreSQL or production infrastructure
- Celery, Redis, or external worker infrastructure

Do not mock core backend behaviour. The dashboard should consume the real FastAPI backend.

## Package defaults

Frontend:

- Vite
- React
- TypeScript
- plain CSS or simple CSS modules
- no heavy UI framework unless already justified

Backend:

- Keep existing FastAPI backend functionality working.
- Keep v0.1 ingestion/search, v0.2 summary/job behaviour, and v0.3 retrieval/QA behaviour passing.
- SQLite remains the local default.
- Docker support should be simple and local-only.

## Engineering priorities

Prioritise:

- reliable clone-and-run reviewer experience
- deterministic stable IDs and hashes
- clean SQLite persistence
- inspectable retrieval, summaries, jobs, citations, and evidence
- clear user-facing errors and empty states
- no source-text dumps in logs
- no secrets in config, docs, logs, or tests
- meaningful regression tests
- generated artifact cleanup

Avoid:

- unnecessary abstractions
- broad architecture rewrites
- mocked core backend behaviour
- committed secrets or generated artifacts
