# Gatekeeper developer commands. Everything runs in Docker; the host only
# needs Docker with the compose plugin.
#
# Run an isolated copy of the stack with COMPOSE_PROJECT_NAME, e.g.
#   COMPOSE_PROJECT_NAME=gk-review make test

COMPOSE ?= docker compose
RUN     := $(COMPOSE) run --rm
PYTEST_ARGS ?=
SEED_ARGS ?=
SERVICE ?=
BENCH_ARGS ?=

.DEFAULT_GOAL := help
.PHONY: help build setup up down clean migrate seed test lint logs shell psql bench

help:  ## list targets
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | expand -t 10

build:  ## build images
	$(COMPOSE) build

setup: build  ## build, start db, migrate, seed, start everything
	$(COMPOSE) up -d --wait db
	$(MAKE) migrate
	$(MAKE) seed
	$(COMPOSE) up -d

up:  ## start all services (API on 127.0.0.1:$GATE_PORT, default 8090)
	$(COMPOSE) up -d

down:  ## stop all services
	$(COMPOSE) down

clean:  ## stop everything and delete volumes (dev data is lost)
	$(COMPOSE) --profile tests down -v --remove-orphans

migrate:  ## alembic upgrade head on the dev database
	$(RUN) app alembic upgrade head

seed:  ## load deterministic demo data (SEED_ARGS="--scale 5")
	$(RUN) app python -m gatekeeper.seed $(SEED_ARGS)

test:  ## pytest on gatekeeper_test (PYTEST_ARGS="-k waiver")
	$(COMPOSE) up -d --wait db
	$(COMPOSE) --profile tests run --rm tests pytest $(PYTEST_ARGS)

lint:  ## ruff check
	$(RUN) --no-deps tests ruff check --no-cache .

logs:  ## follow logs (SERVICE=scheduler)
	$(COMPOSE) logs -f --tail=200 $(SERVICE)

shell:  ## bash in an app container
	$(RUN) app bash

psql:  ## psql on the dev database
	$(COMPOSE) exec db psql -U gatekeeper -d gatekeeper

bench:  ## time scorecard queries and CSV export on seeded data
	$(RUN) app python scripts/bench.py $(BENCH_ARGS)
