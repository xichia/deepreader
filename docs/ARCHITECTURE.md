# DeepReader Architecture

DeepReader is a local-first inspection workbench. The main design goal is to preserve and expose the retrieval pipeline rather than hide it behind a chatbot surface.

## Runtime Shape

```text
React dashboard
  -> FastAPI routes
    -> SQLAlchemy repositories
      -> SQLite
    -> optional paragraph-summary-service
      -> asynchronous in-memory mock batches
```

The backend summary endpoint is synchronous in both modes. Local summaries run inline; remote mode submits to the optional paragraph service and polls until its asynchronous in-memory batches finish. Backend jobs and job steps are persisted so reviewers can inspect progress and failures.

## Backend Modules

- `deepreader.api`: HTTP routes, request models, and response models.
- `deepreader.api.upload_safety`: filename, extension, and upload size checks.
- `deepreader.ingest`: text, EPUB, and PDF parsing into deterministic records.
- `deepreader.records`: stable IDs, hashing, and metadata helpers.
- `deepreader.storage`: SQLAlchemy models, database setup, and repositories.
- `deepreader.summarise`: deterministic local summariser, remote service client, artifacts, and job runner.
- `deepreader.retrieval`: BM25, local vector-style retrieval, schema conversion, and fusion.
- `deepreader.answer`: extractive answer selection, citations, and evidence packets.
- `deepreader.security`: lightweight redaction utilities for future sensitive configuration.

## Related Services

- `services/paragraph-summary-service`: Optional mock/Gemini batch scheduling with quota lanes; its inspectable job registry is in-memory and non-durable.

## Frontend Panels

- `DocumentList`: upload and select documents.
- `DocumentRecords`: inspect source records and generated summaries.
- `JobPanel`: inspect jobs, job steps, attempts, failures, and retry failed steps.
- `SearchWorkbench`: run retrieval over source text, summaries, local vector-style scores, and fusion.
- `SearchResults`: inspect ranked results and component scores.
- `QaWorkbench`: run deterministic extractive QA.
- `CitationInspector` and `EvidencePanel`: inspect answer support.

## Data Flow

1. Upload `.txt`, `.epub`, or `.pdf`.
2. Backend validates filename and extension; PDF bytes stream to a hashed temporary file without an application-level size cap.
3. Parsers create ordered records; PDF parsing uses layout-preserving paragraph boundaries and skips empty or obvious table-of-contents pages.
4. Repository stores document and records in SQLite.
5. Stable IDs are derived deterministically from source hash and record position.
6. Summary runner creates a job and one step per record.
7. Existing matching summaries are treated as checkpoints.
8. In opt-in remote mode, the backend submits only records without provider-specific checkpoints, persists the remote job ID and each polled progress snapshot, validates and imports one artifact, and maps compact, sanitized failure details back to its job steps.
9. Search converts records and summaries into retrieval items.
10. QA consumes retrieval results as evidence packets and returns extractive citations.

## Important Data Contracts

Documents include:

- `document_id` as `id` in document response bodies
- `title`
- `source_filename`
- `source_type`
- `source_hash`

Records include:

- `record_id` as `id` in record response bodies
- `document_id`
- `stable_id`
- `order_index`
- `source_text`
- `source_hash`
- `metadata`

Retrieval and QA surfaces keep these inspectable fields:

- `record_id`
- `stable_id`
- `retrieval_method`
- `source_text`
- `summary`
- `metadata`
- `score`
- `component_scores`

## Security And Local Defaults

- No external LLM APIs are called by default.
- No secrets are required for tests or demos.
- CORS defaults are limited to local frontend origins.
- Uploaded file content is not logged.
- Runtime SQLite data lives under `backend/data` locally or in the Docker `backend-data` volume.
- The repo should not include runtime databases, `node_modules`, `dist`, caches, or `.env` files.

## Current Tradeoffs

- SQLite keeps local setup simple.
- Synchronous processing keeps the milestone reviewable without Celery or Redis.
- The optional paragraph service adds asynchronous batching but not durable background processing; the backend waits for it.
- Deterministic summaries and extractive QA make tests reproducible.
- Duplicate ingest is allowed and documented.
- Local vector-style retrieval is a lexical approximation, not embeddings.
