# Run targets from the `backend/` directory (same folder as this Makefile).

.PHONY: dev install

install:
	pip install -e .

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
