# DeepReader Feature Notes and Validation Plans

## 1. Gemini Batch-Size Escalation Plan

To optimize provider API usage and verify scaling boundaries:
* **Current Validated State**:
  * Live runs validated using a batch size of `5` (`SUMMARY_BATCH_MAX_RECORDS=5`).
  * Synthetic Gemini hard-profile batch tuning completed manually against `gemini-3.1-flash-lite` using synthetic `textbook-hard` records (dense prose, equations, cross-references, caveats, examples). The documented batch tuning results came from manual live Gemini canary/tuning runs (requiring uvicorn and live provider/API calls from the native terminal). The documentation update itself was docs-only. OpenStax was not used, persistent defaults were not changed, and no secrets were printed or committed.
  * Validated configurations up to:
    * 30 records × ~240 words in one provider call (`SUMMARY_BATCH_MAX_RECORDS=32`, cap 2, attempted 1 call).
    * 32 records × ~240 words with cap 2 (attempted 2 calls, completed successfully).
* **Recommended Configurations**:
  * **Balanced Production Candidate**:
    * `SUMMARY_BATCH_MAX_RECORDS=16`
    * `SUMMARY_BATCH_TARGET_TOKENS=10000`
    * `SUMMARY_BATCH_HARD_MAX_TOKENS=14000`
    * `SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=3500`
  * **Aggressive Validation Candidate**:
    * `SUMMARY_BATCH_MAX_RECORDS=24`
    * `SUMMARY_BATCH_TARGET_TOKENS=12000`
    * `SUMMARY_BATCH_HARD_MAX_TOKENS=16000`
    * `SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=4000`
* **Constraints**:
  * Persistent defaults and configuration files were not changed.
  * Do not default to 32 yet.
  * OpenStax remains deferred.

## 2. Pause/Resume Roadmap

* **Phase 1 (Completed & Validated)**:
  * In-memory pause/resume lifecycle controls implemented inside `paragraph-summary-service`.
  * Validated via targeted unit tests and mock-provider smoke tests.
* **Phase 2 (Completed & Validated)**:
  * Backend pause/resume proxy endpoint additions.
  * Polling support updates in the main dashboard server.
* **Phase 3 (Completed & Validated)**:
  * Frontend dashboard controls integration (buttons/status pills).
* **Phase 4 (Completed & Validated)**:
  * Full mock-smoke validation and developer docs update.
  * Makefile execution and helper targets integrated.

## 3. Deferred OpenStax Validation

* OpenStax large-document validation remains **intentionally deferred** until explicitly approved.
* **Guarded Workflow**: A bounded validation workflow is documented at [docs/validation-workflows.md](file:///Users/ianchia/deepreader/docs/validation-workflows.md) and can be checked via `make openstax-bounded-validation-help`.
* **Pre-requisites**: Proceed with OpenStax validation only after:
  * Pipeline lifecycle controls (pause, resume, cancel) are fully integrated across all layers.
  * Batch-size limits are verified and stable.
  * API quota headroom is confirmed.

## 4. Reusable Gemini Canary Script

* A reusable synthetic Gemini batch-size escalation canary script is available at [scripts/canary_gemini_batch_escalation.py](file:///Users/ianchia/deepreader/scripts/canary_gemini_batch_escalation.py).
* Instructions are queryable via `make canary-gemini-batch-help`.
* Runs remain manual/deferred and will consume actual Gemini API quota.

## 5. Tracking Rules

* **docs/validation-log.md**: Records only proven results, completed validation runs, and verified fixes.
* **docs/project-log/feature-notes.md**: Records future planning, candidate configurations, and deferred scaling tasks.
* **Defect tracking**: Any known defects or regressions should be cataloged as GitHub issues or listed in the known-gaps logs.
