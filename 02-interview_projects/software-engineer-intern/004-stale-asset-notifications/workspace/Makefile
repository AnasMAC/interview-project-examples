# Atlas developer commands. Everything runs in Docker; the host only needs
# Docker with the compose plugin.
#
# Isolated copy of the stack:   COMPOSE_PROJECT_NAME=atlas-review make test
# Different host port:          ATLAS_PORT=8100 make up

COMPOSE ?= docker compose
RUN     := $(COMPOSE) run --rm
PYTEST_ARGS ?=
SEED_ARGS ?=
SERVICE ?=

.DEFAULT_GOAL := help
.PHONY: help build setup up down clean migrate seed test lint logs shell psql bench

help:
	@echo "Targets:"
	@echo "  setup    build, start db, migrate, seed, create the demo dashboard user, start all"
	@echo "  up       start all services (http://127.0.0.1:$${ATLAS_PORT:-8000})"
	@echo "  down     stop all services"
	@echo "  clean    stop everything and delete volumes (dev data is lost)"
	@echo "  migrate  apply Django migrations to the dev database"
	@echo "  seed     load deterministic demo data (SEED_ARGS=\"--reset --scale 8\")"
	@echo "  test     run pytest in the tests container (PYTEST_ARGS=...)"
	@echo "  lint     ruff check"
	@echo "  logs     follow logs (SERVICE=worker to filter)"
	@echo "  shell    Django shell in a web container"
	@echo "  psql     psql on the dev database"
	@echo "  bench    time the asset search and dashboard list on seeded data"

build:
	$(COMPOSE) build

setup: build
	$(COMPOSE) up -d --wait db
	$(MAKE) migrate
	$(MAKE) seed
	$(RUN) web python manage.py create_demo_user
	$(COMPOSE) up -d

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

clean:
	$(COMPOSE) --profile tests down -v --remove-orphans

migrate:
	$(RUN) web python manage.py migrate --noinput

seed:
	$(RUN) web python manage.py seed $(SEED_ARGS)

test:
	$(COMPOSE) up -d --wait db
	$(COMPOSE) --profile tests run --rm tests pytest $(PYTEST_ARGS)

lint:
	$(RUN) --no-deps tests ruff check --no-cache .

logs:
	$(COMPOSE) logs -f --tail=200 $(SERVICE)

shell:
	$(RUN) web python manage.py shell

psql:
	$(COMPOSE) exec db psql -U atlas -d atlas

bench:
	$(RUN) web python scripts/bench.py
