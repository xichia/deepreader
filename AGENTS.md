# DeepReader Agent Instructions

DeepReader is a serious AI document intelligence and RAG workbench portfolio project.

Build it as a reliable engineering system, not a generic chatbot or beginner AI wrapper.

## Current milestone

The v0.1 backend/frontend slice is complete.

The v0.2 processing pipeline is implemented in the working tree: uploads, jobs, job steps, deterministic local summaries, checkpointing, summary-aware BM25 search, and frontend summary/job panels.

The current milestone is v0.3 retrieval, citations, and QA workbench.

Read:

- README.md
- docs/V0.1_ACCEPTANCE.md
- examples/README.md
- backend/src/deepreader
- frontend/src
- backend/tests

## Allowed in this milestone

Add v0.3 retrieval and QA features:

- retrieval result abstractions
- BM25 over source text and summaries
- deterministic local vector-style retrieval over source text and summaries
- simple score normalisation and fusion
- evidence packets
- stable-ID citation mapping
- deterministic local extractive QA
- persisted answers and answer citations
- frontend QA/citation inspection workbench

The project must continue to work locally with no API keys.

## Do not overbuild

Do not add:

- real external LLM providers
- OpenAI, Gemini, Anthropic, or paid API calls
- required API keys
- production async worker infrastructure
- authentication
- multi-user permissions
- cloud deployment
- Docker polish

Do not mock core backend behaviour. The dashboard should consume the real FastAPI backend.

## Package defaults

Frontend:

- Vite
- React
- TypeScript
- plain CSS or simple CSS modules
- no heavy UI framework unless already justified

Backend:

- Keep existing FastAPI backend functionality working.
- Keep v0.1 ingestion/search and v0.2 summary/job behaviour passing.
- Use deterministic local retrieval and answer generation by default.
- Provider interfaces may exist for future LLM support, but real external calls must not be required.

## Engineering priorities

Prioritise:

- deterministic stable IDs and hashes
- clean SQLite persistence
- inspectable retrieval methods and component scores
- evidence packets that map back to original source records
- citations that never cite summaries alone
- source text preservation
- meaningful tests
- simple professional UI
- no fake AI claims
- no hidden retrieval behaviour

Avoid:

- unnecessary abstractions
- advanced styling before behaviour works
- mocked core backend behaviour
- committed secrets or generated artifacts
