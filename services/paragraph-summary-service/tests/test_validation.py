import pytest
import app.scheduler.dispatcher as dispatcher_module
from app.providers.gemini import ResponseParseError, SchemaValidationError
from app.scheduler.dispatcher import (
    JobState,
    _process_batch,
    _provider_error_code,
    _run_job_background,
)
from app.records.schema import InputRecord, SummaryArtifactLine, SummaryRequest
from app.scheduler.lane import QuotaLane

class MockFaultyProvider:
    def __init__(self, fault_type):
        self.fault_type = fault_type
        self.call_count = 0

    async def summarize_batch(self, document_id, batch, summary_style):
        self.call_count += 1
        results = []
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).isoformat()
        if self.fault_type == "exception":
            raise ValueError("Provider error")
        elif self.fault_type == "missing":
            # Returns only first record
            results.append(SummaryArtifactLine(
                document_id=document_id, record_id=batch[0].record_id, source_hash=batch[0].source_hash,
                summary_text="summary", summary_style=summary_style, provider="mock",
                model="test", template_version="v1", status="completed", created_at=now_str
            ))
        elif self.fault_type == "duplicate":
            for _ in range(2):
                results.append(SummaryArtifactLine(
                    document_id=document_id, record_id=batch[0].record_id, source_hash=batch[0].source_hash,
                    summary_text="summary", summary_style=summary_style, provider="mock",
                    model="test", template_version="v1", status="completed", created_at=now_str
                ))
        elif self.fault_type == "malformed":
            results.append(SummaryArtifactLine(
                document_id=document_id, record_id=batch[0].record_id, source_hash=batch[0].source_hash,
                summary_text="", summary_style=summary_style, provider="mock",
                model="test", template_version="v1", status="completed", created_at=now_str
            ))
        elif self.fault_type == "unknown":
            results.append(SummaryArtifactLine(
                document_id=document_id, record_id="unknown_id", source_hash="none",
                summary_text="summary", summary_style=summary_style, provider="mock",
                model="test", template_version="v1", status="completed", created_at=now_str
            ))
        elif self.fault_type == "source_hash":
            results.append(SummaryArtifactLine(
                document_id=document_id, record_id=batch[0].record_id, source_hash="wrong_hash",
                summary_text="summary", summary_style=summary_style, provider="mock",
                model="test", template_version="v1", status="completed", created_at=now_str
            ))
        elif self.fault_type == "failed_status":
            results.append(SummaryArtifactLine(
                document_id=document_id, record_id=batch[0].record_id, source_hash=batch[0].source_hash,
                summary_text="provider failure", summary_style=summary_style, provider="mock",
                model="test", template_version="v1", status="failed", created_at=now_str
            ))
        return results

@pytest.mark.asyncio
async def test_validation_exception():
    job = JobState("job1", "doc1", 2)
    batch = [InputRecord(record_id="r1", text="a", source_hash="a")]
    provider = MockFaultyProvider("exception")
    await _process_batch(job, batch, provider, "style")
    assert provider.call_count == 3 # 1 initial + 2 retries
    assert job.failed_records == 1
    assert job.stats["completed_batches"] == 0
    assert job.stats["failed_batches"] == 1
    assert len(job.artifact_lines) == 1
    assert job.artifact_lines[0].status == "failed"
    assert job.artifact_lines[0].error_code == "provider_exception"
    assert job.artifact_lines[0].message == "ValueError: Provider error"


@pytest.mark.asyncio
async def test_provider_exception_artifact_preserves_sanitized_diagnostics():
    secret = "test-secret-lane-key"
    source_marker = "FULL_SOURCE_TEXT_MUST_NOT_LEAK"

    class RaisingProvider:
        async def summarize_batch(self, document_id, batch, summary_style):
            error = RuntimeError(
                f"429 rate limit exceeded; api_key={secret}; contents: {source_marker}"
            )
            error.usage = {"prompt_tokens": 42, "total_tokens": 42}
            raise error

    lane = QuotaLane("lane_03", rpm=6000, api_key=secret)
    job = JobState("job-diagnostic", "doc1", 1)
    batch = [InputRecord(record_id="r1", stable_id="stable-r1", text=source_marker, source_hash="h1")]

    await _process_batch(job, batch, RaisingProvider(), "one_sentence", lane=lane)

    line = job.artifact_lines[0]
    assert line.status == "failed"
    assert line.record_id == "r1"
    assert line.stable_id == "stable-r1"
    assert line.error_code == "provider_rate_limited"
    assert "rate limit" in (line.message or "")
    assert secret not in (line.message or "")
    assert source_marker not in (line.message or "")
    assert line.lane_id == "lane_03"
    assert line.attempt_count == 3
    assert line.retry_count == 2
    assert line.usage == {"prompt_tokens": 42, "total_tokens": 42}


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (TimeoutError("provider timed out"), "provider_timeout"),
        (RuntimeError("429 rate limit exceeded"), "provider_rate_limited"),
        (RuntimeError("401 invalid API key"), "provider_auth_error"),
        (RuntimeError("requested model was not found"), "provider_model_not_found"),
        (ResponseParseError("invalid JSON"), "response_parse_failed"),
        (SchemaValidationError("invalid schema"), "schema_validation_failed"),
    ],
)
def test_provider_exception_codes_are_stable(exception, expected_code):
    assert _provider_error_code(exception) == expected_code

