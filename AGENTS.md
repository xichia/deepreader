# DeepReader Agent Instructions

DeepReader is a serious AI document intelligence and RAG workbench portfolio project.

Build it as a reliable engineering system, not a generic chatbot or beginner AI wrapper.

## Current milestone

The current milestone is v0.1 backend only.

Read:

- docs/V0.1_ACCEPTANCE.md
- examples/README.md
- examples/simple_manual.txt
- examples/troubleshooting_log.txt

## Do not overbuild

Do not implement v0.2 or v0.3 features yet.

Do not add:

- LLM calls
- embeddings
- hybrid retrieval
- question answering
- generated answers
- citation inspector
- frontend dashboard
- Docker polish

Focus only on v0.1 backend acceptance criteria and tests.

## Package defaults

Backend:

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x
- Pydantic
- pytest
- httpx
- ebooklib
- beautifulsoup4
- rank-bm25 or a simple internal BM25 implementation

Dev:

- Makefile
- .env.example
- SQLite local default

## Engineering priorities

Prioritise:

- deterministic stable IDs
- clean SQLite persistence
- inspectable BM25 search
- source text preservation
- small composable modules
- meaningful tests
- safe file handling
- clear README instructions

Avoid:

- opaque AI features
- hidden retrieval behaviour
- unnecessary abstractions
- mocked core backend behaviour
- committed secrets
