"""
Local Smoke Test Script for DeepReader Job Lifecycle (Pause/Resume/Cancel).

Scenarios Covered:
1. Pause & Resume: Submit job -> Observe running -> Pause -> Verify paused -> Wait and verify progress is stable -> Resume -> Verify completed.
2. Cancel: Submit job -> Pause -> Cancel -> Verify status remains cancelled and is not overwritten.

Requirements:
- Target already-running local services:
  - backend: http://127.0.0.1:8000
  - paragraph-summary-service: http://127.0.0.1:8001
- Uses mock provider only (no external Gemini/OpenStax/provider API calls/secrets).
- Services must already be running.

Usage instructions:

Terminal 1 paragraph-summary-service (from repository root):
    SUMMARY_SERVICE_PROVIDER=mock \
    SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=false \
    SUMMARY_MOCK_PROVIDER_DELAY_MS=750 \
    SUMMARY_BATCH_MAX_RECORDS=1 \
    SUMMARY_MAX_PARALLEL_LANES=1 \
    SUMMARY_LANE_RPM=600 \
    PYTHONPATH=services/paragraph-summary-service \
    uv run --project services/paragraph-summary-service \
    uvicorn app.main:app --host 127.0.0.1 --port 8001

Terminal 2 backend (from repository root):
    DEEPREADER_SUMMARY_BACKEND=remote \
    DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE=true \
    DEEPREADER_REMOTE_SUMMARY_POLL_INTERVAL_SECONDS=0.5 \
    DEEPREADER_REMOTE_SUMMARY_MAX_POLLS=90 \
    PYTHONPATH=backend/src \
    uv run --project backend \
    uvicorn deepreader.api.main:app --host 127.0.0.1 --port 8000

Terminal 3 smoke (from repository root):
    uv run --with 'httpx>=0.27' python scripts/smoke_mock_lifecycle.py
"""

import asyncio
import contextlib
import httpx
import sys

BACKEND_URL = "http://127.0.0.1:8000"
SERVICE_URL = "http://127.0.0.1:8001"

def get_progress(job):
    """Retrieve progress based on remote completed records if present, otherwise local steps."""
    if job.get("remote_total_records") is not None and job.get("remote_total_records") > 0:
        return job.get("remote_completed_records") or 0
    return job.get("completed_steps") or 0

async def wait_for_job_for_document(client: httpx.AsyncClient, doc_id: int, timeout_seconds: float = 10.0):
    """Poll jobs endpoint until a job associated with the document is found (ideally with remote_job_id populated)."""
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < timeout_seconds:
        res = await client.get(f"{BACKEND_URL}/jobs")
        res.raise_for_status()
        jobs = [j for j in res.json() if j["document_id"] == doc_id]
        if jobs:
            job = jobs[0]
            if job.get("remote_job_id"):
                return job
        await asyncio.sleep(0.1)

    # Fallback return or raise
    res = await client.get(f"{BACKEND_URL}/jobs")
    jobs = [j for j in res.json() if j["document_id"] == doc_id]
    if jobs:
        return jobs[0]
    raise TimeoutError(f"Job for document {doc_id} was not created within {timeout_seconds} seconds.")

async def wait_for_job_status(client: httpx.AsyncClient, job_id: int, allowed_statuses: set[str], timeout_seconds: float = 30.0):
    """Poll a job until its status matches one of the allowed statuses."""
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < timeout_seconds:
        res = await client.get(f"{BACKEND_URL}/jobs/{job_id}")
        res.raise_for_status()
        job = res.json()
        if job["status"] in allowed_statuses:
            return job
        await asyncio.sleep(0.1)
    raise TimeoutError(f"Job {job_id} did not transition to one of {allowed_statuses} within {timeout_seconds} seconds.")

async def wait_for_paused_progress_to_settle(client: httpx.AsyncClient, job_id: int, timeout_seconds: float = 10.0, stable_window_seconds: float = 1.5):
    """Poll the job, ensuring it remains paused, and wait for already in-flight progress to settle."""
    start_time = asyncio.get_event_loop().time()
    last_progress = None
    last_change_time = start_time

    while asyncio.get_event_loop().time() - start_time < timeout_seconds:
        res = await client.get(f"{BACKEND_URL}/jobs/{job_id}")
        res.raise_for_status()
        job = res.json()

        if job["status"] != "paused":
            raise AssertionError(f"Job {job_id} left 'paused' status early. Current status: {job['status']}")

        prog = get_progress(job)
        now = asyncio.get_event_loop().time()

        if last_progress is None:
            last_progress = prog
            last_change_time = now
        elif prog != last_progress:
            print(f"Paused progress advanced from {last_progress} to {prog} during settle period.")
            last_progress = prog
            last_change_time = now
        else:
            if now - last_change_time >= stable_window_seconds:
                return job, prog

        await asyncio.sleep(0.2)
    raise TimeoutError(f"Job {job_id} progress did not settle within {timeout_seconds} seconds.")

