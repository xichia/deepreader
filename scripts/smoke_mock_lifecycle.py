"""
Local Smoke Test Script for DeepReader Job Lifecycle (Pause/Resume/Cancel).

Scenarios Covered:
1. Pause & Resume: Submit job -> Observe running -> Pause -> Verify paused -> Wait and verify progress is stable -> Resume -> Verify completed.
2. Cancel: Submit job -> Pause -> Cancel -> Verify status remains cancelled and is not overwritten.

Requirements:
- Target already-running local services:
  - backend: http://127.0.0.1:8000
  - paragraph-summary-service: http://127.0.0.1:8001
- Uses mock provider only (no external API calls/secrets).

Usage instructions:

Terminal 1 (paragraph-summary-service):
    cd services/paragraph-summary-service
    SUMMARY_SERVICE_PROVIDER=mock \
    SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=false \
    SUMMARY_MOCK_PROVIDER_DELAY_MS=500 \
    SUMMARY_BATCH_MAX_RECORDS=1 \
    SUMMARY_MAX_PARALLEL_LANES=1 \
    poetry run uvicorn app.main:app --host 127.0.0.1 --port 8001

Terminal 2 (backend):
    cd backend
    DEEPREADER_SUMMARY_BACKEND=remote \
    DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE=true \
    DEEPREADER_REMOTE_SUMMARY_POLL_INTERVAL_SECONDS=0.5 \
    DEEPREADER_REMOTE_SUMMARY_MAX_POLLS=60 \
    .venv/bin/uvicorn deepreader.api.main:app --reload --host 127.0.0.1 --port 8000

Terminal 3 (run smoke test):
    uv run --with 'httpx>=0.27' python scripts/smoke_mock_lifecycle.py
"""

import asyncio
import httpx
import sys

BACKEND_URL = "http://127.0.0.1:8000"
SERVICE_URL = "http://127.0.0.1:8001"

async def test_health():
    async with httpx.AsyncClient() as client:
        # Backend health check (get documents list)
        try:
            res = await client.get(f"{BACKEND_URL}/documents")
            res.raise_for_status()
            print("PASS: Backend is reachable.")
        except Exception as e:
            print(f"FAIL: Backend not reachable at {BACKEND_URL}: {e}")
            sys.exit(1)

        # Service health check (configured to use mock provider)
        try:
            res = await client.get(f"{SERVICE_URL}/health")
            res.raise_for_status()
            data = res.json()
            provider = data.get("provider") or data.get("summary_service_provider")
            if provider != "mock":
                print(f"FAIL: Service provider is '{provider}', expected 'mock'.")
                sys.exit(1)
            print("PASS: Paragraph-summary-service is reachable and configured with mock provider.")
        except Exception as e:
            print(f"FAIL: Paragraph-summary-service not reachable at {SERVICE_URL}: {e}")
            sys.exit(1)

