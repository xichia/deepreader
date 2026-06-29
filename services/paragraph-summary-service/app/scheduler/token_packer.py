from app.records.schema import InputRecord

def estimate_tokens(text: str) -> int:
    # Very rough estimate: 1 token per 4 chars
    return max(1, len(text) // 4)

def pack_batches(records: list[InputRecord], target_tokens: int, hard_max_tokens: int) -> list[list[InputRecord]]:
    """Packs records into batches near target_tokens, never exceeding hard_max_tokens."""
    batches = []
    current_batch = []
    current_tokens = 0

    for record in records:
        tokens = estimate_tokens(record.text)
        
        # If single record is oversized, pack it alone (let provider fail it or handle it)
        if tokens > hard_max_tokens:
            if current_batch:
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            batches.append([record])
            continue

        if current_tokens + tokens > target_tokens and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0

        current_batch.append(record)
        current_tokens += tokens

    if current_batch:
        batches.append(current_batch)

    return batches
