# DeepReader

DeepReader is a local-first AI document intelligence and RAG workbench for turning technical documents into inspectable retrieval evidence. It demonstrates the pieces a reviewer expects in a serious RAG system: document ingestion, deterministic record IDs, source-preserving retrieval, summaries, processing jobs, citations, and evidence inspection.

It is intentionally not a chatbot wrapper. The dashboard exposes records, scores, retrieval methods, summaries, job steps, citations, and evidence packets so the retrieval pipeline can be inspected end to end.

## Visual Walkthrough

![DeepReader dashboard showing upload controls and document records](docs/screenshots/dashboard.png)

*Document upload and records: ingest local `.txt` or `.epub` files, select documents, and inspect stable record IDs.*

![DeepReader records panel showing generated summaries](docs/screenshots/records-summaries.png)

*Generated summaries: deterministic local summaries are displayed beside preserved source text.*

![DeepReader search results showing retrieval details](docs/screenshots/search-results.png)

*Search/retrieval results: compare ranked records with scores, retrieval methods, metadata, summaries, and source text.*

![DeepReader QA panel showing citations and evidence](docs/screenshots/qa-citations.png)

*Extractive QA with citations/evidence: answers remain tied to cited records and inspectable evidence packets.*

![DeepReader jobs panel showing processing steps](docs/screenshots/jobs.png)

*Job tracking and steps: summary processing jobs expose status, progress, target stable IDs, attempts, and errors.*

## Core Features

- Text, EPUB, and PDF ingestion through a FastAPI backend.
- SQLite persistence for local, reproducible demos.
- Deterministic document records with stable IDs and source hashes.
- Source-preserving BM25 retrieval over original document text.
- Local vector-style retrieval and simple fusion for comparison.
- Deterministic local summaries with checkpointing.
- Optional standalone Paragraph Summary Service with deterministic mock summaries, explicitly enabled Gemini validation, and asynchronous batch scheduling.
- Processing jobs and job steps for summary generation.
- Summary-aware search with visible retrieval methods and component scores.
- Deterministic extractive QA with citations, evidence packets, and retrieval settings.
- React/Vite/TypeScript dashboard built for inspection rather than chat.
- Docker Compose setup for a no-secrets local demo.
- Backend tests and frontend build in GitHub Actions CI.

No API keys are required for the default workflow. The local summariser, mock paragraph provider, and QA flow are deterministic; the optional Gemini paragraph provider is disabled unless both provider selection and provider-call opt-in are set.

## How to evaluate this project

DeepReader is a portfolio/demo project built to be inspected rather than trusted. The fastest way to evaluate it is to clone it, run the local demo, and check that every pipeline stage is traceable.

### What to inspect in the UI

- **Ingest + records:** upload `examples/simple_manual.txt`. Confirm stable IDs, `order_index`, section titles, and unchanged source text.
- **Search provenance:** run `what causes low flow?`. Confirm each result shows retrieval method, aggregate score, component scores, record ID/stable ID, and source location (section/page/chapter). Missing fields fall back to `Not reported`; a zero-results query renders a styled empty state.
- **QA evidence provenance:** ask `What causes low flow?`. Confirm the Evidence provenance panel separates *used in answer* vs *available only*, shows each packet's retrieval method, scores, record ID, and location.
- **Job lifecycle:** generate summaries and open the job. Confirm completed/failed/skipped counts, `error_code`, attempts, and the retry button for failed or cancelled-unfinished steps.

### What backend reliability work is covered by tests

- Skipped-step accounting and `error_code` exposure (`v0.6-cancel-retry-hardening` tag).
- Retry of failed *and* skipped/`job_cancelled` steps (content/data skips like `empty_summary` excluded).
- Remote-cancel partial artifact import (completed records imported; unfinished steps marked skipped/`job_cancelled`).
- Concurrent local cancellation guard (rollback-based finalization-overwrite prevention).
- Upload filename/extension safety, search, QA evidence packets, and answer persistence.

Run `make test` for the full backend suite.

### What is intentionally mocked/deferred

