import asyncio
import pytest
from app.providers.mock import MockProvider
from app.records.schema import InputRecord, RecordMetadata

@pytest.mark.asyncio
async def test_mock_provider():
    provider = MockProvider(model_name="mock-model", template_version="v1")
    
    records = [
        InputRecord(record_id="r1", text="This is a test of the mock provider. It should return ten words max.", source_hash="h1", metadata=RecordMetadata()),
        InputRecord(record_id="r2", text="", source_hash="h2", metadata=RecordMetadata(status="empty_or_skipped"))
    ]
    
    results = await provider.summarize_batch("doc1", records, "one_sentence")
    
    assert len(results) == 2
    
    res1 = results[0]
    assert res1.record_id == "r1"
    assert res1.status == "completed"
    assert res1.summary_text.endswith("(mock summary).")
    
    res2 = results[1]
    assert res2.record_id == "r2"
    assert res2.status == "skipped"
    assert "Empty" in res2.summary_text


@pytest.mark.asyncio
async def test_mock_provider_configuration_validation_bypasses_gemini(monkeypatch):
    from app.config import settings
    from app.scheduler.dispatcher import validate_provider_configuration

    monkeypatch.setattr(settings, "summary_service_provider", "mock")
    # Even if enable provider calls is False, it should not fail configuration check
    monkeypatch.setattr(settings, "summary_service_enable_provider_calls", False)

    credentials = validate_provider_configuration()
    assert credentials == {}


@pytest.mark.asyncio
async def test_mock_provider_delay_and_cancellation(monkeypatch):
    from app.config import settings
    from app.scheduler.dispatcher import JobState, _run_job_background
    from app.records.schema import SummaryRequest

    monkeypatch.setattr(settings, "summary_service_provider", "mock")
    monkeypatch.setattr(settings, "summary_mock_provider_delay_ms", 100)

    request = SummaryRequest(
        document_id="doc1",
        records=[InputRecord(record_id="r1", text="some text", source_hash="h1")]
    )
    job = JobState("job1", "doc1", 1)

    # Start job in background, cancel it immediately
    task = asyncio.create_task(_run_job_background(job, request))
    await asyncio.sleep(0.01)  # yield to let loop start
    job.status = "cancelled"
    await task

    assert job.status == "cancelled"
    # Delay was respected and cancellation caught it