@pytest.mark.asyncio
async def test_validation_missing():
    job = JobState("job1", "doc1", 2)
    batch = [
        InputRecord(record_id="r1", text="a", source_hash="a"),
        InputRecord(record_id="r2", text="b", source_hash="b")
    ]
    provider = MockFaultyProvider("missing")
    await _process_batch(job, batch, provider, "style")
    # r1 succeeds immediately. r2 succeeds on the retry because it's now batch[0].
    assert provider.call_count == 2
    assert job.completed_records == 2
    assert job.failed_records == 0
    assert len(job.artifact_lines) == 2
    assert job.stats["completed_batches"] == 1
    assert job.stats["failed_batches"] == 0

@pytest.mark.asyncio
async def test_validation_duplicate():
    job = JobState("job1", "doc1", 2)
    batch = [InputRecord(record_id="r1", text="a", source_hash="a")]
    provider = MockFaultyProvider("duplicate")
    await _process_batch(job, batch, provider, "style")
    assert provider.call_count == 3
    assert job.completed_records == 0
    assert job.failed_records == 1
    assert len(job.artifact_lines) == 1
    assert job.artifact_lines[0].error_code == "duplicate_record_id"

@pytest.mark.asyncio
async def test_validation_malformed():
    job = JobState("job1", "doc1", 2)
    batch = [InputRecord(record_id="r1", text="a", source_hash="a")]
    provider = MockFaultyProvider("malformed")
    await _process_batch(job, batch, provider, "style")
    assert provider.call_count == 3
    assert job.failed_records == 1
    assert job.artifact_lines[0].status == "failed"

@pytest.mark.asyncio
async def test_validation_unknown():
    job = JobState("job1", "doc1", 2)
    batch = [InputRecord(record_id="r1", text="a", source_hash="a")]
    provider = MockFaultyProvider("unknown")
    await _process_batch(job, batch, provider, "style")
    assert provider.call_count == 3
    assert job.failed_records == 1


@pytest.mark.parametrize("fault_type", ["source_hash", "failed_status"])
@pytest.mark.asyncio
async def test_validation_rejects_integrity_and_status_failures(fault_type):
    job = JobState("job1", "doc1", 1)
    batch = [InputRecord(record_id="r1", text="a", source_hash="a")]
    provider = MockFaultyProvider(fault_type)

    await _process_batch(job, batch, provider, "style")

    assert provider.call_count == 3
    assert job.completed_records == 0
    assert job.failed_records == 1
    assert len(job.artifact_lines) == 1
    assert job.artifact_lines[0].status == "failed"


@pytest.mark.asyncio
async def test_scheduler_surfaces_unexpected_worker_failure(monkeypatch):
    class InvalidResultProvider:
        def __init__(self, model_name, template_version):
            pass

        async def summarize_batch(self, document_id, batch, summary_style):
            return [object()]

    monkeypatch.setattr(dispatcher_module, "MockProvider", InvalidResultProvider)
    request = SummaryRequest(
        document_id="doc1",
        records=[InputRecord(record_id="r1", text="source", source_hash="hash1")],
    )
    job = JobState("job1", request.document_id, len(request.records))

    await _run_job_background(job, request)

    assert job.status == "failed"
    assert job.completed_records == 0
    assert job.failed_records == 1
    assert job.stats["failed_batches"] == 1
    assert len(job.artifact_lines) == 1
    assert job.artifact_lines[0].record_id == "r1"
    assert job.artifact_lines[0].status == "failed"
    assert job.artifact_lines[0].error_code == "schema_validation_failed"
