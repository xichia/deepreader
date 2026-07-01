#!/usr/bin/env bash
set -Eeuo pipefail

# Live, quota-bounded scheduler canary. This script never prints API keys or source text.

ROOT="${DEEPREADER_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
SUMMARY_URL="${SUMMARY_URL:-http://127.0.0.1:8001}"
DOCUMENT_ID="${DOCUMENT_ID:-}"
CANARY_SYNTHETIC="${CANARY_SYNTHETIC:-0}"
RESTART_SUMMARY="${RESTART_SUMMARY:-0}"
SUMMARY_PORT="${SUMMARY_PORT:-8001}"

SUMMARY_MAX_PARALLEL_LANES="${SUMMARY_MAX_PARALLEL_LANES:-10}"
SUMMARY_LANE_RPM="${SUMMARY_LANE_RPM:-1}"
SUMMARY_BATCH_MAX_RECORDS="${SUMMARY_BATCH_MAX_RECORDS:-10}"
SUMMARY_BATCH_TARGET_TOKENS="${SUMMARY_BATCH_TARGET_TOKENS:-3000}"
SUMMARY_BATCH_HARD_MAX_TOKENS="${SUMMARY_BATCH_HARD_MAX_TOKENS:-12000}"
SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS="${SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS:-4000}"
CANARY_MAX_CALLS="${CANARY_MAX_CALLS:-80}"
POLL_SECONDS="${POLL_SECONDS:-30}"
MAX_POLL_MINUTES="${MAX_POLL_MINUTES:-20}"
CANARY_MAX_RECORDS="${CANARY_MAX_RECORDS:-0}"

RUN_DIR="${RUN_DIR:-$ROOT/.tmp/gemini-scheduler-canary-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$RUN_DIR"

SUMMARY_PID=""

