.PHONY: up down migrate test lint api web check

up:        ## Postgres on 127.0.0.1:55433 (db ilmhona)
	docker compose up -d --wait

down:
	docker compose down

migrate:   ## apply migrations to the dev database
	cd apps/api && uv run alembic upgrade head

test:      ## API tests (need `make up`; TEST_DB_NAME picks the throwaway DB) and web unit tests
	cd apps/api && uv run pytest -q
	cd apps/web && pnpm test

lint:
	cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy app
	cd apps/web && pnpm lint && pnpm typecheck

api:       ## API on :8200
	cd apps/api && uv run uvicorn app.main:app --reload --port 8200

web:       ## web on :3200 (proxies /api to :8200)
	cd apps/web && pnpm dev

check: lint test
