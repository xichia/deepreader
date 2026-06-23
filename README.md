# DeepReader

DeepReader is a document intelligence and RAG workbench project for turning long technical documents into searchable, inspectable knowledge bases.

## Current v0.1 Scope

This milestone is backend only. It implements deterministic text and EPUB ingestion, paragraph records, SQLite persistence, and BM25 search over preserved source text.

In scope:

- UTF-8 `.txt` ingestion
- `.epub` ingestion with `ebooklib` and `beautifulsoup4`
- deterministic stable record IDs
- SQLite tables for documents, document records, and search queries
- paragraph chunking on blank lines
- inspectable BM25 source-text search
- FastAPI document and search endpoints
- meaningful pytest coverage

Out of scope for v0.1:

- LLM calls
- embeddings or hybrid retrieval
- generated answers or summaries
- question answering
- citation inspection
- frontend dashboard
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

## API Endpoints

- `POST /documents/ingest/text`
- `POST /documents/ingest/epub`
- `GET /documents`
- `GET /documents/{document_id}`
- `GET /documents/{document_id}/records`
- `POST /search`

Search results expose `record_id`, `stable_id`, `score`, `retrieval_method`, `source_text`, `summary: null`, and record metadata.

## Tests

```bash
make test
```

The tests cover text ingestion, EPUB ingestion, stable IDs, paragraph chunking, BM25 ranking, document APIs, search APIs, and upload safety.

## Configuration

Copy `.env.example` if you want to override local defaults:

```bash
cp .env.example .env
```

The default database URL is `sqlite:///./data/deepreader.sqlite3`. Uploaded files are parsed in memory and are not persisted by the v0.1 API.

## Current Limitations

- Chunking is paragraph-based only.
- EPUB extraction focuses on readable HTML document items.
- BM25 searches exact source text tokens and does not use embeddings.
- `summary` is intentionally always `null`.
- No frontend is included in v0.1.

## Roadmap

v0.2 should add richer document formats, retrieval inspection, and better ingestion observability.

v0.3 can introduce embeddings, hybrid retrieval, answer generation, citations, and a frontend once the backend slice is stable.