cleanup() {
  if [[ -n "$SUMMARY_PID" ]]; then
    echo
    echo "Stopping canary-owned summary service PID $SUMMARY_PID"
    kill "$SUMMARY_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

require_cmd curl
require_cmd python3

echo "DeepReader Gemini scheduler canary"
echo "Root:        $ROOT"
echo "Backend:     $BACKEND_URL"
echo "Summary:     $SUMMARY_URL"
echo "Run dir:     $RUN_DIR"
echo

if [[ "$RESTART_SUMMARY" == "1" ]]; then
  echo "Restarting paragraph summary service on port $SUMMARY_PORT..."
  if command -v lsof >/dev/null 2>&1; then
    EXISTING_PIDS="$(lsof -ti ":$SUMMARY_PORT" || true)"
    if [[ -n "$EXISTING_PIDS" ]]; then
      echo "Killing existing process(es) on port $SUMMARY_PORT: $EXISTING_PIDS"
      kill -9 $EXISTING_PIDS >/dev/null 2>&1 || true
      sleep 1
    fi
  fi

  (
    cd "$ROOT/services/paragraph-summary-service"
    source .venv/bin/activate
    set -a
    source "$ROOT/.env.local"
    set +a
    export SUMMARY_MAX_PARALLEL_LANES
    export SUMMARY_LANE_RPM
    export SUMMARY_BATCH_MAX_RECORDS
    export SUMMARY_BATCH_TARGET_TOKENS
    export SUMMARY_BATCH_HARD_MAX_TOKENS
    export SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS
    export SUMMARY_MAX_PROVIDER_CALLS_PER_JOB="$CANARY_MAX_CALLS"
    export PYTHONPATH=.
    exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$SUMMARY_PORT"
  ) >"$RUN_DIR/summary-service.log" 2>&1 &
  SUMMARY_PID="$!"
  echo "Summary service PID: $SUMMARY_PID"
  echo "Summary service log: $RUN_DIR/summary-service.log"
fi

summary_ready=0
for _ in {1..40}; do
  if curl -fsS "$SUMMARY_URL/health" >/dev/null 2>&1; then
    summary_ready=1
    break
  fi
  if [[ -n "$SUMMARY_PID" ]] && ! kill -0 "$SUMMARY_PID" >/dev/null 2>&1; then
    echo "Summary service exited early. Last log lines:" >&2
    tail -80 "$RUN_DIR/summary-service.log" >&2 || true
    exit 1
  fi
  sleep 0.5
done

if [[ "$summary_ready" != "1" ]]; then
  echo "Summary service did not become ready at $SUMMARY_URL" >&2
  exit 1
fi
echo "Summary service is responding."

export ROOT BACKEND_URL SUMMARY_URL DOCUMENT_ID CANARY_SYNTHETIC RUN_DIR
export SUMMARY_MAX_PARALLEL_LANES SUMMARY_BATCH_MAX_RECORDS
export CANARY_MAX_CALLS POLL_SECONDS MAX_POLL_MINUTES CANARY_MAX_RECORDS

python3 - <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import sys
import time
from typing import Any
import urllib.error
import urllib.request

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
SUMMARY_URL = os.environ["SUMMARY_URL"].rstrip("/")
DOCUMENT_ID = os.environ.get("DOCUMENT_ID", "").strip()
CANARY_SYNTHETIC = os.environ.get("CANARY_SYNTHETIC", "0") == "1"
RUN_DIR = os.environ["RUN_DIR"]
EXPECTED_MAX_LANES = int(os.environ["SUMMARY_MAX_PARALLEL_LANES"])
EXPECTED_BATCH_MAX_RECORDS = int(os.environ["SUMMARY_BATCH_MAX_RECORDS"])
CANARY_MAX_CALLS = int(os.environ["CANARY_MAX_CALLS"])
POLL_SECONDS = int(os.environ["POLL_SECONDS"])
MAX_POLL_MINUTES = int(os.environ["MAX_POLL_MINUTES"])
CANARY_MAX_RECORDS = int(os.environ.get("CANARY_MAX_RECORDS", "0"))


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dump(filename: str, value: Any) -> None:
    with open(os.path.join(RUN_DIR, filename), "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)


def request_json(
    method: str,
    url: str,
    body: Any | None = None,
    *,
    timeout: float = 30,
) -> tuple[int, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body_out = json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            body_out = {"error": "non-JSON HTTP error response"}
        return exc.code, body_out
    except Exception as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def require_get(url: str, *, timeout: float = 30) -> Any:
    status, body = request_json("GET", url, timeout=timeout)
    if not 200 <= status < 300:
        raise RuntimeError(f"GET {url} failed with status {status}: {body}")
    return body


def resolve_document() -> dict[str, Any]:
    documents = require_get(f"{BACKEND_URL}/documents")
    if not isinstance(documents, list) or not documents:
        raise RuntimeError("Backend has no documents to use for the canary")

    if DOCUMENT_ID:
        candidate_ids = [DOCUMENT_ID]
    else:
        candidate_ids = [str(item["id"]) for item in reversed(documents) if "id" in item]

    details = [require_get(f"{BACKEND_URL}/documents/{document_id}") for document_id in candidate_ids]
    selected = details[0]
    if not DOCUMENT_ID:
        selected = max(details, key=lambda item: (int(item.get("record_count", 0)), int(item["id"])))
    return selected


def build_summary_request(document_id: int) -> tuple[dict[str, Any], int]:
    records = require_get(f"{BACKEND_URL}/documents/{document_id}/records", timeout=120)
    if not isinstance(records, list) or not records:
        raise RuntimeError(f"Document {document_id} has no records")
    total_count = len(records)
    if CANARY_MAX_RECORDS > 0 and total_count > CANARY_MAX_RECORDS:
        print(f"Real-document canary record limit active: using first {CANARY_MAX_RECORDS} of {total_count} records")
        records = records[:CANARY_MAX_RECORDS]
    payload_records = [
        {
            "record_id": record["stable_id"],
            "stable_id": record["stable_id"],
            "source_ref": (
                f"page {record['page_number']}" if record.get("page_number") is not None else None
            ),
            "text": record["source_text"],
            "source_hash": record["source_hash"],
            "metadata": record.get("metadata") or {},
        }
        for record in records
    ]
    return (
        {
            "document_id": str(document_id),
            "records": payload_records,
            "summary_style": "one_sentence",
            "priority": "interactive",
        },
        len(payload_records),
    )


def build_synthetic_summary_request() -> tuple[dict[str, Any], int]:
    payload_records = []
    for index in range(1, 5052):
        stable_id = f"scheduler-canary-{index:05d}"
        text = f"Synthetic scheduler canary paragraph {index} contains no workspace document data."
        payload_records.append(
            {
                "record_id": stable_id,
                "stable_id": stable_id,
                "source_ref": "synthetic canary",
                "text": text,
                "source_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "metadata": {"paragraph_index": index},
            }
        )
    return (
        {
            "document_id": "synthetic-gemini-scheduler-canary",
            "records": payload_records,
            "summary_style": "one_sentence",
            "priority": "interactive",
        },
        len(payload_records),
    )


def state_from(job: dict[str, Any]) -> dict[str, Any]:
    stats = job.get("stats") if isinstance(job.get("stats"), dict) else {}
    effective = stats.get("effective_config") if isinstance(stats.get("effective_config"), dict) else {}
    return {
        "status": job.get("status"),
        "provider_identity_count": stats.get("provider_identity_count"),
        "configured_parallel_lanes": stats.get("scheduler_parallelism")
        or effective.get("max_parallel_lanes"),
        "active_lanes": stats.get("active_lanes"),
        "total_records": job.get("total_records"),
        "total_batches": stats.get("total_batches"),
        "completed_batches": stats.get("completed_batches"),
        "failed_batches": stats.get("failed_batches"),
        "completed_records": job.get("completed_records"),
        "failed_records": job.get("failed_records"),
        "provider_calls_attempted": stats.get("provider_calls_attempted"),
        "provider_calls_by_alias": stats.get("provider_calls_by_alias"),
        "retry_count": stats.get("retry_count"),
        "rate_limit_count": stats.get("rate_limit_count"),
        "rate_limit_count_by_alias": stats.get("rate_limit_count_by_alias"),
        "cooldown_count": stats.get("cooldown_count"),
        "cooldown_aliases": stats.get("cooldown_aliases"),
        "batch_max_records": stats.get("batch_max_records"),
        "provider_aliases": stats.get("provider_aliases"),
    }


def print_state(poll_number: int, state: dict[str, Any]) -> None:
    print(
        f"[{now()}] poll={poll_number} status={state['status']} "
        f"lanes={state['active_lanes']}/{state['configured_parallel_lanes']} "
        f"ids={state['provider_identity_count']} "
        f"batches={state['completed_batches']}/{state['total_batches']} "
        f"failed_batches={state['failed_batches']} "
        f"calls={state['provider_calls_attempted']}/{CANARY_MAX_CALLS} "
        f"retries={state['retry_count']} rate_limits={state['rate_limit_count']} "
        f"cooldowns={state['cooldown_count']} batch_max_records={state['batch_max_records']}",
        flush=True,
    )
    print(f"  calls_by_alias={state['provider_calls_by_alias']}", flush=True)
    print(f"  rate_limits_by_alias={state['rate_limit_count_by_alias']}", flush=True)
    if state["cooldown_aliases"]:
        print(f"  cooldown_aliases={state['cooldown_aliases']}", flush=True)


backend_openapi = require_get(f"{BACKEND_URL}/openapi.json")
summary_health = require_get(f"{SUMMARY_URL}/health")
dump(
    "health.json",
    {
        "backend": {"title": backend_openapi.get("info", {}).get("title")},
        "summary": summary_health,
    },
)
print(f"Backend responding at {BACKEND_URL}/openapi.json")
print(f"Summary service responding at {SUMMARY_URL}/health")

if CANARY_SYNTHETIC:
    document_id: int | str = "synthetic-gemini-scheduler-canary"
    document = {"source_type": "synthetic", "title": "Gemini scheduler canary"}
    request_body, record_count = build_synthetic_summary_request()
else:
    document = resolve_document()
    document_id = int(document["id"])
    request_body, record_count = build_summary_request(document_id)
dump(
    "selected-document.json",
    {
        "document_id": document_id,
        "record_count": record_count,
        "source_type": document.get("source_type"),
        "title": document.get("title"),
    },
)
print(f"Using document_id={document_id} records={record_count}")
print(f"Canary max provider calls={CANARY_MAX_CALLS}")

status, launch_body = request_json(
    "POST",
    f"{SUMMARY_URL}/paragraph-summaries",
    request_body,
    timeout=180,
)
dump("launch-response.json", {"status": status, "body": launch_body})
if not 200 <= status < 300 or not isinstance(launch_body, dict) or not launch_body.get("job_id"):
    raise RuntimeError(f"Summary launch failed with status {status}: {launch_body}")

job_id = str(launch_body["job_id"])
print(f"Launched summary job_id={job_id}")
max_polls = max(1, (MAX_POLL_MINUTES * 60) // POLL_SECONDS)
final_state: dict[str, Any] | None = None

for poll_number in range(1, max_polls + 1):
    job = require_get(f"{SUMMARY_URL}/jobs/{job_id}")
    dump(f"poll-{poll_number:03d}.json", job)
    final_state = state_from(job)
    print_state(poll_number, final_state)
    if final_state["status"] in {"completed", "failed"}:
        break
    time.sleep(POLL_SECONDS)

if final_state is None:
    raise RuntimeError("No summary status was observed")

print("\nFinal canary state:")
print(json.dumps(final_state, indent=2, sort_keys=True))
print(f"Artifacts written to: {RUN_DIR}")

expected_min_batches = (record_count + EXPECTED_BATCH_MAX_RECORDS - 1) // EXPECTED_BATCH_MAX_RECORDS
calls_by_alias = final_state.get("provider_calls_by_alias") or {}
expected_aliases = {f"gemini_{index:02d}" for index in range(1, EXPECTED_MAX_LANES + 1)}
observed_aliases = {alias for alias, count in calls_by_alias.items() if int(count) > 0}

checks = {
    "provider identities": final_state.get("provider_identity_count") == EXPECTED_MAX_LANES,
    "parallel lane cap": final_state.get("configured_parallel_lanes") == EXPECTED_MAX_LANES,
    "active lanes bounded": int(final_state.get("active_lanes") or 0) <= EXPECTED_MAX_LANES,
    "record cap": final_state.get("batch_max_records") == EXPECTED_BATCH_MAX_RECORDS,
    "batch count": int(final_state.get("total_batches") or 0) >= expected_min_batches,
    "all aliases used": expected_aliases.issubset(observed_aliases),
    "provider call ceiling": int(final_state.get("provider_calls_attempted") or 0)
    <= CANARY_MAX_CALLS,
}

print("\nInterpretation:")
for label, passed in checks.items():
    print(f"- {'PASS' if passed else 'CHECK'}: {label}")

if not all(checks.values()):
    sys.exit(1)
PY
