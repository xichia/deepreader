from app.scheduler.token_packer import pack_batches
from app.records.schema import InputRecord

def test_token_packer():
    # Create dummy records
    records = [
        InputRecord(record_id=f"r{i}", text="word " * 10, source_hash="hash") 
        for i in range(10)
    ]
    # Each text is 50 chars -> ~12 tokens
    
    # If target is 25 tokens, we should get 2 records per batch
    batches = pack_batches(records, target_tokens=25, hard_max_tokens=50)
    
    assert len(batches) == 5
    for batch in batches:
        assert len(batch) == 2

def test_oversized_item_handling():
    records = [
        InputRecord(record_id="r1", text="word " * 10, source_hash="hash"), # 12 tokens
        InputRecord(record_id="r2", text="word " * 100, source_hash="hash"), # 125 tokens
        InputRecord(record_id="r3", text="word " * 10, source_hash="hash"), # 12 tokens
    ]
    
    # hard max is 100 tokens. r2 is oversized.
    batches = pack_batches(records, target_tokens=50, hard_max_tokens=100)
    
    # r1 should be in one batch, r2 alone, r3 alone
    assert len(batches) == 3
    assert len(batches[0]) == 1
    assert batches[0][0].record_id == "r1"
    assert len(batches[1]) == 1
    assert batches[1][0].record_id == "r2"
    assert len(batches[2]) == 1
    assert batches[2][0].record_id == "r3"


def test_record_count_cap_produces_expected_batches_for_large_document():
    records = [
        InputRecord(record_id=f"r{i}", text="tiny", source_hash=f"hash-{i}")
        for i in range(5051)
    ]

    batches = pack_batches(
        records,
        target_tokens=50_000,
        hard_max_tokens=75_000,
        max_records=10,
    )

    assert len(batches) == 506
    assert max(len(batch) for batch in batches) == 10
