# DeepReader

DeepReader is a local document intelligence and RAG workbench for inspecting how technical documents become retrievable evidence. It is built as a portfolio-grade engineering system rather than a chatbot wrapper: every record, score, summary, job, citation, and evidence packet is visible.

## Current Scope

DeepReader v0.4 includes:

- FastAPI backend with SQLite persistence
- text and EPUB upload ingestion
- deterministic document records and stable IDs
- BM25 source-text search
- deterministic local record summaries with checkpointing
- jobs and job steps for processing inspection
- summary-aware search
- local vector-style retrieval and simple fusion
- evidence packets, citation mapping, and deterministic extractive QA
- React/Vite/TypeScript inspection dashboard
- Docker Compose local demo setup
- backend and frontend CI workflow

No API keys are required. The local summariser and QA flow are deterministic placeholders for pipeline verification; they do not call OpenAI, Gemini, or any paid external API.

## Architecture

- `backend/src/deepreader/api`: FastAPI routes and response schemas.
- `backend/src/deepreader/ingest`: text and EPUB parsing.
- `backend/src/deepreader/storage`: SQLAlchemy models and repositories.
- `backend/src/deepreader/summarise`: local summariser, checkpointing, and summary job runner.
- `backend/src/deepreader/retrieval`: BM25, local vector-style retrieval, and fusion.
- `backend/src/deepreader/answer`: extractive QA, evidence packets, and citations.
- `frontend/src`: dashboard panels for uploads, documents, records, jobs, search, and QA.

More detail lives in [docs/ARCHITECTURE.md](/Users/ianchia/deepreader/docs/ARCHITECTURE.md).

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
- frontend on `http://127.0.0.1:5173`
- SQLite in a named local volume, mounted at `/app/data` in the backend container

No secrets or external services are required.

## Demo Workflow

Use [docs/DEMO_WORKFLOW.md](/Users/ianchia/deepreader/docs/DEMO_WORKFLOW.md) for a step-by-step reviewer script. The short version:

1. Start backend and frontend locally, or run Docker Compose.
2. Upload `examples/simple_manual.txt`.
3. Select the document and inspect records, stable IDs, and source text.
4. Search for `what causes low flow?`.
5. Generate summaries and inspect the processing job.
6. Search summaries.
7. Ask a QA question.
8. Inspect citations and evidence packets.
9. Run tests and the frontend build.

Reviewer checklist:

- Uploads accept `.txt` and `.epub` and reject unsafe filenames/extensions.
- Source records remain visible and unchanged.
- Summary generation creates inspectable jobs and steps.
- Search results show scores, retrieval methods, metadata, and source text.
- QA answers expose citations and evidence, not hidden generated claims.
- Tests and frontend build pass locally.

## Uploads

Dashboard uploads use the real API:

- `POST /documents/ingest/text` for `.txt`
- `POST /documents/ingest/epub` for `.epub`

The backend enforces a local filename safety check, extension allowlist, and upload size limit. Duplicate ingest currently creates another document row, while deterministic record stable IDs are reused for identical content. That behavior is intentional for now and tested.

## Jobs, Summaries, And Checkpointing

Generating summaries for a document creates a `record_summary` job and one `summarise_record` step per record. The job runner is synchronous in v0.4, but it stores background-style progress:

- `pending`
- `running`
- `completed`
- `failed`

Checkpointing is based on `record_id`, `summariser_name`, and `source_hash`. Rerunning summary generation skips unchanged records that already have a matching summary. If a record source hash changes, a new current summary is created and prior source text remains untouched.

The summariser is `local_extractive_v1`: it normalises whitespace, selects deterministic text, truncates predictably, and stores summary/source hashes. It is not meant to be high-quality AI prose.

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

GitHub Actions runs backend install/tests and frontend install/build without secrets.

## Configuration

Backend defaults live in `.env.example`:

- `DEEPREADER_DATABASE_URL=sqlite:///./data/deepreader.sqlite3`
- `DEEPREADER_MAX_UPLOAD_BYTES=10485760`
- `DEEPREADER_CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173`

The default CORS origins are local-only. Uploaded file content and secrets are not logged by design. A small redaction utility exists for future provider-backed configuration, but no provider keys are needed today.

## Limitations

- SQLite is the only configured persistence layer.
- Summary jobs are synchronous despite job/step bookkeeping.
- The local summariser is deterministic and extractive, not an LLM summary.
- The local vector-style retriever is not embeddings and should not be treated as semantic search.
- Fusion is intentionally simple.
- QA is extractive and deterministic, not answer generation from a model.
- No auth, multi-user permissions, cloud deployment, PostgreSQL, Celery, Redis, or production observability stack.
- Screenshots are not committed yet. Add them later under `docs/assets/` after a stable visual QA pass.

## Roadmap

- Add screenshots and a short demo video.
- Add optional provider-backed summaries behind disabled-by-default configuration.
- Add real embeddings and hybrid retrieval in a later milestone.
- Add richer job retry/checkpoint inspection.
- Add exportable evidence packets for reviewer handoff.
- Consider production deployment concerns only after the local portfolio workflow is stable.