async def drain_run_task(run_task: asyncio.Task | None, label: str):
    """Safely cancel and await a background run task to prevent unretrieved exceptions."""
    if run_task is None:
        return
    if run_task.done():
        try:
            res = run_task.result()
            print(f"Background run task '{label}' finished on its own: {res.status_code}")
        except Exception as e:
            print(f"Background run task '{label}' finished with error: {e}")
    else:
        try:
            await asyncio.wait_for(asyncio.shield(run_task), timeout=0.2)
            res = run_task.result()
            print(f"Background run task '{label}' completed during drain: {res.status_code}")
        except asyncio.TimeoutError:
            print(f"Background run task '{label}' still pending, cancelling...")
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, httpx.HTTPError, Exception):
                await run_task
            print(f"Background run task '{label}' successfully cancelled/drained.")
        except Exception as e:
            print(f"Background run task '{label}' finished with error during drain: {e}")

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
    run_task = None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Generate at least 12 paragraphs programmatically to avoid startup races
            doc_content = "\n\n".join(
                f"This is paragraph {i} of our synthetic smoke test document, designed to run through the mock provider."
                for i in range(1, 13)
            )

            # Ingest the synthetic document
            ingest_res = await client.post(
                f"{BACKEND_URL}/documents/ingest/text",
                files={"file": ("smoke_synthetic.txt", doc_content.encode("utf-8"), "text/plain")},
            )
            ingest_res.raise_for_status()
            doc_id = ingest_res.json()["document"]["id"]
            print(f"Ingested synthetic document ID: {doc_id}")

            # Start job run in the background (since it blocks synchronously)
            run_task = asyncio.create_task(client.post(f"{BACKEND_URL}/documents/{doc_id}/summaries/run"))

            # Wait for the job to start and find it
            job = await wait_for_job_for_document(client, doc_id)
            job_id = job["id"]
            print(f"Found active job ID: {job_id}, status: {job['status']}")

            # Pause the job
            print("Pausing job...")
            pause_res = await client.post(f"{BACKEND_URL}/jobs/{job_id}/pause")
            pause_res.raise_for_status()
            paused_job = pause_res.json()
            print(f"Pause response progress: {get_progress(paused_job)}")
            assert paused_job["status"] == "paused", f"Expected status 'paused', got '{paused_job['status']}'"

            # Verify remote status in service is paused
            remote_res = await client.get(f"{SERVICE_URL}/jobs/{paused_job['remote_job_id']}")
            remote_res.raise_for_status()
            remote_data = remote_res.json()
            print(f"Remote service job status: {remote_data['status']}")
            assert remote_data["status"] == "paused", f"Expected remote status 'paused', got '{remote_data['status']}'"

            # Wait for paused progress to settle
            settled_job, settled_progress = await wait_for_paused_progress_to_settle(client, job_id)
            print(f"Settled paused progress: {settled_progress}")

            # Wait another stable_window_seconds and assert progress hasn't changed
            await asyncio.sleep(1.5)
            check_res = await client.get(f"{BACKEND_URL}/jobs/{job_id}")
            check_res.raise_for_status()
            check_job = check_res.json()
            final_progress = get_progress(check_job)
            print(f"Final paused stability progress check: {final_progress}")
            assert check_job["status"] == "paused", f"Expected job {job_id} to still be paused, got {check_job['status']}"
            assert final_progress == settled_progress, f"Progress advanced from {settled_progress} to {final_progress} after settling!"

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
    finally:
        await drain_run_task(run_task, "scenario_1_run")

async def run_scenario_2():
    print("\n--- Running Scenario 2: Pause and Cancel ---")
    run_task = None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Generate at least 8 paragraphs programmatically
            doc_content = "\n\n".join(
                f"This is paragraph {i} of our cancel-smoke test document, designed to run through the mock provider."
                for i in range(1, 9)
            )

            # Ingest the synthetic document
            ingest_res = await client.post(
                f"{BACKEND_URL}/documents/ingest/text",
                files={"file": ("smoke_cancel.txt", doc_content.encode("utf-8"), "text/plain")},
            )
            ingest_res.raise_for_status()
            doc_id = ingest_res.json()["document"]["id"]
            print(f"Ingested synthetic document ID: {doc_id}")

            # Start job run in the background
            run_task = asyncio.create_task(client.post(f"{BACKEND_URL}/documents/{doc_id}/summaries/run"))

            # Wait for the job to start and find it
            job = await wait_for_job_for_document(client, doc_id)
            job_id = job["id"]

            # Pause
            print("Pausing job...")
            pause_res = await client.post(f"{BACKEND_URL}/jobs/{job_id}/pause")
            pause_res.raise_for_status()
            paused_job = pause_res.json()
            assert paused_job["status"] == "paused", f"Expected job {job_id} to be paused."

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
    finally:
        await drain_run_task(run_task, "scenario_2_run")

async def main():
    await test_health()
    await run_scenario_1()
    await run_scenario_2()
    print("\nALL SMOKE SCENARIOS PASSED.")

if __name__ == "__main__":
    asyncio.run(main())
