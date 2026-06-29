# Gemini Provider Validation

## Purpose

DeepReader v0.6 validates the existing PDF-to-paragraph summary pipeline against the real Gemini API. It does not add a new retrieval or QA model: Gemini only creates one-sentence paragraph summaries inside `paragraph-summary-service`. DeepReader still persists the original source text, validates imported artifacts against document ID, stable ID, and source hash, and uses original source text for citation-grade QA evidence.

The v0.5 behavior remains the default. `SUMMARY_SERVICE_PROVIDER=mock` requires no API key and makes no external request. Gemini requests are possible only when the provider is explicitly `gemini` and `SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=true`.

> Privacy warning: Gemini free-tier requests leave the local machine. Use synthetic or non-sensitive PDFs only, and review the current Gemini API data-use terms before testing.

## Quota lanes

The intended ten-lane experiment uses ten independent Gemini projects and quota pools. Ten keys created in one project must not be assumed to provide ten independent quotas. DeepReader does not discover quotas automatically; it only applies the configured per-lane cooldown and concurrency caps.

`SUMMARY_LANE_RPM` is a per-key limit. Every unique key gets its own Gemini client, safe alias (`gemini_01`, `gemini_02`, and so on), RPM clock, one-request in-flight cap, and rate-limit cooldown. Effective aggregate RPM is `configured provider identities * SUMMARY_LANE_RPM`; `SUMMARY_MAX_PARALLEL_LANES` separately caps concurrent in-flight calls.

`SUMMARY_LANE_COUNT` is a legacy/configured upper bound, not a requirement that every numbered variable be populated. The service accepts numbered `GEMINI_API_KEY_LANE_01` variables, a comma/newline/semicolon-separated `GEMINI_API_KEYS` pool, or the single-key `GEMINI_API_KEY` fallback. Duplicate values are collapsed. Active lanes never exceed the number of unique configured identities or `SUMMARY_MAX_PARALLEL_LANES`.

Key values are retained only in runtime lane/provider objects and are excluded from API responses, artifacts, configuration summaries, and logs. Job status exposes aliases, calls and rate-limit counts per alias, cooldown aliases, scheduler parallelism, batch counts, and the effective non-secret configuration.

## Start with one lane

Create an ignored `.env.local` at the repository root:

```env
DEEPREADER_SUMMARY_BACKEND=remote
DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE=true
PARAGRAPH_SUMMARY_SERVICE_URL=http://127.0.0.1:8001

SUMMARY_SERVICE_PROVIDER=gemini
SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=true
SUMMARY_SERVICE_MODEL=gemini-2.5-flash

SUMMARY_LANE_COUNT=1
SUMMARY_LANE_RPM=4
SUMMARY_MAX_PARALLEL_LANES=1

SUMMARY_BATCH_TARGET_TOKENS=50000
SUMMARY_BATCH_HARD_MAX_TOKENS=75000
SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=25000
SUMMARY_BATCH_MAX_RECORDS=10

SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1000

GEMINI_API_KEY_LANE_01=replace_me
```

`.env.local` and `.env.*.local` are ignored by Git. Never place a real key in `.env.example`, documentation, test fixtures, shell history, screenshots, or logs.

## Run locally

### One-Command Dev Runner (Honcho / Foreman)

You can run all three services concurrently using the provided `Procfile.gemini` and your preferred process manager (like `honcho`, `foreman`, or `overmind`). First, make sure you have created `.env.local` at the root, then run:

```bash
# Example using honcho (must be run from your active virtualenv containing honcho/foreman)
honcho -e .env.local -f Procfile.gemini start
```

If shell/process managers are unavailable, fallback to the three-terminal setup below.

### Three-Terminal Setup

Terminal 1 — paragraph service:

