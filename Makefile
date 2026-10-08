.PHONY: up down deps migrate seed superuser purge-keys logs test lint arch schema load load-up load-stress hot-slot locust check

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

K6 := docker run --rm --user 0 --network scheduling_default \
	-v "$(CURDIR)/tests/load:/load:ro" -v "$(CURDIR)/docs/load:/out" grafana/k6:0.54.0 run

load-up:  ## Stack with throttles lifted + load-test data (50 dealerships, 5000 customers)
	$(COMPOSE) -f docker-compose.yml -f docker-compose.load.yml up -d --build --wait
	$(COMPOSE) exec web python manage.py migrate --noinput
	$(COMPOSE) exec web python manage.py seed_load

load:  ## Sustained design target: 10 booking + 100 availability TPS for 10 minutes (k6)
	$(K6) -e PROFILE=sustained -e DURATION=$${DURATION:-10m} \
		--summary-export /out/sustained.json /load/k6.js | tee docs/load/sustained.txt

load-stress:  ## Stress burst: 50 booking + 500 availability TPS for 60 seconds (k6)
	$(K6) -e PROFILE=stress -e DURATION=$${DURATION:-60s} \
		--summary-export /out/stress.json /load/k6.js | tee docs/load/stress.txt

locust:  ## Interactive Locust UI on http://localhost:8089
	$(RUN) locust -f tests/load/locustfile.py --host http://localhost:8000

hot-slot:  ## 50 simultaneous requests for one dealership/slot
	$(RUN) python tests/load/hot_slot.py --requests 50

check: lint arch test
