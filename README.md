# DeepReader

DeepReader is a document intelligence and RAG workbench project for turning long technical documents into searchable, inspectable knowledge bases.

## Current v0.2 Scope

DeepReader now has a working local full-stack processing slice:

- FastAPI backend
- SQLite persistence
- text and EPUB ingestion
- deterministic document records
- deterministic local record summaries
- synchronous background-style jobs and job steps
- checkpointed summary generation
- BM25 search over source text and optional summaries
- React/Vite/TypeScript inspection dashboard

The v0.2 summariser is intentionally local and deterministic. It does not call OpenAI, Gemini, or any paid external API. This keeps tests and demos reproducible with no API keys.

Out of scope for v0.2:

- embeddings
- hybrid retrieval
- answer generation
- chatbot UI
- citation inspector
- real external LLM dependency
- Docker polish

## Backend Quickstart

From the repository root, create a virtual environment and install the backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
cd ..
```

Start the API:

```bash
make backend-dev
```

The local API runs at `http://127.0.0.1:8000`.

## Frontend Quickstart

In a second terminal, install and start the dashboard:

```bash
cd frontend
pnpm install
pnpm dev
```

The dashboard runs at `http://127.0.0.1:5173` and defaults to `http://127.0.0.1:8000` for the backend API.

To override the API URL:

```bash
cd frontend
cp .env.example .env
```

Then edit `VITE_API_BASE_URL`.

The root Makefile also includes:

```bash
make test
make backend-dev
make frontend-dev
make frontend-build
```

`make frontend-dev` and `make frontend-build` use `pnpm` by default. You can run them with npm using `make frontend-dev NPM=npm` or `make frontend-build NPM=npm`.

## Demo Workflow

1. Start the backend with `make backend-dev`.
2. Start the frontend with `cd frontend && pnpm dev`.
3. Upload `examples/simple_manual.txt` or `examples/troubleshooting_log.txt` from the dashboard.
4. Select the uploaded document.
5. Inspect source records and stable IDs.
6. Click `Generate summaries`.
7. Inspect summaries in the records panel.
8. Inspect the completed processing job in the jobs panel.
9. Run a search with source text, summaries, or both enabled.

## Uploads

The dashboard upload control uses the real backend endpoints:

- `.txt` files go to `POST /documents/ingest/text`
- `.epub` files go to `POST /documents/ingest/epub`

Uploads are parsed in memory by the v0.2 API. The backend keeps extension allowlists, size limits, and filename safety checks from v0.1.

You can still ingest from curl:

```bash
curl -X POST "http://127.0.0.1:8000/documents/ingest/text" \
  -F "file=@examples/simple_manual.txt"
```

## Summaries

Generate summaries for one document:

```bash
curl -X POST "http://127.0.0.1:8000/documents/1/summaries/run"
```

Read current summaries:

```bash
curl "http://127.0.0.1:8000/documents/1/summaries"
```

The v0.2 provider is `local_extractive_v1`. It normalises whitespace, selects the first sentence, truncates long output predictably, and stores a deterministic summary hash. It is a pipeline placeholder, not a high-quality AI summary.

Each summary stores:

- `document_id`
- `record_id`
- `stable_id`
- `summary_text`
- `summariser_name`
- `summary_hash`
- `source_hash`

Source text remains the ground truth and is never overwritten.

## Jobs And Checkpointing

Summary generation creates a `record_summary` job and one `summarise_record` step per document record.

Inspect jobs:

```bash
curl "http://127.0.0.1:8000/jobs"
curl "http://127.0.0.1:8000/jobs/1"
```

Statuses are:

- `pending`
- `running`
- `completed`
- `failed`

Checkpointing is based on `record_id`, `summariser_name`, and `source_hash`. Rerunning summary generation skips unchanged records that already have a matching summary. If a record's `source_hash` changes, a new current summary is created for that record.

## Search

Default source-text search still works:

```bash
curl -X POST "http://127.0.0.1:8000/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"low flow","limit":5}'
```

Search summaries only:

```bash
curl -X POST "http://127.0.0.1:8000/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"bearing wear","document_id":1,"limit":5,"search_source_text":false,"search_summaries":true}'
```

Search both source text and summaries:

```bash
curl -X POST "http://127.0.0.1:8000/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"filter replacement","limit":10,"search_source_text":true,"search_summaries":true}'
```

Retrieval methods are explicitly labelled:

- `bm25_source_text`
- `bm25_summary_text`

Summary search results still include the original `source_text`, `stable_id`, score, retrieval method, summary text, and metadata.

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
- `POST /search`

## Tests And Builds

Backend tests:

```bash
make test
```

Frontend production build:

```bash
cd frontend
pnpm build
```

The backend tests cover v0.1 ingestion/search behavior plus v0.2 local summaries, summary storage, summary jobs, checkpointing, jobs API, summary API, and summary-aware search.

## Configuration

Copy `.env.example` if you want to override backend local defaults:

```bash
cp .env.example .env
```

Defaults:

- `DEEPREADER_DATABASE_URL=sqlite:///./data/deepreader.sqlite3`
- `DEEPREADER_MAX_UPLOAD_BYTES=10485760`
- `DEEPREADER_CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173`

The dashboard uses `frontend/.env.example` for `VITE_API_BASE_URL`.

## Current Limitations

- Chunking is paragraph-based only.
- EPUB extraction focuses on readable HTML document items.
- Summary generation is synchronous even though it records jobs and steps.
- The local summariser is extractive and deterministic, not a real LLM summary.
- BM25 summary search and source-text search are combined with simple score sorting.
- No embeddings, hybrid retrieval, generated answers, or chatbot UI are included.

## Roadmap

v0.3 can add provider-backed LLM summaries behind optional configuration, richer checkpoint inspection, embeddings, hybrid retrieval, answer generation, citations, and broader product workflows once the v0.2 pipeline is stable.
