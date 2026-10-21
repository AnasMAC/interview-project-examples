# Bellpost developer tasks. Run `make` (or `make help`) for the list.
#
# .env is loaded when present, so the ports below follow your local settings.

SHELL := bash
.DEFAULT_GOAL := help

PYTHON ?= python3.12
VENV := .venv
BIN := $(VENV)/bin
PY := $(BIN)/python
PIP := $(BIN)/pip

SEED_ARGS ?=
PYTEST_ARGS ?=

-include .env
export

.PHONY: help setup up down clean migrate seed serve worker test lint smoke mockhook mock-metadata psql logs

help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup:  ## Create .venv, install pinned requirements, start db, migrate, seed
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' \
		|| { echo "error: python3.12 is required (found $$($(PYTHON) -V 2>&1))"; exit 1; }
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -r requirements.txt -r requirements-dev.txt
	docker compose up -d db
	@i=0; until docker compose exec -T db pg_isready -U bellpost -d bellpost >/dev/null 2>&1; do \
		i=$$((i + 1)); \
		if [ $$i -ge 60 ]; then echo "error: postgres did not become ready"; exit 1; fi; \
		sleep 1; \
	done; echo "postgres is ready"
	$(BIN)/alembic upgrade head
	$(PY) seed/generate.py --seed 1
	@echo "setup complete: make serve  (http://127.0.0.1:$${BELLPOST_WEB_PORT:-8080}/admin)"

up:  ## Start the database container
	docker compose up -d db

down:  ## Stop the database container (data is kept)
	docker compose down

clean:  ## Stop the database, drop its volume and remove generated files
	docker compose down -v
	rm -rf var

migrate:  ## Apply database migrations (alembic upgrade head)
	$(BIN)/alembic upgrade head

seed:  ## Load demo data (SEED_ARGS="--reset" to reload over existing tenants)
	$(PY) seed/generate.py --seed 1 $(SEED_ARGS)

serve:  ## Run the web app and admin panel on BELLPOST_WEB_PORT (default 8080)
	$(PY) -m flask --app app:create_app run --host 127.0.0.1 --port $${BELLPOST_WEB_PORT:-8080}

worker:  ## Process the spool once with the email-ingest worker
	$(PY) -m app.ingest --spool $${BELLPOST_SPOOL_DIR:-spool/incoming} --once

mockhook:  ## Run the local webhook receiver (MOCKHOOK_STRICT=1 to verify signatures)
	$(PY) tools/mockhook/server.py --port $${MOCKHOOK_PORT:-8900} --log $${MOCKHOOK_LOG:-var/mockhook/deliveries.jsonl}

mock-metadata:  ## Run the local instance-metadata stand-in used by the security tests
	$(PY) tools/mock_metadata/server.py --port $${MOCK_METADATA_PORT:-8901}

test:  ## Run the test suite (needs the db container; the fixtures create bellpost_test)
	$(BIN)/pytest -q $(PYTEST_ARGS)

lint:  ## Check the source with ruff
	$(BIN)/ruff check --no-cache app migrations seed tests tools

smoke:  ## Start the app briefly and assert GET /healthz answers 200
	@mkdir -p var
	@bash -c 'set -euo pipefail; port=$${BELLPOST_WEB_PORT:-8080}; \
		$(PY) -m flask --app app:create_app run --host 127.0.0.1 --port $$port --no-reload >var/smoke.log 2>&1 & \
		pid=$$!; trap "kill $$pid 2>/dev/null || true" EXIT; \
		for i in $$(seq 1 40); do \
			if curl -fsS "http://127.0.0.1:$$port/healthz" >/dev/null 2>&1; then \
				echo "GET /healthz -> 200"; exit 0; \
			fi; \
			sleep 0.25; \
		done; \
		echo "error: /healthz did not answer on port $$port"; \
		sed -n "1,40p" var/smoke.log; exit 1'

psql:  ## Open psql on the development database
	docker compose exec db psql -U bellpost -d bellpost

logs:  ## Follow the database container log
	docker compose logs -f db