- The optional paragraph-summary-service defaults to a deterministic `mock` provider; the Gemini path is validation-only and disabled unless explicitly opted in.
- Local summaries are deterministic-extractive, not LLM summaries.
- Local vector-style retrieval is a lexical approximation, **not** embeddings/semantic search.
- QA is extractive and deterministic, not answer generation from a model.
- **Provider (Gemini) and OpenStax validation remain deferred** unless explicitly approved; the default demo runs fully offline.

### Where to find validation logs and the demo workflow

- Step-by-step reviewer script with "what this demonstrates" commentary: [docs/DEMO_WORKFLOW.md](docs/DEMO_WORKFLOW.md).
- Proven-results-only validation history: [docs/validation-log.md](docs/validation-log.md).
- Module/data-flow overview: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- Planning notes and deferred scaling: [docs/project-log/feature-notes.md](docs/project-log/feature-notes.md).

### Current milestone / polish work

- Current tag: `v0.6-cancel-retry-hardening` (lifecycle hardening: skipped steps, cancel, retry, remote-cancel partial artifact import).
- Current v0.7 polish (`search-demo-polish` direction): QA evidence provenance surfacing (T1) and search result provenance/component-score display (T2), both complete and documented.

## Architecture

- `backend/src/deepreader/api`: FastAPI routes and response schemas.
- `backend/src/deepreader/ingest`: text, EPUB, and PDF parsing.
- `backend/src/deepreader/storage`: SQLAlchemy models and repositories.
- `backend/src/deepreader/summarise`: local summariser, remote service client, artifacts, and summary job runner.
- `backend/src/deepreader/retrieval`: BM25, local vector-style retrieval, and fusion.
- `backend/src/deepreader/answer`: extractive QA, evidence packets, and citations.
- `frontend/src`: dashboard panels for uploads, documents, records, jobs, search, and QA.

More detail lives in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Local Quickstart

Install and run the backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
cd ..
make backend-dev
```

In a second terminal, install and run the frontend:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Open `http://127.0.0.1:5173`. The dashboard defaults to the backend at `http://127.0.0.1:8000`. To override it, copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_BASE_URL`.

## Docker Quickstart

From the repository root:

```bash
docker compose up --build
```

Then open `http://127.0.0.1:5173`.

Docker Compose runs:

- backend on `http://127.0.0.1:8000`
- paragraph-summary-service on `http://127.0.0.1:8001`
- frontend on `http://127.0.0.1:5173`
- SQLite in a named local volume, mounted at `/app/data` in the backend container

No secrets or external services are required.

The backend uses its deterministic local summariser by default even though the paragraph service is running. To exercise the mock remote path, set both `DEEPREADER_SUMMARY_BACKEND=remote` and `DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE=true` before starting Compose.

## Demo Workflow

Use [docs/DEMO_WORKFLOW.md](docs/DEMO_WORKFLOW.md) for a step-by-step reviewer script. The short version:

1. Start backend and frontend locally, or run Docker Compose.
2. Upload `examples/simple_manual.txt` or a PDF.
3. Select the document and inspect records, stable IDs, and source text.
4. Search for `what causes low flow?`.
5. Generate summaries and inspect the processing job.
6. Search summaries.
7. Ask a QA question.
8. Inspect citations and evidence packets.
9. Run tests and the frontend build.

Reviewer checklist:

- Uploads accept `.txt`, `.epub`, and `.pdf`, and reject unsafe filenames/extensions.
- Source records remain visible and unchanged.
- Stable IDs make records traceable across retrieval, summaries, citations, and jobs.
- Search results show scores, retrieval methods, metadata, summaries, and source text.
- QA answers expose citations and evidence rather than hidden generated claims.
- Tests and frontend build pass locally.

## Uploads

Dashboard uploads use the real API:

- `POST /documents/ingest/text` for `.txt`
- `POST /documents/ingest/epub` for `.epub`
- `POST /documents/ingest/pdf` for `.pdf`

The backend enforces local filename safety checks and extension allowlists. PDF uploads stream to a temporary file while hashing and do not have an application-level size cap. Duplicate ingest currently creates another document row, while deterministic record stable IDs are reused for identical content. That behavior is intentional for now and tested.

