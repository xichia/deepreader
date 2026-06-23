.PHONY: test backend-dev install-dev

install-dev:
	cd backend && python3 -m pip install -e ".[dev]"

test:
	cd backend && pytest

backend-dev:
	cd backend && uvicorn deepreader.api.main:app --reload --host 127.0.0.1 --port 8000
