# DeepReader Validation Log

## 2026-06-30 — Gemini provider status fix

Commit: e5c21b3 `Constrain Gemini summary statuses`

Validated:
- Targeted Gemini provider tests passed: 23/23.
- Tiny live Gemini canary passed:
  - 12 submitted
  - 12 completed
  - 0 failed
  - provider_calls_attempted: 3
  - 429 count: 0
  - effective_config.batch_max_records: 5
  - canary-rec-11 and canary-rec-12 completed
- Raw keys were not exposed.
- OpenStax was not touched.

Notes:
- The original failure was caused by unconstrained Gemini result statuses.
- The fix constrained Gemini summary item status to canonical values:
  - completed
  - skipped
  - failed
- The correct env var for service record batching is SUMMARY_BATCH_MAX_RECORDS.
- SUMMARY_PROVIDER_BATCH_SIZE does not control effective_config.batch_max_records.

## 2026-06-30 — Progress bar UI

Commit: 2b506dc `Add job progress bar`

Validated:
- Frontend build passed.
- Progress API already exposed local and remote progress fields.
- UI now displays a progress bar.
- UI prefers remote paragraph-summary progress when remote_total_records is present.
- UI falls back to local backend step progress otherwise.

Notes:
- Pause/resume/cancel controls were not added in this patch.

## 2026-06-30 — Job cancellation

Commit: 1c4f1e7 `Add job cancellation`

Validated:
- Backend tests passed.
- Paragraph-summary-service tests passed.
- Frontend build passed.
- Added real cancel endpoints:
  - Backend: POST /jobs/{job_id}/cancel
  - Paragraph summary service: POST /jobs/{job_id}/cancel
- Cancel is terminal and idempotent.
- In-flight batches are allowed to finish naturally.
- Cancel prevents new scheduler work after cancellation is observed.

Notes:
- Pause and resume remain unimplemented.

## 2026-06-30 — Mock summary provider

Commit: cd4a552 `Add mock summary provider`

Validated:
- Paragraph-summary-service tests passed: 66/66.
- Mock provider accepts jobs without external provider/API calls.
- Mock provider does not require Gemini credentials.
- Mock mode supports deterministic local testing.
- SUMMARY_MOCK_PROVIDER_DELAY_MS can slow mock batches for cancellation/progress smoke tests.

Notes:
- Mock provider is for offline validation and smoke testing.
- It should not be confused with live Gemini provider validation.

## 2026-06-30 — Cancellation accounting refinement

Commit: 84e3d4d `Refine cancellation accounting`

Validated:
- Paragraph-summary-service tests passed: 67/67.
- Backend tests passed: 78/78.
- Mock-provider cancellation accounting smoke passed:
  - provider: mock
  - submit status: 202
  - job transitioned from running to cancelled
  - final status: cancelled
  - final completed: 15
  - final failed: 0
  - final total: 500
  - mock batch calls attempted: 3
  - rate_limit_count: 0
  - external Gemini/API calls: 0
- Port 8001 was cleaned up after smoke testing.
- Working tree was clean after validation.

Notes:
- Unstarted records after cancellation are now marked as skipped with job_cancelled rather than failed.
- True provider errors still count as failed.
- provider_calls_attempted may be nonzero in mock mode because it counts local mock batch calls, not external Gemini calls.

## Current validated state

- Gemini provider path: fixed and tiny live-canary validated.
- Mock provider: implemented for offline smoke tests.
- Progress API: ready.
- Progress bar UI: implemented.
- Cancel: implemented, tested, and mock-smoke validated.
- Cancellation accounting: refined and mock-smoke validated.
- OpenStax: not touched during these validations.
- Pause: missing.
- Resume: missing.

## Remaining gaps

- Pause/resume design and implementation.
- Optional full UI smoke for cancel button through browser.
- Optional larger bounded non-OpenStax document validation.
- OpenStax validation remains intentionally deferred.
