.PHONY: up down deps migrate seed superuser purge-keys logs test lint arch schema load check

COMPOSE := docker compose
RUN := uv run

up:  ## Build and start the full stack
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down

deps:  ## Start only the backing services (Postgres, Redis) for host-side tests
	$(COMPOSE) up -d --wait db redis

migrate:
	$(COMPOSE) exec web python manage.py migrate

seed:
	$(COMPOSE) exec web python manage.py seed_demo

superuser:  ## Create a Django admin login for managing reference data
	$(COMPOSE) exec web python manage.py createsuperuser

purge-keys:  ## Delete expired idempotency keys (run from cron in production)
	$(COMPOSE) exec web python manage.py purge_idempotency_keys

logs:
	$(COMPOSE) logs -f web

test: deps
	$(RUN) pytest --cov --cov-report=term-missing

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy .

arch:
	$(RUN) lint-imports

schema:
	$(RUN) python manage.py spectacular --file docs/openapi.yaml --validate

load:
	$(RUN) locust -f tests/load/locustfile.py --host http://localhost:8000

check: lint arch test