async def run_scenario_1():
    print("\n--- Running Scenario 1: Pause and Resume ---")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Ingest a synthetic document
        ingest_res = await client.post(
            f"{BACKEND_URL}/documents/ingest/text",
            files={"file": ("smoke_synthetic.txt", b"Paragraph 1\n\nParagraph 2\n\nParagraph 3\n\nParagraph 4", "text/plain")},
        )
        ingest_res.raise_for_status()
        doc_id = ingest_res.json()["document"]["id"]
        print(f"Ingested synthetic document ID: {doc_id}")

        # Start job run in the background (since it blocks synchronously)
        run_task = asyncio.create_task(client.post(f"{BACKEND_URL}/documents/{doc_id}/summaries/run"))

        # Wait briefly for job to be submitted and active
        await asyncio.sleep(0.8)

        # Query jobs to find our active job
        jobs_res = await client.get(f"{BACKEND_URL}/jobs")
        jobs_res.raise_for_status()
        jobs = [j for j in jobs_res.json() if j["document_id"] == doc_id]
        if not jobs:
            print("FAIL: No job found for our document.")
            sys.exit(1)
        job = jobs[0]
        job_id = job["id"]
        print(f"Found active job ID: {job_id}, status: {job['status']}")

        # Assert status is running (or paused/pending)
        if job["status"] not in {"running", "pending", "accepted"}:
            print(f"FAIL: Job {job_id} is in unexpected state: {job['status']}")
            sys.exit(1)

        # Pause the job
        print("Pausing job...")
        pause_res = await client.post(f"{BACKEND_URL}/jobs/{job_id}/pause")
        pause_res.raise_for_status()
        paused_job = pause_res.json()
        print(f"Paused job response status: {paused_job['status']}")
        assert paused_job["status"] == "paused", f"Expected status 'paused', got '{paused_job['status']}'"

        # Verify remote status in service is paused
        remote_res = await client.get(f"{SERVICE_URL}/jobs/{paused_job['remote_job_id']}")
        remote_res.raise_for_status()
        remote_data = remote_res.json()
        print(f"Remote service job status: {remote_data['status']}")
        assert remote_data["status"] == "paused", f"Expected remote status 'paused', got '{remote_data['status']}'"

        # Wait briefly and verify progress does not advance
        progress_before = paused_job["completed_steps"]
        print(f"Waiting to verify progress stays stable at {progress_before}...")
        await asyncio.sleep(1.5)
        check_res = await client.get(f"{BACKEND_URL}/jobs/{job_id}")
        check_res.raise_for_status()
        check_job = check_res.json()
        progress_after = check_job["completed_steps"]
        print(f"Progress check: before={progress_before}, after={progress_after}")
        assert progress_before == progress_after, f"Progress advanced from {progress_before} to {progress_after} while paused!"

        # Resume the job
        print("Resuming job...")
        resume_res = await client.post(f"{BACKEND_URL}/jobs/{job_id}/resume")
        resume_res.raise_for_status()
        resumed_job = resume_res.json()
        print(f"Resumed job response status: {resumed_job['status']}")
        assert resumed_job["status"] == "running", f"Expected status 'running', got '{resumed_job['status']}'"

        # Now await the run task to finish
        print("Waiting for job completion...")
        run_res = await run_task
        run_res.raise_for_status()
        final_job = run_res.json()
        print(f"Final job status: {final_job['status']}")
        assert final_job["status"] == "completed", f"Expected final status 'completed', got '{final_job['status']}'"
        assert final_job["completed_steps"] == final_job["total_steps"], "Expected all steps completed"
        assert final_job["failed_steps"] == 0, "Expected zero failed steps"
        print("PASS: Scenario 1 completed successfully.")

async def run_scenario_2():
    print("\n--- Running Scenario 2: Pause and Cancel ---")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Ingest a synthetic document
        ingest_res = await client.post(
            f"{BACKEND_URL}/documents/ingest/text",
            files={"file": ("smoke_cancel.txt", b"Cancel paragraph 1\n\nCancel paragraph 2", "text/plain")},
        )
        ingest_res.raise_for_status()
        doc_id = ingest_res.json()["document"]["id"]
        print(f"Ingested synthetic document ID: {doc_id}")

        # Start job run in the background
        run_task = asyncio.create_task(client.post(f"{BACKEND_URL}/documents/{doc_id}/summaries/run"))

        # Wait briefly for job to start
        await asyncio.sleep(0.8)

        # Get active job ID
        jobs_res = await client.get(f"{BACKEND_URL}/jobs")
        jobs_res.raise_for_status()
        jobs = [j for j in jobs_res.json() if j["document_id"] == doc_id]
        if not jobs:
            print("FAIL: No job found for our document.")
            sys.exit(1)
        job = jobs[0]
        job_id = job["id"]

        # Pause
        print("Pausing job...")
        await (await client.post(f"{BACKEND_URL}/jobs/{job_id}/pause")).raise_for_status()

        # Cancel
        print("Cancelling job...")
        cancel_res = await client.post(f"{BACKEND_URL}/jobs/{job_id}/cancel")
        cancel_res.raise_for_status()
        cancelled_job = cancel_res.json()
        print(f"Cancelled job response status: {cancelled_job['status']}")
        assert cancelled_job["status"] == "cancelled", f"Expected cancelled, got {cancelled_job['status']}"

        # Wait for background task to finish
        try:
            run_res = await run_task
            final_run_job = run_res.json()
            print(f"Final background run job status: {final_run_job['status']}")
            assert final_run_job["status"] == "cancelled", f"Expected final job status cancelled, got {final_run_job['status']}"
        except Exception as e:
            print(f"Background run request finished with: {e}")

        # Verify status is not overwritten
        await asyncio.sleep(1.0)
        verify_res = await client.get(f"{BACKEND_URL}/jobs/{job_id}")
        verify_res.raise_for_status()
        verify_job = verify_res.json()
        print(f"Verify job status remains cancelled: {verify_job['status']}")
        assert verify_job["status"] == "cancelled", "Cancelled status was overwritten!"

        print("PASS: Scenario 2 completed successfully.")

async def main():
    await test_health()
    await run_scenario_1()
    await run_scenario_2()
    print("\nALL SMOKE SCENARIOS PASSED.")

if __name__ == "__main__":
    asyncio.run(main())
