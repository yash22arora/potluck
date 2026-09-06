# Shortcuts. Everything here is a one-liner you could type by hand — the point
# is that you stop having to remember which.

.DEFAULT_GOAL := help
.PHONY: help install env auth probe up down logs migrate revision test lint fmt shell

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Create the venv and install everything
	uv sync --all-groups

env: ## Create .env if missing and fill in any blank generated values
	@python3 tools/bootstrap_env.py

auth: ## Print the URL that connects a Swiggy account
	@echo "open this in a browser:  http://localhost:8000/auth/swiggy/start"

probe: ## Talk to Swiggy with no agent: make probe c="search milk"
	uv run python -m potluck.scripts.probe $(c)

up: env ## Build and start db + api + worker
	docker compose up --build -d
	@echo "api → http://localhost:8000/healthz"

down: ## Stop everything (keeps the database volume)
	docker compose down

logs: ## Tail all container logs
	docker compose logs -f

migrate: ## Apply migrations against the running database
	docker compose run --rm api migrate

revision: ## Autogenerate a migration: make revision m="add messages"
	uv run alembic revision --autogenerate -m "$(m)"

test: ## Run the test suite
	uv run pytest -q

lint: ## Check formatting and lint rules
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Fix what can be fixed automatically
	uv run ruff check --fix .
	uv run ruff format .

shell: ## A shell inside the api container
	docker compose run --rm api bash
