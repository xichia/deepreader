# DeepReader Demo Workflow

This script is for reviewers who want to clone the repo, run the app, and inspect the end-to-end local workflow.

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

## 2. Upload A Document

Use the dashboard upload control and choose:

```text
examples/simple_manual.txt
```

The document should appear in the Library panel. Select it.

## 3. Inspect Records

In the Records panel, check:

- record count
- `stable_id`
- `order_index`
- section titles where present
- preserved source text

Source text is the ground truth. Summaries and QA evidence point back to these records.

## 4. Search Source Text

In Search, run:

```text
what causes low flow?
```

Keep Source text enabled. Inspect:

- score
- stable ID
- retrieval method
- source text
- metadata

## 5. Generate Summaries

Click Generate summaries in the Records panel. The app calls:

```text
POST /documents/{document_id}/summaries/run
```

The run is synchronous for now. When it finishes, summaries appear beside source records.

## 6. Inspect Jobs

In Processing, open the summary job details. Check:

- job type
- status
- completed, failed, and skipped counts
- step type
- target stable ID
- attempts
- errors, if any

Failed or cancelled-unfinished steps can be retried through the local retry endpoint. Content/data skips (e.g. `empty_summary`) are excluded from retry.

## 7. Search Summaries

In Search, enable Summaries. Try:

```text
bearing wear
```

Inspect whether results came from `bm25_source_text`, `bm25_summary_text`, local vector retrieval, or fusion depending on selected toggles.

## 8. Ask A QA Question

In the QA workbench, run:

```text
What causes low flow?
```

Inspect:

- extractive answer
- confidence
- citations
- evidence packets
- used and unused evidence
- retrieval settings

This is deterministic extractive QA, not an LLM-generated answer.

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

## Reviewer Notes

- No API keys are needed.
- Duplicate uploads create separate document rows today.
- Summaries are local, deterministic, and checkpointed.
- SQLite is the default local store.
- The app intentionally exposes retrieval details instead of hiding them behind chat.
