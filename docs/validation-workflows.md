# Guarded Bounded OpenStax Validation Workflow

> [!WARNING]
> OpenStax large-document validation remains **intentionally deferred** and must not be run without explicit user approval.
> This workflow consumes live Gemini API quota when provider-backed summaries are enabled. Confirm quota limits and API key settings before running.

This document describes the validation workflow for integrating large-document validation using actual OpenStax content.

## 1. Prerequisites

Before attempting bounded OpenStax validation, ensure:
1. **Pipeline Lifecycle Controls**: Integration of pause, resume, and cancel is complete and verified across all services.
2. **Batch-Size Escalation**: Synthetic batch-size scaling limits are verified and stable (tested via `scripts/canary_gemini_batch_escalation.py`).
3. **API Quota Verification**: Headroom for the target Gemini API model has been checked and confirmed.

## 2. Quota Check Instructions

Determine active Gemini API tier limits and active lane allocation. Check that `lane_rpm` times `lane_count` does not exceed overall API quota ceilings.

## 3. Recommended First Bounded Run Configuration

Start with an extremely limited bounded environment to minimize API call count and cost:

- **SUMMARY_SERVICE_PROVIDER**: `gemini`
- **SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS**: `true`
- **SUMMARY_MAX_PROVIDER_CALLS_PER_JOB**: `2` (Force the job to terminate/fail if it attempts more than 2 calls)
- **SUMMARY_BATCH_MAX_RECORDS**: `5`
- **SUMMARY_LANE_RPM**: `10`

Run command (Terminal 1):
```bash
SUMMARY_SERVICE_PROVIDER=gemini \
SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=true \
SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=2 \
SUMMARY_BATCH_MAX_RECORDS=5 \
SUMMARY_LANE_RPM=10 \
PYTHONPATH=services/paragraph-summary-service \
uv run --project services/paragraph-summary-service uvicorn app.main:app --host 127.0.0.1 --port 8001
```

## 4. Run Execution & Safety Gates

1. **Tiny Subset Only**: Only submit a small sample of records (e.g. 5-10 paragraphs), do not upload entire multi-hundred page books.
2. **Stop Immediately On**:
   - Any `429` rate limiting code.
   - Any schema validation error in API requests/responses.
   - Unexpected job status accounting (e.g. status stuck in running, incorrect count, failed steps).
3. **Validation metrics to record**:
   - `provider_calls_attempted`
   - `failed_records`
   - `429` occurrences
   - schema error details
   - generated artifact visual quality

## 5. Cleanup Instructions

Always clean up generated database records and summary artifacts afterwards to keep the local workspace pristine.
