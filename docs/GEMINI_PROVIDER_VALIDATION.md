# Gemini Provider Validation

## Purpose

DeepReader v0.6 validates the existing PDF-to-paragraph summary pipeline against the real Gemini API. It does not add a new retrieval or QA model: Gemini only creates one-sentence paragraph summaries inside `paragraph-summary-service`. DeepReader still persists the original source text, validates imported artifacts against document ID, stable ID, and source hash, and uses original source text for citation-grade QA evidence.

The v0.5 behavior remains the default. `SUMMARY_SERVICE_PROVIDER=mock` requires no API key and makes no external request. Gemini requests are possible only when the provider is explicitly `gemini` and `SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=true`.

> Privacy warning: Gemini free-tier requests leave the local machine. Use synthetic or non-sensitive PDFs only, and review the current Gemini API data-use terms before testing.

## Quota lanes

The intended ten-lane experiment uses ten independent Gemini projects and quota pools. Ten keys created in one project must not be assumed to provide ten independent quotas. DeepReader does not discover quotas automatically; it only applies the configured per-lane cooldown and concurrency caps.

When Gemini is selected, startup/request validation requires one non-empty key for every configured lane. Key values are retained only in runtime lane/provider objects and are excluded from API responses, artifacts, configuration summaries, and logs.

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
SUMMARY_LANE_RPM=1
SUMMARY_MAX_PARALLEL_LANES=1

SUMMARY_BATCH_TARGET_TOKENS=1000
SUMMARY_BATCH_HARD_MAX_TOKENS=3000
SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=1000

SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1
SUMMARY_MAX_INPUT_TOKENS_PER_JOB=3000

GEMINI_API_KEY_LANE_01=replace_me
```

`.env.local` and `.env.*.local` are ignored by Git. Never place a real key in `.env.example`, documentation, test fixtures, shell history, screenshots, or logs.

## Run locally

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
4. Configure ten independent lanes and use conservative small batches.
5. Increase token budgets only after observing actual rate-limit behavior.

Do not begin with 250k-token batches. The initial validation defaults are a 5,000-token batch target, a 10,000-token hard maximum, 2,000 reserved output tokens, and a 50,000 estimated-input-token job cap.

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
SUMMARY_LANE_RPM=1
SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=10
SUMMARY_BATCH_TARGET_TOKENS=5000
SUMMARY_BATCH_HARD_MAX_TOKENS=10000
SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=2000
SUMMARY_MAX_INPUT_TOKENS_PER_JOB=50000

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

Observe batch count, lane assignment, completed/failed records, retries, and rate-limit behavior before changing budgets.

## Rate-limit recovery

On a 429 or other provider exception, the dispatcher retries only within the configured call cap and writes failed artifact lines after exhaustion. Do not rapidly resubmit. Wait for the project quota window/cooldown, reduce parallel lanes or batch count if needed, then run Generate summaries again. The new backend job checkpoints already imported Gemini summaries with matching source hashes and resubmits only records that still need work.

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
- Scanned PDFs have no OCR path.
- The service does not use the Gemini provider Batch API.
- Local `.env.local` files are not a production secret manager.
- Quotas and independence between projects are not discovered automatically.
- There is no auth, Redis, Celery, durable queue, or production deployment configuration.
