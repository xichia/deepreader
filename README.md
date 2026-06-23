# DeepReader

DeepReader is a document intelligence and RAG workbench project for turning long technical documents into searchable, inspectable knowledge bases.

## Current v0.1 Scope

This milestone includes a working FastAPI backend and a minimal React dashboard. It is focused on deterministic ingestion, preserved source records, SQLite persistence, and inspectable BM25 retrieval.

In scope:

- UTF-8 `.txt` ingestion
- `.epub` ingestion with `ebooklib` and `beautifulsoup4`
- deterministic stable record IDs
- SQLite tables for documents, document records, and search queries
- paragraph chunking on blank lines
- inspectable BM25 source-text search
- FastAPI document and search endpoints
- minimal React/Vite/TypeScript dashboard
- meaningful backend pytest coverage

Out of scope for v0.1:

- LLM calls
- embeddings or hybrid retrieval
- generated answers or summaries
- question answering
- citation inspection
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
npm install
npm run dev
```

The local dashboard runs at `http://127.0.0.1:5173` and defaults to `http://127.0.0.1:8000` for the backend API.

To override the API URL:

```bash
cd frontend
cp .env.example .env
```

Then edit `VITE_API_BASE_URL`.

The root Makefile also includes:

```bash
make frontend-install
make frontend-dev
make frontend-build
```

## Running Backend And Frontend Together

Terminal 1:

```bash
make backend-dev
```

Terminal 2:

```bash
make frontend-dev
```

The backend allows local CORS requests from `http://127.0.0.1:5173` and `http://localhost:5173` by default. Override `DEEPREADER_CORS_ORIGINS` with a comma-separated list if your local frontend origin differs.

## Ingest An Example Text File

```bash
curl -X POST "http://127.0.0.1:8000/documents/ingest/text" \
  -F "file=@examples/simple_manual.txt"
```

From inside `backend/`, use:

```bash
curl -X POST "http://127.0.0.1:8000/documents/ingest/text" \
  -F "file=@../examples/simple_manual.txt"
```

After ingesting, refresh the dashboard document list.

## Search

```bash
curl -X POST "http://127.0.0.1:8000/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"low flow","limit":5}'
```

Search can be scoped to one document:

```bash
curl -X POST "http://127.0.0.1:8000/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"bearing wear","document_id":1,"limit":10}'
```

The dashboard exposes the same search path and shows scores, stable IDs, retrieval method, source text, `summary: null`, and metadata for each result.

## API Endpoints

- `POST /documents/ingest/text`
- `POST /documents/ingest/epub`
- `GET /documents`
- `GET /documents/{document_id}`
- `GET /documents/{document_id}/records`
- `POST /search`

Search results expose `record_id`, `stable_id`, `score`, `retrieval_method`, `source_text`, `summary: null`, and record metadata.

## Tests And Builds

Backend tests:

```bash
make test
```

Frontend production build:

```bash
cd frontend
npm run build
```

The backend tests cover text ingestion, EPUB ingestion, stable IDs, paragraph chunking, BM25 ranking, document APIs, search APIs, CORS, and upload safety.

## Configuration

Copy `.env.example` if you want to override backend local defaults:

```bash
cp .env.example .env
```

The default database URL is `sqlite:///./data/deepreader.sqlite3`. Uploaded files are parsed in memory and are not persisted by the v0.1 API.

## Current Limitations

- Chunking is paragraph-based only.
- EPUB extraction focuses on readable HTML document items.
- BM25 searches exact source text tokens and does not use embeddings.
- `summary` is intentionally always `null`.
- The dashboard does not upload documents yet; use the API ingest endpoints.
- The dashboard is a local development UI, not a deployed product shell.

## Roadmap

v0.2 should add richer document formats, retrieval inspection refinements, and better ingestion observability.

v0.3 can introduce embeddings, hybrid retrieval, answer generation, citations, and broader product workflows once the v0.1 system is stable.
