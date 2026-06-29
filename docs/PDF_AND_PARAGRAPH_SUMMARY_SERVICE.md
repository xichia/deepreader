# PDF and Paragraph Summary Service

DeepReader v0.5 introduces PDF ingestion and an optional standalone mock summary service.

## PDF Ingestion

DeepReader parses PDFs using `pypdf`, extracting text page by page. 
Extracted text is split into ordered paragraph records, preserving deterministic stable IDs. 
If a page has no extractable text, an empty/skipped page marker is created to maintain order and structure.

## Paragraph Summary Service

The Paragraph Summary Service is an optional local service that handles asynchronous batch scheduling for remote-mode summaries.
It uses quota lanes to pace concurrent batches.

The service currently implements only a deterministic `mock` provider, so it needs no external API keys.

### QuotaLane Scheduler

- Validates record IDs and rejects duplicate IDs.
- Uses a rough text-length token estimate.
- Packs work items near the configured batch target; a single oversized record is dispatched alone for provider handling.
- Assigns ready batches to concurrent lanes.
- Applies a configurable per-lane cooldown. The mock provider uses a shortened time scale so local demos complete quickly.

## Configuration

To enable the mock remote workflow with Docker Compose:

```bash
DEEPREADER_SUMMARY_BACKEND=remote \
DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE=true \
docker compose up --build
```

The paragraph service uses the `mock` provider, while the backend defaults to its local summariser unless both opt-in variables are set. The backend summary endpoint waits while it polls the service, and service job state is held only in memory. External providers are not implemented.
