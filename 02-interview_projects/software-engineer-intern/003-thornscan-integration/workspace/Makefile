# Ledger developer commands (GNU make). Only Python 3.11+ is required; there
# are no third-party dependencies. Windows: run the python3 commands directly
# (see README.md).

PYTHON ?= python3
TESTS ?= tests
SCALE ?= 1
LEDGER_PORT ?= 8765
export LEDGER_PORT

.DEFAULT_GOAL := help
.PHONY: help setup migrate seed demo test run-api bench clean

help:
	@echo "Targets:"
	@echo "  setup    create var/, migrate var/ledger.db, load the demo seed"
	@echo "  migrate  apply pending SQL migrations"
	@echo "  seed     reload the deterministic demo data (SCALE=$(SCALE))"
	@echo "  demo     ingest the sample scanner outputs in samples/"
	@echo "  test     run the unit tests (TESTS=tests/dedupe to narrow)"
	@echo "  run-api  serve the JSON API on 127.0.0.1:$(LEDGER_PORT)"
	@echo "  bench    time sample ingest, weekly report and CSV export on a scale-17 temp DB"
	@echo "  clean    delete var/ and Python caches"

setup: migrate seed

migrate:
	$(PYTHON) -m ledger migrate

seed:
	$(PYTHON) -m ledger seed --reset --scale $(SCALE)

demo:
	$(PYTHON) -m ledger ingest --manifest samples/manifest.json

test:
	$(PYTHON) -m unittest discover -s $(TESTS) -t .

run-api:
	$(PYTHON) -m ledger.api

bench:
	$(PYTHON) scripts/bench_ingest.py

clean:
	rm -rf var .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
