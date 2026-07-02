# DeepReader Demo Workflow

This script is for reviewers who want to clone the repo, run the app, and inspect the end-to-end local workflow.

## What this demo is meant to prove

DeepReader is an inspection-first RAG workbench, not a chatbot wrapper. The local demo is designed to prove that the retrieval pipeline is **end-to-end inspectable and reproducible without API keys**:

- Documents ingest into deterministic records with stable IDs and source hashes.
- Source text is preserved and never mutated through summaries or QA.
- Retrieval exposes *how* a result was found: retrieval method, aggregate score, component scores, record ID, and source location.
- QA answers are extractive and remain tied to cited records and inspectable evidence packets (used vs. available).
- Summary processing is a hardened job lifecycle: skipped-step accounting, cancel, and retry are all surfaced in the dashboard and covered by backend tests.
- Remote-cancel partial artifact import is backend reliability work covered by tests, not a demoed UI flow.

Provider (Gemini) and OpenStax validation remain **intentionally deferred** and require explicit opt-in; the default demo runs entirely offline with the deterministic local summariser.

## 1. Start The App

Local terminals:

```bash
make backend-dev
```

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Or Docker:

```bash
docker compose up --build
```

Open `http://127.0.0.1:5173`.

**What this demonstrates:** the project is clone-and-run locally with no secrets. SQLite is the default store and the dashboard connects to the real FastAPI backend. The optional paragraph-summary-service runs in the Compose stack with the deterministic `mock` provider by default.

## 2. Upload A Document

Use the dashboard upload control and choose:

```text
examples/simple_manual.txt
```

The document should appear in the Library panel. Select it.

**What this demonstrates:** real ingestion through `POST /documents/ingest/text` with filename-safety validation and a deterministic `source_hash`. Duplicate uploads intentionally create another document row, while record stable IDs are reused for identical content. PDF uploads stream to a hashed temp file while hashing and have no application-level size cap.

## 3. Inspect Records

In the Records panel, check:

- record count
- `stable_id`
- `order_index`
- section titles where present
- preserved source text

Source text is the ground truth. Summaries and QA evidence point back to these records.

**What this demonstrates:** stable IDs are derived deterministically from source hash and record position, so the same record is traceable across retrieval, summaries, citations, and job steps. Records are immutable source of truth; later pipeline stages annotate rather than mutate them.

## 4. Search Source Text

In Search, run:

```text
what causes low flow?
```

Keep Source text enabled. Inspect:

- retrieval method (`bm25_source_text`)
- aggregate score
- component scores (rendered as readable chips, not raw JSON)
- record ID and stable ID
- source location from section/page/chapter metadata
- source text

A zero-results query shows a styled empty state explaining that no matching records were found and suggesting adjustments — it is not an error.

**What this demonstrates:** the search response is inspection-first. Reviewers can see *which method* produced a hit and *how much each contributed* (component scores), not just an opaque ranking. Missing fields fall back to `"Not reported"` rather than rendering blank or crashing.

## 5. Generate Summaries

Click Generate summaries in the Records panel. The app calls:

```text
POST /documents/{document_id}/summaries/run
```

The run is synchronous for now. When it finishes, summaries appear beside source records.

**What this demonstrates:** the local summariser `local_extractive_v1` is deterministic (whitespace normalisation, deterministic text selection, predictable truncation, summary/source hashes). Checkpointing is based on `record_id` + `summariser_name` + `source_hash`; rerunning skips unchanged records that already have a matching summary.

## 6. Inspect Jobs

In Processing, open the summary job details. Check:

- job type
- status
- completed, failed, and skipped counts
- step type
- target stable ID
- attempts
- errors and `error_code`, if any

Failed or cancelled-unfinished steps can be retried through the local retry endpoint (`POST /jobs/{job_id}/retry-failed`). Content/data skips (e.g. `error_code="empty_summary"`) are excluded from retry.

**What this demonstrates:** the v0.6 lifecycle hardening — skipped-step accounting, `error_code` exposure, retry of failed *and* cancelled-unfinished (skipped/`job_cancelled`) steps, and frontend skipped-step display. This is the reliability work covered by backend tests in the `v0.6-cancel-retry-hardening` tag.

## 7. Search Summaries

In Search, enable Summaries. Try:

```text
bearing wear
```

Inspect whether results came from `bm25_source_text`, `bm25_summary_text`, local vector retrieval, or fusion depending on selected toggles.

**What this demonstrates:** summary-aware search. Component scores show exactly which retrieval method contributed each result, so a reviewer can audit fusion ranking rather than trust an opaque score.

## 8. Ask A QA Question

In the QA workbench, run:

```text
What causes low flow?
```

Inspect:

- extractive answer
- confidence
- citations
- evidence provenance panel: used vs. available evidence, retrieval method, aggregate score, component scores, record ID, and source location
- retrieval settings

This is deterministic extractive QA, not an LLM-generated answer.

**What this demonstrates:** QA evidence provenance (v0.7 T1). Each evidence packet shows whether it was *used in the answer* or merely *available*, plus its retrieval method, scores, and location. Used/available classification uses compound `record_id:retrieval_method` keys to avoid false "used" labels across duplicate record IDs.

## 9. Run Verification

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

**What this demonstrates:** the project is verifiable, not just runnable. Backend tests cover lifecycle hardening, remote-cancel partial artifact import, search, QA evidence, and upload safety. The frontend build runs TypeScript typecheck and Vite production build. GitHub Actions runs both without secrets or real provider calls.

## Reviewer Notes

- No API keys are needed.
- Duplicate uploads create separate document rows today.
- Summaries are local, deterministic, and checkpointed.
- SQLite is the default local store.
- The app intentionally exposes retrieval details instead of hiding them behind chat.
- Provider (Gemini) and OpenStax validation remain **deferred** unless explicitly approved; the local demo is fully deterministic and offline.