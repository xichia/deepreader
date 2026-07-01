# OpenStax Bounded Validation Plan

This document defines the required planning gate and guardrails that must be established before conducting any future validation run using OpenStax datasets.

## 1. Purpose

* **Prevent Unbounded Runs**: This plan exists to prevent accidental, unbounded, or high-cost OpenStax and provider API runs.
* **Transition to Real Content**: It converts prior mock lifecycle and synthetic Gemini validation findings into a structured, safe future real-content validation plan.

---

## 2. Preconditions

Before executing any phase of this plan, the following conditions must be met:

* **Commit Baseline**: The branch `origin/main` must include the following commits:
  * `0349493 Document summary config presets`
  * `f1154b2 Document Gemini batch tuning results`
* **Clean Working Tree**: The local working tree must be completely clean (`git status` shows no modified/untracked files).
* **Quota Verification**: Gemini API quota headroom must be confirmed.
* **Call Cap Configured**: A hard provider-call cap must be explicitly chosen.
* **Explicit Approval**: OpenStax must be explicitly approved before any run.

---

## 3. Recommended First Bounded Configuration

For the initial provider-backed planning run, the **Balanced Preset** from [config-presets.md](file:///Users/ianchia/deepreader/docs/config-presets.md) must be configured:

```ini
SUMMARY_BATCH_MAX_RECORDS=16
SUMMARY_BATCH_TARGET_TOKENS=10000
SUMMARY_BATCH_HARD_MAX_TOKENS=14000
SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS=3500
SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1
```

* **Rationale**: This configuration is highly recommended for first planning because it is synthetic-validated and highly quota-conscious.

> [!IMPORTANT]
> Cap 1 leaves no retry budget. Review the retry-budget implications in [config-presets.md](config-presets.md) (section 4) before choosing between cap 1 and a small higher cap for the actual run.

---

## 4. Initial OpenStax Subset Proposal

This subset is defined for planning only:

* **Tiny Subset**: Use only a very small subset of paragraphs.
* **Bounded Focus**: Select exactly one document or one small section.
* **Limited Paragraph Count**: Restrict the run to a small, pre-counted number of paragraphs.
* **No Full Ingestion**: Avoid ingesting full textbooks.
* **No Unbounded Discovery**: Disable or avoid recursive/unbounded page discovery.
* **No Infinite Retry Loop**: Do not allow retry loops without a strict cap.

---

## 5. Stop Conditions

The run must be immediately aborted or considered failed if any of the following occur:

* **Rate Limits**: Any `429` / rate-limit response from the provider.
* **Cap Reached**: The provider-call cap (`SUMMARY_MAX_PROVIDER_CALLS_PER_JOB`) is reached.
* **Unexpected Splitting**: The batch is split unexpectedly.
* **Failures**: Any failed records occur (`failed_records > 0`).
* **Validation Issues**: Schema or provider response validation failures.
* **State Regression**: Detection of cancellation, pause, or resume regressions.
* **Mismatches**: Artifact import mismatches.
* **Status Overwrites**: Local cancelled status is overwritten by remote status.
* **Quota Ambiguity**: Unclear or unknown quota status.

---

## 6. Expected Observations

During a successful bounded validation run, the following behavior is expected:

* **Remote Progress**: Remote progress should advance cleanly via `remote_completed_records / remote_total_records`.
* **State Syncing**: Pausing the job should mirror correctly and cleanly on the local workspace.
* **Resume Behavior**: Resuming should continue from the last paused state.
* **Idempotent Cancellation**: Cancellation must be terminal, immediate, and idempotent.
* **Skip Unstarted Records**: Any queued or unstarted records after cancellation must be skipped with `error_code="job_cancelled"`.
* **Zero Failure Completion**: A completed bounded run should have `failed_records=0`.

---

## 7. Commands Are Intentionally Omitted

* **No Runnable Commands**: Run commands are intentionally omitted from this plan to prevent accidental execution.
* **Approval Requirement**: Executable commands should only be drafted and run after explicit approval has been granted for OpenStax validation.

---

## 8. Approval Checklist

The following checks must be checked off by the operator before execution:

* [ ] Quota confirmed
* [ ] Subset chosen
* [ ] Provider-call cap chosen
* [ ] Stop conditions accepted
* [ ] Balanced preset accepted
* [ ] Operator confirms no full OpenStax run will occur
* [ ] Explicit approval granted

---

## 9. Persistent Defaults

* **No Defaults Altered**: Persistent system defaults remain completely unchanged.
* **Planning Only**: This document is a planning artifact only and does not reflect runtime system defaults.
