# DeepReader Agent Instructions

DeepReader is a serious AI document intelligence and RAG workbench portfolio project.

Build it as a reliable engineering system, not a generic chatbot or beginner AI wrapper.

## Current milestone

The v0.1 backend is implemented and tested.

The current milestone is a minimal v0.1 frontend dashboard that consumes the real backend API.

Read:

- docs/V0.1_ACCEPTANCE.md
- examples/README.md
- README.md
- backend/src/deepreader/api/main.py
- backend/src/deepreader/api/routes_documents.py
- backend/src/deepreader/api/routes_search.py

## Allowed in this milestone

Add a minimal React/Vite/TypeScript frontend.

The frontend should consume the real FastAPI backend API.

It should support:

- listing documents
- viewing document records
- running search queries
- inspecting ranked chunks
- showing stable IDs, scores, source text, summaries, and metadata

## Do not overbuild

Do not implement v0.2 or v0.3 features yet.

Do not add:

- LLM calls
- embeddings
- hybrid retrieval
- question answering
- generated answers
- citation inspector
- Docker polish

Do not mock the backend API unless only used as a fallback error state. The dashboard should consume the real backend.

## Package defaults

Frontend:

- Vite
- React
- TypeScript
- plain CSS or simple CSS modules
- no heavy UI framework unless already justified

Backend:

- Keep the current FastAPI backend working.
- Do not rewrite the backend unless required for frontend integration.
- Small CORS changes are acceptable if needed for local frontend development.

## Engineering priorities

Prioritise:

- clean API integration
- readable components
- clear loading and error states
- inspectable search results
- simple professional UI
- no fake AI features
- no hidden retrieval behaviour

Avoid:

- unnecessary abstractions
- advanced styling before behaviour works
- mocked core backend behaviour
- committed secrets
