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