## Jobs, Summaries, And Checkpointing

Generating summaries for a document creates a `record_summary` job and one `summarise_record` step per record. The backend endpoint is synchronous: local extraction runs inline, while the opt-in remote path submits work to `paragraph-summary-service`, polls it to completion, imports the artifact once, and then returns the persisted job.

Remote backend jobs persist the paragraph-service job ID and the latest remote record counts, status, and compact stats. The paragraph service exposes read-only `GET /jobs`, `GET /jobs/{job_id}`, and `GET /jobs/{job_id}/artifact` diagnostics; none includes source records or credentials.

Checkpointing is based on `record_id`, `summariser_name`, and `source_hash`. Rerunning summary generation skips unchanged records that already have a matching summary. If a record source hash changes, a new current summary is created and prior source text remains untouched.

The local summariser is `local_extractive_v1`: it normalises whitespace, selects deterministic text, truncates predictably, and stores summary/source hashes. The optional Paragraph Summary Service defaults to the deterministic `mock` provider and returns JSON artifacts. The v0.6 Gemini provider is an explicit, capped validation path; see [docs/GEMINI_PROVIDER_VALIDATION.md](docs/GEMINI_PROVIDER_VALIDATION.md).

## Search And QA

Search supports source text, summaries, local vector-style retrieval, and simple fusion. Response fields are inspection-first:

- `document_id`
- `record_id`
- `stable_id`
- `retrieval_method`
- `source_text`
- `summary`
- `metadata`
- `score`
- `component_scores`

The QA endpoint is deterministic and extractive. It returns an answer plus citations, all evidence packets, used evidence, unused evidence, and retrieval settings. It is not a chatbot and does not call an LLM.

## API Endpoints

- `POST /documents/ingest/text`
- `POST /documents/ingest/epub`
- `POST /documents/ingest/pdf`
- `GET /documents`
- `GET /documents/{document_id}`
- `GET /documents/{document_id}/records`
- `POST /documents/{document_id}/summaries/run`
- `GET /documents/{document_id}/summaries`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/steps`
- `POST /jobs/{job_id}/retry-failed`
- `POST /search`
- `POST /qa/ask`
- `GET /answers`
- `GET /answers/{answer_id}`

## Makefile Commands

```bash
make test
make backend-dev
make frontend-dev
make frontend-build
```

`make frontend-dev` and `make frontend-build` use `pnpm` by default. Override with `NPM=npm` if needed.

## Verification

Backend:

```bash
make test
```

Frontend:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm build
```

Docker config:

```bash
docker compose config
```

GitHub Actions runs backend and paragraph-service tests plus the frontend build without secrets or real provider calls.

## Configuration

Backend defaults live in `.env.example`:

- `DEEPREADER_DATABASE_URL=sqlite:///./data/deepreader.sqlite3`
- `DEEPREADER_CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173`

The default CORS origins are local-only. Uploaded file content and secrets are not logged by design. A small redaction utility exists for future provider-backed configuration, but no provider keys are needed today.

## Limitations

- SQLite is the only configured persistence layer.
- Text, EPUB, and PDF are supported; real OCR is not implemented for scanned PDFs.
- The backend summary request remains synchronous in both modes; the paragraph service schedules its internal batches asynchronously while the backend polls.
- Paragraph-service jobs are in-memory and non-durable; Gemini mode is validation-only and disabled by default.
- The local summariser is deterministic and extractive, not an LLM summary.
- The local vector-style retriever is not embeddings and should not be treated as semantic search.
- Fusion is intentionally simple.
- QA is extractive and deterministic, not answer generation from a model.
- No auth, multi-user permissions, hosted deployment, PostgreSQL, Celery, Redis, or production observability stack.

## Roadmap

- Add a short demo video.
- Validate optional provider-backed summaries conservatively before expanding the workflow.
- Add real embeddings and hybrid retrieval in a later milestone.
- Add richer job retry/checkpoint inspection.
- Add exportable evidence packets for reviewer handoff.
- Consider production deployment concerns only after the local portfolio workflow is stable.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