```bash
cd services/paragraph-summary-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
set -a
source ../../.env.local
set +a
PYTHONPATH=. uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Terminal 2 — backend:

```bash
cd backend
source .venv/bin/activate
set -a
source ../.env.local
set +a
PYTHONPATH=src uvicorn deepreader.api.main:app --host 127.0.0.1 --port 8000
```

Terminal 3 — frontend:

```bash
cd frontend
pnpm dev
```

Open `http://127.0.0.1:5173`, upload a small non-sensitive PDF, inspect its extracted records, and generate summaries. The records panel shows source text beside the current summary; a Gemini import is labeled with the `gemini` summariser name. Search with source and summary terms, ask a QA question, and inspect citations/evidence to confirm quoted text and `source_hash` still refer to the original `source_text` rather than the summary.

## Staged ramp

1. Run one lane against the tiny synthetic smoke records.
2. Keep one lane and summarize one tiny non-sensitive PDF.
3. Configure two independent lanes and force two small batches.
4. Configure ten independent lanes and use the stability-oriented 50k batch target.
5. Increase token budgets only after observing actual rate-limit behavior.

The recommended batch target was reduced from 200k to 50k after a real run packed 347,169 estimated input tokens into only two large batches. Both provider batches failed after retries, and the resulting artifact exposed only `provider_exception` without actionable detail. The 50k target is a stability and diagnostic default, not a hard architectural limit.

The recommended local values are a 50,000-token batch target, a 75,000-token hard maximum, 25,000 reserved output tokens, 10 records per call, and 1,000 provider calls per job. The record cap matters for paragraph-heavy documents: 5,051 tiny records produce 506 batches rather than a few oversized token-only batches. `SUMMARY_MAX_INPUT_TOKENS_PER_JOB` remains disabled when unset, empty, or `0`; a positive integer can opt into a job-level cap.

### Stage A: synthetic smoke test

With the paragraph service running and the one-lane environment loaded:

```bash
cd services/paragraph-summary-service
source .venv/bin/activate
set -a
source ../../.env.local
set +a
python scripts/gemini_smoke_test.py
```

The script submits three tiny records, validates record IDs, stable IDs, source hashes, and one-sentence results, and prints only provider/model/count/job metadata. It never prints the key or source paragraphs.

### Stage B: tiny PDF

Keep one lane and one provider call. Upload a tiny PDF, generate summaries, then verify records, hashes, side-by-side source/summary display, search, and source-backed QA citations.

### Stage C: two lanes

```env
SUMMARY_LANE_COUNT=2
SUMMARY_MAX_PARALLEL_LANES=2
SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=2
GEMINI_API_KEY_LANE_01=...
GEMINI_API_KEY_LANE_02=...
```

Use a slightly larger PDF or a smaller target so the packer creates two batches.

### Stage D: ten lanes

```env
SUMMARY_LANE_COUNT=10
SUMMARY_MAX_PARALLEL_LANES=10
SUMMARY_LANE_RPM=4
SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1000
SUMMARY_BATCH_TARGET_TOKENS=50000
SUMMARY_BATCH_HARD_MAX_TOKENS=75000
SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=25000
SUMMARY_BATCH_MAX_RECORDS=10

GEMINI_API_KEY_LANE_01=...
GEMINI_API_KEY_LANE_02=...
GEMINI_API_KEY_LANE_03=...
GEMINI_API_KEY_LANE_04=...
GEMINI_API_KEY_LANE_05=...
GEMINI_API_KEY_LANE_06=...
GEMINI_API_KEY_LANE_07=...
GEMINI_API_KEY_LANE_08=...
GEMINI_API_KEY_LANE_09=...
GEMINI_API_KEY_LANE_10=...
```

Observe batch count, alias assignment, calls per alias, completed/failed records, retries, and rate-limit behavior before changing budgets.

### Large-document verification overrides

After loading `.env.local`, start the summary service with the effective scheduler values inline:

