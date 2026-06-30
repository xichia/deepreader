# DeepReader Feature Notes and Validation Plans

## 1. Gemini Batch-Size Escalation Plan

To optimize provider API usage and verify scaling boundaries:
* **Current Validated State**: Live runs have been validated using a batch size of `5` (`SUMMARY_BATCH_MAX_RECORDS=5`).
* **Future Candidate Batch Size 10**:
  * Run with provider call cap set to `2` (`SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=2`).
  * Execute via inline env overrides only.
* **Future Candidate Batch Size 12**:
  * Run with provider call cap set to `1` (`SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1`).
  * Execute via inline env overrides only.
* **Constraints**:
  * Do not modify persistent defaults or configuration files yet.
  * Do not use OpenStax documents for initial batch-size escalation; use small, safe synthetic sets only.

## 2. Pause/Resume Roadmap

* **Phase 1 (Completed & Validated)**:
  * In-memory pause/resume lifecycle controls implemented inside `paragraph-summary-service`.
  * Validated via targeted unit tests and mock-provider smoke tests.
* **Phase 2 (Planned)**:
  * Backend pause/resume proxy endpoint additions.
  * Polling support updates in the main dashboard server.
* **Phase 3 (Planned)**:
  * Frontend dashboard controls integration (buttons/status pills).
* **Phase 4 (Planned)**:
  * Full mock-smoke validation and developer docs update.

## 3. Deferred OpenStax Validation

* OpenStax large-document validation remains **intentionally deferred**.
* **Pre-requisites**: Proceed with OpenStax validation only after:
  * Pipeline lifecycle controls (pause, resume, cancel) are fully integrated across all layers.
  * Batch-size limits are verified and stable.
  * API quota headroom is confirmed.

## 4. Tracking Rules

* **docs/validation-log.md**: Records only proven results, completed validation runs, and verified fixes.
* **docs/project-log/feature-notes.md**: Records future planning, candidate configurations, and deferred scaling tasks.
* **Defect tracking**: Any known defects or regressions should be cataloged as GitHub issues or listed in the known-gaps logs.
