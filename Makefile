NPM ?= pnpm

.PHONY: test backend-dev install-dev frontend-install frontend-dev frontend-build

install-dev:
	cd backend && python3 -m pip install -e ".[dev]"

test:
	cd backend && pytest

backend-dev:
	cd backend && uvicorn deepreader.api.main:app --reload --host 127.0.0.1 --port 8000

frontend-install:
	cd frontend && $(NPM) install

frontend-dev:
	cd frontend && $(NPM) run dev

frontend-build:
	cd frontend && $(NPM) run build