```bash
cd services/paragraph-summary-service
source .venv/bin/activate
set -a
source ../../.env.local
set +a

SUMMARY_MAX_PARALLEL_LANES=10 \
SUMMARY_LANE_RPM=1 \
SUMMARY_BATCH_MAX_RECORDS=10 \
SUMMARY_BATCH_TARGET_TOKENS=3000 \
SUMMARY_BATCH_HARD_MAX_TOKENS=12000 \
SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=4000 \
SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1000 \
PYTHONPATH=. python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

For a 5,051-record job, `/jobs/{job_id}` should report 506 `total_batches`, at most ten provider identities/parallel lanes, `provider_calls_by_alias` distributed across configured aliases, and `batch_max_records: 10`. Provider-call logs should always report `batch_records` at or below ten.

## Running the full PDF test

Follow this workflow to validate PDF extraction and remote summary generation end-to-end:

1. **Start the services**: Either run the one-command Honcho runner or start the three separate terminals as detailed in the "Run locally" section.
2. **Upload PDF**: Click the upload control in the dashboard library panel and upload `deepreader_gemini_smoke_test.pdf` (or any small synthetic PDF).
3. **Expect 2 records**: Ensure the document records panel loads exactly 2 paragraph records parsed from the PDF.
4. **Generate summaries**: Click the "Generate summaries" button.
5. **Expected result**:
   - The panel should display "2 records / 2 summaries" when complete.
   - No importer errors should be logged in the console or shown on screen.
   - The document records list should display the source text and the generated summary together side-by-side.
   - Running QA queries (e.g. asking a question about the PDF text) should produce extractive citations referencing verbatim original source text, not the summary.
6. **If the job times out**:
   - Increase `DEEPREADER_REMOTE_SUMMARY_MAX_POLLS` in `.env.local` to allow more time (e.g. 180).
   - Confirm that the configured per-lane RPM and project quotas are compatible before changing cooldowns.
   - Click "Retry failed" to resume the timed-out job. The backend will reuse the same remote job ID and query the summary service directly without resubmitting duplicate work.
   - To debug or inspect the paragraph service job directly, run these diagnostic commands:
     ```bash
     curl -s http://127.0.0.1:8001/jobs | python3 -m json.tool
     curl -s http://127.0.0.1:8001/jobs/JOB_ID | python3 -m json.tool
     curl -s http://127.0.0.1:8001/jobs/JOB_ID/artifact | python3 -m json.tool
     curl -s http://127.0.0.1:8000/jobs | python3 -m json.tool
     ```

## Rate-limit recovery

On a 429, only the affected alias enters a jittered exponential cooldown; other aliases continue. If every identity is cooling down, their workers wait rather than issuing immediate retries. Other provider failures use a shorter jittered retry backoff. The dispatcher still respects the job-wide call cap and writes sanitized failed artifact lines after exhaustion. Each line includes a stable error code plus provider/model, lane, safe provider alias, attempt/retry, and available usage details without credentials or source text. Do not rapidly resubmit. Wait for the project quota window/cooldown, then run Generate summaries again. The backend job checkpoints already imported Gemini summaries with matching source hashes and resubmits only records that still need work.

## Offline verification

No test calls Gemini. Provider tests inject fake response/client objects.

```bash
cd backend
pytest

cd ../services/paragraph-summary-service
PYTHONPATH=. pytest

cd ../../frontend
pnpm run build

cd ..
docker compose config
```

Docker is optional for this branch. The checked-in Compose configuration remains mock-only and contains no credentials.

## Known limitations

- Free-tier privacy and data-use caveats apply; do not submit private PDFs.
- Paragraph-service jobs and cooldown state are in memory and not durable.
- Limiters are process-local; run one paragraph-service worker for this local demo.
- With 506 batches, ten identities, and one RPM per identity, a clean full run takes at least about 51 minutes before retries or provider latency.
- Scanned PDFs have no OCR path.
- The service does not use the Gemini provider Batch API.
- Local `.env.local` files are not a production secret manager.
- Quotas and independence between projects are not discovered automatically.
- There is no auth, Redis, Celery, durable queue, or production deployment configuration.
