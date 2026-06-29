#!/usr/bin/env python3
"""Submit a tiny, non-sensitive Gemini validation job to the running service."""

from __future__ import annotations

import hashlib
import os
import re
import sys
import time

import httpx


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _one_sentence(text: str) -> bool:
    clean = text.strip()
    if not clean or "\n" in clean or re.match(r"^(?:[-*#]|\d+[.)]\s)", clean):
        return False
    return len(re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", clean)) == 1


def _fail(message: str) -> None:
    print(f"Smoke test refused: {message}", file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    provider = os.getenv("SUMMARY_SERVICE_PROVIDER", "mock").strip().lower()
    if provider != "gemini":
        _fail("SUMMARY_SERVICE_PROVIDER must be gemini")
    if not _enabled("SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS"):
        _fail("SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS must be true")
    has_credential = any(
        os.getenv(name, "").strip()
        for name in ("GEMINI_API_KEY_LANE_01", "GEMINI_API_KEYS", "GEMINI_API_KEY")
    )
    if not has_credential:
        _fail("a Gemini API key must be configured")

    source_texts = [
        "A centrifugal pump needs a stable inlet flow for reliable operation.",
        "The controller records pressure once per second during the local test.",
        "Operators should inspect the filter before restarting the demonstration rig.",
    ]
    records = []
    expected_hashes = {}
    for index, source_text in enumerate(source_texts, start=1):
        record_id = f"gemini-smoke-{index:02d}"
        source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        expected_hashes[record_id] = source_hash
        records.append(
            {
                "record_id": record_id,
                "stable_id": record_id,
                "text": source_text,
                "source_hash": source_hash,
                "metadata": {},
            }
        )

    base_url = os.getenv("PARAGRAPH_SUMMARY_SERVICE_URL", "http://127.0.0.1:8001").rstrip("/")
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{base_url}/paragraph-summaries",
            json={
                "document_id": "gemini-smoke-document",
                "records": records,
                "summary_style": "one_sentence",
                "priority": "interactive",
            },
        )
        response.raise_for_status()
        job_id = response.json()["job_id"]

        status_payload = {}
        for _ in range(120):
            status_response = client.get(f"{base_url}/jobs/{job_id}")
            status_response.raise_for_status()
            status_payload = status_response.json()
            if status_payload["status"] in {"completed", "failed"}:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Summary job did not finish within 120 seconds")

        artifact_response = client.get(f"{base_url}/jobs/{job_id}/artifact")
        artifact_response.raise_for_status()
        artifact = artifact_response.json()

    seen_ids = set()
    completed = 0
    failed = 0
    for line in artifact:
        record_id = line.get("record_id")
        if record_id not in expected_hashes or record_id in seen_ids:
            raise RuntimeError("Artifact contains an unknown or duplicate record ID")
        seen_ids.add(record_id)
        if line.get("stable_id") != record_id:
            raise RuntimeError("Artifact stable ID validation failed")
        if line.get("source_hash") != expected_hashes[record_id]:
            raise RuntimeError("Artifact source hash validation failed")
        if line.get("status") == "completed" and _one_sentence(line.get("summary_text", "")):
            completed += 1
        else:
            failed += 1

    if seen_ids != set(expected_hashes):
        raise RuntimeError("Artifact is missing one or more smoke-test records")

    print(f"provider: {provider}")
    print(f"model: {os.getenv('SUMMARY_SERVICE_MODEL', 'gemini-2.5-flash')}")
    print(f"configured lane cap: {os.getenv('SUMMARY_LANE_COUNT', '10')}")
    print(f"active provider identities: {status_payload['stats']['provider_identity_count']}")
    print(f"number of records: {len(records)}")
    print(f"completed count: {completed}")
    print(f"failed count: {failed}")
    print(f"job ID: {job_id}")

    if status_payload.get("status") != "completed" or failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
