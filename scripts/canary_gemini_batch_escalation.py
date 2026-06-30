"""
Synthetic Gemini Batch-Size Escalation Canary Validation Script.

WARNING: This consumes live Gemini quota when provider-backed summaries are enabled.
This script is for manual execution only and must not be run as part of the automated build.
Ensure sufficient quota headroom before running.

Future Native-Terminal commands:

Scenario A: Batch size 10, provider cap 2
  Terminal 1 (paragraph-summary-service):
    cd /Users/ianchia/deepreader
    SUMMARY_SERVICE_PROVIDER=gemini \\
    SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=true \\
    SUMMARY_BATCH_MAX_RECORDS=10 \\
    SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=2 \\
    SUMMARY_LANE_RPM=15 \\
    PYTHONPATH=services/paragraph-summary-service \\
    uv run --project services/paragraph-summary-service uvicorn app.main:app --host 127.0.0.1 --port 8001

  Terminal 2 (run escalation canary script):
    uv run --with 'httpx>=0.27' python scripts/canary_gemini_batch_escalation.py --total-records 10 --expected-provider gemini --max-provider-calls 2

Scenario B: Batch size 12, provider cap 1
  Terminal 1 (paragraph-summary-service):
    cd /Users/ianchia/deepreader
    SUMMARY_SERVICE_PROVIDER=gemini \\
    SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=true \\
    SUMMARY_BATCH_MAX_RECORDS=12 \\
    SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1 \\
    SUMMARY_LANE_RPM=15 \\
    PYTHONPATH=services/paragraph-summary-service \\
    uv run --project services/paragraph-summary-service uvicorn app.main:app --host 127.0.0.1 --port 8001

  Terminal 2 (run escalation canary script):
    uv run --with 'httpx>=0.27' python scripts/canary_gemini_batch_escalation.py --total-records 12 --expected-provider gemini --max-provider-calls 1
"""

import argparse
import asyncio
import hashlib
import sys
import uuid
import httpx

def str_to_bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

async def main():
    parser = argparse.ArgumentParser(description="Canary Gemini Batch Escalation Test")
    parser.add_argument("--total-records", type=int, default=12)
    parser.add_argument("--expected-provider", type=str, default="gemini")
    parser.add_argument("--expected-model", type=str, default="gemini-3.1-flash-lite")
    parser.add_argument("--max-provider-calls", type=int, default=None)
    parser.add_argument("--require-zero-429", type=str_to_bool, default=True)
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8001")
    args = parser.parse_args()

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Check health and verify provider/model configuration
        try:
            res = await client.get(f"{args.base_url}/health")
            res.raise_for_status()
            health_data = res.json()
        except Exception as e:
            print(f"FAIL: Paragraph-summary-service not reachable at {args.base_url}: {e}")
            sys.exit(1)

        health_provider = health_data.get("provider") or health_data.get("summary_service_provider")
        health_settings = health_data.get("settings", {})
        health_model = health_settings.get("model") or health_settings.get("summary_service_model") or health_data.get("model")

        print(f"health provider/model: {health_provider}/{health_model}")

        # Check if provider matches what we expect
        if args.expected_provider and health_provider != args.expected_provider:
            print(f"FAIL: Expected provider '{args.expected_provider}', but health shows '{health_provider}'")
            sys.exit(1)

        # Submit synthetic records
        doc_id = str(uuid.uuid4())
        records = []
        for i in range(args.total_records):
            text = f"Synthetic paragraph content {i} to test batch-size escalation without external file dependencies."
            source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            records.append({
                "record_id": f"rec-{i}",
                "stable_id": f"rec-{i}",
                "text": text,
                "source_hash": source_hash,
                "metadata": {}
            })

        payload = {
            "document_id": doc_id,
            "records": records,
            "summary_style": "one_sentence",
            "priority": "interactive"
        }

        print(f"Submitting job with {args.total_records} records...")
        try:
            submit_res = await client.post(f"{args.base_url}/paragraph-summaries", json=payload)
            submit_res.raise_for_status()
            job_data = submit_res.json()
            job_id = job_data["job_id"]
        except Exception as e:
            print(f"FAIL: Job submission failed: {e}")
            sys.exit(1)

        print(f"submitted total: {args.total_records}")
        print(f"Job ID: {job_id}")

        # Poll status
        while True:
            try:
                status_res = await client.get(f"{args.base_url}/jobs/{job_id}")
                status_res.raise_for_status()
                job = status_res.json()
            except Exception as e:
                print(f"FAIL: Querying job status failed: {e}")
                sys.exit(1)

            status = job["status"]
            if status in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(1.0)

        stats = job.get("stats", {})
        provider_calls_attempted = stats.get("provider_calls_attempted", 0)
        rate_limit_count = stats.get("rate_limit_count", 0)

        eff = stats.get("effective_config", {})
        batch_max_records = eff.get("batch_max_records")
        max_provider_calls_per_job = eff.get("max_provider_calls_per_job")

        print(f"final status: {status}")
        print(f"completed/failed/total: {job['completed_records']}/{job['failed_records']}/{job['total_records']}")
        print(f"provider_calls_attempted: {provider_calls_attempted}")
        print(f"rate_limit_count: {rate_limit_count}")
        print(f"effective_config.batch_max_records: {batch_max_records}")
        print(f"effective_config.max_provider_calls_per_job: {max_provider_calls_per_job}")

        # Assertions
        failures = []

        if status != "completed":
            failures.append(f"Job status is '{status}', expected 'completed'")
        if job["failed_records"] != 0:
            failures.append(f"Failed records is {job['failed_records']}, expected 0")
        if job["completed_records"] != args.total_records:
            failures.append(f"Completed records is {job['completed_records']}, expected {args.total_records}")
        if args.max_provider_calls is not None and provider_calls_attempted > args.max_provider_calls:
            failures.append(f"provider_calls_attempted {provider_calls_attempted} exceeded limit {args.max_provider_calls}")
        if args.require_zero_429 and rate_limit_count != 0:
            failures.append(f"rate_limit_count is {rate_limit_count}, expected 0")

        if failures:
            print("\nFAILURES DETECTED:")
            for f in failures:
                print(f" - {f}")
            sys.exit(1)

        print("\nPASS: All batch escalation assertions satisfied.")

if __name__ == "__main__":
    asyncio.run(main())
