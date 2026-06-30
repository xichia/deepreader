NPM ?= pnpm

.PHONY: test backend-dev install-dev frontend-install frontend-dev frontend-build smoke-mock-lifecycle-help smoke-mock-lifecycle canary-gemini-batch-help openstax-bounded-validation-help

install-dev:
	cd backend && python3 -m pip install -e ".[dev]"

test:
	cd backend && pytest

backend-dev:
	cd backend && uvicorn deepreader.api.main:app --reload --host 127.0.0.1 --port 8000

frontend-install:
	cd frontend && $(NPM) install

frontend-dev:
	cd frontend && $(NPM) run dev

frontend-build:
	cd frontend && $(NPM) run build

smoke-mock-lifecycle-help:
	@echo "Local Mock Summary Job Lifecycle Smoke Test Help"
	@echo "================================================="
	@echo "Requirements: mock provider only, no Gemini calls, no OpenStax."
	@echo "Target services must already be running."
	@echo ""
	@echo "Terminal 1 (paragraph-summary-service):"
	@echo "  cd /Users/ianchia/deepreader"
	@echo "  SUMMARY_SERVICE_PROVIDER=mock \\\\"
	@echo "  SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=false \\\\"
	@echo "  SUMMARY_MOCK_PROVIDER_DELAY_MS=750 \\\\"
	@echo "  SUMMARY_BATCH_MAX_RECORDS=1 \\\\"
	@echo "  SUMMARY_MAX_PARALLEL_LANES=1 \\\\"
	@echo "  SUMMARY_LANE_RPM=600 \\\\"
	@echo "  PYTHONPATH=services/paragraph-summary-service \\\\"
	@echo "  uv run --project services/paragraph-summary-service uvicorn app.main:app --host 127.0.0.1 --port 8001"
	@echo ""
	@echo "Terminal 2 (backend remote mode):"
	@echo "  cd /Users/ianchia/deepreader"
	@echo "  DEEPREADER_SUMMARY_BACKEND=remote \\\\"
	@echo "  DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE=true \\\\"
	@echo "  DEEPREADER_REMOTE_SUMMARY_POLL_INTERVAL_SECONDS=0.5 \\\\"
	@echo "  DEEPREADER_REMOTE_SUMMARY_MAX_POLLS=90 \\\\"
	@echo "  PYTHONPATH=backend/src \\\\"
	@echo "  uv run --project backend uvicorn deepreader.api.main:app --host 127.0.0.1 --port 8000"
	@echo ""
	@echo "Terminal 3 (run smoke test):"
	@echo "  make smoke-mock-lifecycle"

smoke-mock-lifecycle:
	uv run --with 'httpx>=0.27' python scripts/smoke_mock_lifecycle.py

canary-gemini-batch-help:
	@echo "Synthetic Gemini Batch-Size Escalation Canary Help"
	@echo "================================================="
	@echo "WARNING: This consumes live Gemini quota when provider-backed summaries are enabled."
	@echo "Requirements: manual execution only, no OpenStax. Confirm quota headroom first."
	@echo ""
	@echo "Credential Safety Warning:"
	@echo "  - Gemini API credentials must already be exported in the shell."
	@echo "  - Do not print secrets."
	@echo "  - Do not commit .env.local."
	@echo "  - This helper intentionally does not source .env.local."
	@echo ""
	@echo "Terminal 1 (paragraph-summary-service configured for live Gemini):"
	@echo "  cd /Users/ianchia/deepreader"
	@echo "  SUMMARY_SERVICE_PROVIDER=gemini \\\\"
	@echo "  SUMMARY_SERVICE_MODEL=gemini-3.1-flash-lite \\\\"
	@echo "  SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=true \\\\"
	@echo "  SUMMARY_BATCH_MAX_RECORDS=<10 or 12> \\\\"
	@echo "  SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=<2 or 1> \\\\"
	@echo "  SUMMARY_LANE_RPM=15 \\\\"
	@echo "  PYTHONPATH=services/paragraph-summary-service \\\\"
	@echo "  uv run --project services/paragraph-summary-service uvicorn app.main:app --host 127.0.0.1 --port 8001"
	@echo ""
	@echo "Terminal 2 (run escalation canary script):"
	@echo "  # For Batch Size 10 (cap 2):"
	@echo "  uv run --with 'httpx>=0.27' python scripts/canary_gemini_batch_escalation.py --total-records 12 --expected-provider gemini --expected-model gemini-3.1-flash-lite --max-provider-calls 2"
	@echo "  # For Batch Size 12 (cap 1):"
	@echo "  uv run --with 'httpx>=0.27' python scripts/canary_gemini_batch_escalation.py --total-records 12 --expected-provider gemini --expected-model gemini-3.1-flash-lite --max-provider-calls 1"

openstax-bounded-validation-help:
	@echo "Guarded Bounded OpenStax Validation Workflow Help"
	@echo "================================================="
	@echo "WARNING: OpenStax validation remains deferred until explicitly approved by the user."
	@echo "This validation workflow consumes live Gemini quota when provider-backed summaries are enabled."
	@echo ""
	@echo "Prerequisites:"
	@echo "  1. Integration of pause, resume, cancel must be complete."
	@echo "  2. Confirm batch-size escalation is verified and stable."
	@echo "  3. Check API quota limits and ensure sufficient headroom."
	@echo ""
	@echo "Constraints:"
	@echo "  - Tiny subset of records only."
	@echo "  - Low provider-call cap & low RPM per alias."
	@echo "  - No persistent configuration default changes."
	@echo "  - Record provider_calls_attempted, failed_records, 429 count, schema errors, and quality."
	@echo "  - STOP IMMEDIATELY on 429 rate limits, schema validation failure, or unexpected status accounting."
	@echo ""
	@echo "Recommended First Bounded Run Configuration:"
	@echo "  SUMMARY_SERVICE_PROVIDER=gemini \\\\"
	@echo "  SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=true \\\\"
	@echo "  SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=2 \\\\"
	@echo "  SUMMARY_BATCH_MAX_RECORDS=5 \\\\"
	@echo "  SUMMARY_LANE_RPM=10 \\\\"
	@echo "  PYTHONPATH=services/paragraph-summary-service \\\\"
	@echo "  uv run --project services/paragraph-summary-service uvicorn app.main:app --host 127.0.0.1 --port 8001"
