.PHONY: help up up-fg down clean logs logs-api logs-worker status restart build shell psql migrate migrate-new

help:  ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: .env  ## start everything in the background (builds if needed, auto-runs migrations), then prints health
	docker compose up --build -d
	@echo "waiting for api to become healthy (up to 60s)..."
	@for i in $$(seq 1 60); do \
		if curl -sf localhost:8000/health > /dev/null 2>&1; then break; fi; \
		sleep 1; \
	done
	@echo ""
	@echo "health:"
	@curl -s localhost:8000/health | python3 -m json.tool || echo "service did not come up — try: make logs"
	@echo ""
	@echo "temporal ui: http://localhost:8080"

up-fg: .env  ## same as up but foreground (follows logs; Ctrl+C to stop)
	docker compose up --build

.env:
	@echo "no .env found — creating one from .env.example"
	cp .env.example .env

down:  ## stop services, keep volumes
	docker compose down

clean:  ## stop services and wipe volumes (fresh DB next up)
	docker compose down -v

logs:  ## follow logs from all services
	docker compose logs -f

logs-api:  ## follow api logs only
	docker compose logs -f api

logs-worker:  ## follow worker logs only
	docker compose logs -f worker

status:  ## check /health
	@curl -s localhost:8000/health | python3 -m json.tool

restart:  ## restart api and worker (preserve db + temporal)
	docker compose restart api worker

build:  ## rebuild images without starting
	docker compose build

shell:  ## shell into the api container
	docker compose exec api sh

psql:  ## open a psql shell on the app db
	docker compose exec postgres psql -U loura -d loura

migrate:  ## manually re-run migrations (normally automatic on startup)
	docker compose exec api alembic upgrade head

migrate-new:  ## create a new migration: make migrate-new m="add index on created_at"
	docker compose exec api alembic revision -m "$(m)"
