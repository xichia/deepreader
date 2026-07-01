# DeepReader Validation Log

## 2026-07-01 — Retry cancelled skipped summary steps (T5D)

Commit: c80efb0 `Retry cancelled skipped summary steps`

Validated:
- 108 backend tests passed.
- Retry selection expanded: `retry_failed_steps` now targets failed steps and skipped steps with `error_code="job_cancelled"`.
- Content/data skips (e.g. `empty_summary`, no error code) are excluded from retry.
- No-candidate behavior preserved (job returned unchanged).
- New focused retry tests added: skipped/job_cancelled retry, non-cancel skip exclusion, mixed-job selection.

## 2026-07-01 — Account cancelled steps as skipped (T5C)

Commit: 1d6a026 `Account cancelled steps as skipped`

Validated:
- 105 backend tests passed.
- `mark_unfinished_steps_cancelled` helper maps pending/running/paused steps to skipped/job_cancelled.
- Local cancel endpoint uses the helper; remote cancel polling path uses the helper and now refreshes progress counters.
- Terminal steps (completed/failed/skipped) are preserved untouched.
- T4 cancel/import race guard preserved.

## 2026-07-01 — Map skipped remote records to skipped steps (T5B)

Commit: 5274c49 `Map skipped remote records to skipped steps`

Validated:
- 103 backend tests passed.
- Remote artifact skipped records map to `JobStep.status="skipped"` with preserved `error_code` and error message.
- Skipped records do not persist `RecordSummary` rows.
- T4 cancel/import race guard intact.

## 2026-07-01 — Add skipped job step accounting foundation (T5A)

Commit: e09dc1b `Add skipped job step accounting foundation`

Validated:
- 94 backend tests passed.
- `JobStep.error_code` (String(50), nullable) column added.
- `Job.skipped_steps` (Integer, default 0) column added.
- `JOB_STATUS_SKIPPED` constant; `SET_VALID_STATUSES` split so job-level validation rejects `skipped`.
- `set_job_step_status` accepts `error_code` kwarg with clearing logic.
- `refresh_job_progress` computes `skipped_steps`.
- SQLite migration helper extends existing databases.
- API: `JobStepOut.error_code`, `JobOut.skipped_steps` surfaced.

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

## 2026-06-30 — Synthetic Gemini hard-profile batch tuning

Validated:
- The documented batch tuning results came from manual live Gemini canary/tuning runs (requiring uvicorn service to be started and live provider/API calls made from the native terminal).
- The documentation update itself was docs-only.
- OpenStax was not used.
- Persistent defaults were not changed.
- No secrets were printed or committed.
- provider: gemini
- model: gemini-3.1-flash-lite
- synthetic records only
- profile: textbook-hard
- dense synthetic textbook-like prose with equations, cross references, caveats, and worked-example style sentences
- no 429s observed

Tuning Results:

1. Default token budget behavior:
Config:
- SUMMARY_BATCH_TARGET_TOKENS=2000
- SUMMARY_BATCH_HARD_MAX_TOKENS=3000
- SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=1000
- SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1

Result:
- 4 records × ~180 words: PASS
- 5 records × ~180 words: failed because token batcher split and provider call cap was exhausted
- finding: default token budget limits hard textbook-like records to roughly 4 records per provider call

2. Raised token budget, batch size 12:
Config:
- SUMMARY_BATCH_MAX_RECORDS=12
- SUMMARY_BATCH_TARGET_TOKENS=6000
- SUMMARY_BATCH_HARD_MAX_TOKENS=8000
- SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=2000
- SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1

Result:
- 8 records × ~180 words: PASS
- 10 records × ~180 words: PASS
- 12 records × ~180 words: PASS
- finding: Gemini handled 12 hard synthetic records in one provider call when token budget allowed it

3. Raised token budget, batch size 24:
Config:
- SUMMARY_BATCH_MAX_RECORDS=24
- SUMMARY_BATCH_TARGET_TOKENS=10000
- SUMMARY_BATCH_HARD_MAX_TOKENS=14000
- SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=3500
- SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1

Result:
- 16 records × ~180 words: PASS
- 20 records × ~180 words: PASS
- 24 records × ~180 words: PASS

4. 240-word hard profile boundary:
Config:
- SUMMARY_BATCH_MAX_RECORDS=24
- SUMMARY_BATCH_TARGET_TOKENS=12000
- SUMMARY_BATCH_HARD_MAX_TOKENS=16000
- SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=4000

Results:
- With provider cap 1:
  - 20 records × ~240 words: PASS
  - 22 records × ~240 words: failed/retried; max provider call cap exhausted
- With provider cap 2:
  - 22 records × ~240 words: PASS
  - 24 records × ~240 words: PASS

5. Higher headroom run:
Config:
- SUMMARY_BATCH_MAX_RECORDS=32
- SUMMARY_BATCH_TARGET_TOKENS=16000
- SUMMARY_BATCH_HARD_MAX_TOKENS=22000
- SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=6000
- SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=2

Results:
- 26 records × ~240 words: PASS, provider_calls_attempted 1
- 28 records × ~240 words: PASS, provider_calls_attempted 1
- 30 records × ~240 words: PASS, provider_calls_attempted 1
- 32 records × ~240 words: PASS, provider_calls_attempted 2
- finding: one-call hard-profile ceiling appears around 30 records / ~7200 synthetic words under this config; 32 is retry/cap-2 headroom, not recommended default

Recommendations:
- Balanced production candidate:
  SUMMARY_BATCH_MAX_RECORDS=16
  SUMMARY_BATCH_TARGET_TOKENS=10000
  SUMMARY_BATCH_HARD_MAX_TOKENS=14000
  SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=3500
- Aggressive validation candidate:
  SUMMARY_BATCH_MAX_RECORDS=24
  SUMMARY_BATCH_TARGET_TOKENS=12000
  SUMMARY_BATCH_HARD_MAX_TOKENS=16000
  SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=4000
- Do not default to 32 yet.
- Persistent defaults were not changed.
- OpenStax remains deferred.

## Current validated state

- Backend pause/resume proxy implemented and tested.
- Frontend pause/resume controls implemented and built.
- Full mock lifecycle smoke passed through backend and paragraph-summary-service.
- OpenStax remains intentionally deferred.
- Gemini live validation includes tiny-canary and synthetic textbook-hard batch tuning up to size 32.

## Remaining gaps

- OpenStax bounded validation remains deferred.
- Gemini batch-size escalation remains deferred.
