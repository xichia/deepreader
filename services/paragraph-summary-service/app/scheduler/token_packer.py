from app.records.schema import InputRecord


def estimate_tokens(text: str) -> int:
    # Very rough estimate: 1 token per 4 chars
    return max(1, len(text) // 4)


def estimate_record_tokens(record: InputRecord) -> int:
    """Estimate text plus the JSON envelope sent for one record."""

    envelope = len(record.record_id) + len(record.source_hash) + 64
    return estimate_tokens(record.text) + estimate_tokens("x" * envelope)


def estimate_batch_input_tokens(
    records: list[InputRecord],
    *,
    wrapper_overhead_tokens: int = 0,
) -> int:
    return wrapper_overhead_tokens + sum(estimate_record_tokens(record) for record in records)


def pack_batches(
    records: list[InputRecord],
    target_tokens: int,
    hard_max_tokens: int,
    *,
    wrapper_overhead_tokens: int = 0,
    reserved_output_tokens: int = 0,
    include_record_overhead: bool = False,
    max_records: int | None = None,
) -> list[list[InputRecord]]:
    """Pack by token budget while enforcing an optional record-count ceiling."""
    if target_tokens < 1 or hard_max_tokens < 1:
        raise ValueError("Token limits must be positive")
    if max_records is not None and max_records < 1:
        raise ValueError("Maximum records per batch must be positive")

    usable_hard_max = hard_max_tokens - reserved_output_tokens
    if usable_hard_max <= wrapper_overhead_tokens:
        raise ValueError("Reserved output and prompt overhead leave no input token capacity")

    input_target = min(target_tokens, usable_hard_max)
    batches: list[list[InputRecord]] = []
    current_batch: list[InputRecord] = []
    current_tokens = wrapper_overhead_tokens

    for record in records:
        tokens = (
            estimate_record_tokens(record)
            if include_record_overhead
            else estimate_tokens(record.text)
        )

        # If single record is oversized, pack it alone (let provider fail it or handle it)
        if wrapper_overhead_tokens + tokens > usable_hard_max:
            if current_batch:
                batches.append(current_batch)
                current_batch = []
                current_tokens = wrapper_overhead_tokens
            batches.append([record])
            continue

        if current_batch and (
            current_tokens + tokens > input_target
            or (max_records is not None and len(current_batch) >= max_records)
        ):
            batches.append(current_batch)
            current_batch = []
            current_tokens = wrapper_overhead_tokens

        current_batch.append(record)
        current_tokens += tokens

    if current_batch:
        batches.append(current_batch)

    return batches
