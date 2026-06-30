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

## 2026-06-30 — Paragraph service pause/resume

Commit: 830014a `Add paragraph service pause resume`

Validated:
- Paragraph-summary-service tests passed: 71/71.
- Mock-provider pause/resume smoke passed:
  - provider: mock
  - submit status: 202
  - job transitioned running -> paused -> running -> completed
  - pause stopped new batch progress:
    - paused later 1: completed 1, provider_calls_attempted 1
    - paused later 2: completed 1, provider_calls_attempted 1
  - final completed: 20/20
  - final failed: 0
  - provider_calls_attempted: 20 mock calls
  - rate_limit_count: 0
  - artifact uniqueness passed: 20 lines and 20 unique record IDs
  - external Gemini/API calls: 0

Notes:
- This is paragraph-summary-service only.
- Backend pause/resume proxy is not implemented yet.
- Frontend pause/resume controls are not implemented yet.
- Resume is in-memory only; process restart recovery remains out of scope.

## 2026-06-30 — New Gemini 3.1 Flash-Lite key/model validation

Validated:
- Tiny live Gemini canary passed using updated .env.local keys.
- provider: gemini
- model: gemini-3.1-flash-lite
- submitted: 12
- completed: 12
- failed: 0
- provider_calls_attempted: 3
- 429 count: 0
- effective_config.batch_max_records: 5
- effective_config.max_provider_calls_per_job: 4
- live-canary-rec-11 and live-canary-rec-12 completed
- OpenStax was not touched.

Notes:
- This validated the new key/model path.
- It did not change persistent batch-size defaults.
- Future batch-size escalation remains deferred.

## 2026-06-30 — Feature notes project log

Commit: c54d6c7 `Add feature notes project log`

Validated:
- docs/project-log/feature-notes.md added.
- Future Gemini batch-size escalation plan captured.
- Pause/resume roadmap captured.
- OpenStax deferral criteria captured.

## 2026-06-30 — Backend pause/resume proxy

Commit: a22a24f `Add backend pause resume proxy`

Validated:
- Added backend endpoints:
  - POST /jobs/{job_id}/pause
  - POST /jobs/{job_id}/resume
- Remote polling recognizes paused.
- Paused polling cycles do not exhaust DEEPREADER_REMOTE_SUMMARY_MAX_POLLS.
- Remote cancelled is terminal and skips artifact import.
- Local cancelled is not overwritten by later remote statuses.
- Cancel from paused works and remains terminal.
- Backend tests passed:
  - tests/test_jobs_api.py: 12 passed
  - tests/test_remote_summary.py: 18 passed
  - full backend suite: 86 passed
- No uvicorn, canary, OpenStax, or provider calls during implementation.

## 2026-06-30 — Frontend pause/resume controls

Commit: 697c4da `Add frontend pause resume controls`

Validated:
- Added Pause button for running remote jobs.
- Added Resume button for paused remote jobs.
- Cancel remains available for pending, accepted, running, and paused jobs.
- Terminal jobs show no lifecycle controls.
- Paused status styling added.
- Paused progress displays clearly.
- Frontend production build passed with pnpm run build.
- No uvicorn, canary, OpenStax, or provider calls during implementation.

## 2026-06-30 — Mock lifecycle smoke script

Commits:
- a6d86d3 `Add mock lifecycle smoke script`
- 7a70777 `Harden mock lifecycle smoke script`
- 682c98b `Allow paused smoke to settle`

Validated:
- Reusable script added at scripts/smoke_mock_lifecycle.py.
- Static compile passed.
- git diff --check passed.
- Script uses mock provider only.
- Script does not source .env.local.
- Script does not use OpenStax.
- Script does not make Gemini/provider API calls.

## 2026-06-30 — Full local mock lifecycle smoke

Validated manually from native terminal:
- Backend reachable: PASS
- Paragraph-summary-service reachable and configured with mock provider: PASS

Scenario 1:
- submit synthetic document
- job entered running
- pause through backend
- backend status paused
- remote service status paused
- one in-flight batch was allowed to finish during settle
- paused progress then stayed stable
- resume through backend
- job completed
- background run returned 200
- PASS

Scenario 2:
- submit synthetic document
- pause through backend
- cancel through backend
- final status cancelled
- cancelled was not overwritten
- background run returned 200
- PASS

Final result:
- ALL SMOKE SCENARIOS PASSED
- No Gemini calls
- No OpenStax

## 2026-06-30 — Guarded validation workflow tools added

Validated:
- Makefile targets added:
  - `smoke-mock-lifecycle-help` and `smoke-mock-lifecycle`
  - `canary-gemini-batch-help`
  - `openstax-bounded-validation-help`
- Added synthetic Gemini batch-size escalation canary script at `scripts/canary_gemini_batch_escalation.py`.
- Added bounded OpenStax validation workflow documentation at `docs/validation-workflows.md`.
- Both Gemini batch escalation and OpenStax validation remain manual/deferred to protect API quota, and were not run.

## Current validated state

- Backend pause/resume proxy implemented and tested.
- Frontend pause/resume controls implemented and built.
- Full mock lifecycle smoke passed through backend and paragraph-summary-service.
- OpenStax remains intentionally deferred.
- Gemini live validation remains tiny-canary only.

## Remaining gaps

- OpenStax bounded validation remains deferred.
- Gemini batch-size escalation remains deferred.
