# DeepReader Example Documents

These are small synthetic documents for testing DeepReader v0.1.

They are intentionally simple, technical, and inspection-friendly.

## Files

### simple_manual.txt

A fictional maintenance manual for a CP-200 cooling pump.

Useful for testing:

- text ingestion
- paragraph chunking
- stable record IDs
- keyword search
- technical retrieval

Example queries:

- What causes low flow?
- What does alarm A18 mean?
- How often should the filter be replaced?
- What does high motor current indicate?

### troubleshooting_log.txt

A fictional troubleshooting log containing maintenance incidents.

Useful for testing:

- retrieval across repeated terms
- ranking similar incidents
- matching symptoms to root causes
- inspecting source chunks

Example queries:

- Which incident involved bearing wear?
- What happened when flow was low but pressure was normal?
- Which fault was caused by heat exchanger fouling?
- What caused alarm A12 on Mill Line 3?

## Notes

These files are synthetic and safe to commit.

They do not require API keys, embeddings, LLM calls, or external services.
