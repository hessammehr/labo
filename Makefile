.PHONY: help dev dev-backend dev-frontend run serve serve-bg serve-off migrate migrate-new test lint fmt build-frontend clean

BACKEND_DIR := backend
FRONTEND_DIR := frontend
UVICORN := uv run python -m uvicorn

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev: ## Run backend + frontend dev servers
	@set -e; \
	trap 'kill 0' INT TERM EXIT; \
	$(MAKE) dev-backend & \
	$(MAKE) dev-frontend & \
	wait

dev-backend: ## Run backend dev server with reload
	cd $(BACKEND_DIR) && $(UVICORN) app.main:app --reload --host 127.0.0.1 --port 8000

dev-frontend: ## Run frontend dev server
	cd $(FRONTEND_DIR) && bun dev --host 127.0.0.1 --port 5173

run: ## Run backend server (production)
	cd $(BACKEND_DIR) && $(UVICORN) app.main:app --host 127.0.0.1 --port 8000

build-frontend: ## Build frontend static bundle
	cd $(FRONTEND_DIR) && bun run build

serve: ## Expose local server over HTTPS via Tailscale
	tailscale serve https+insecure://127.0.0.1:8000

serve-bg: ## Expose local server over HTTPS via Tailscale (background)
	tailscale serve --bg https+insecure://127.0.0.1:8000

serve-off: ## Stop Tailscale background serve
	tailscale serve --bg off

migrate: ## Run database migrations
	cd $(BACKEND_DIR) && uv run alembic upgrade head

migrate-new: ## Create a new migration (usage: make migrate-new msg="description")
	cd $(BACKEND_DIR) && uv run alembic revision --autogenerate -m "$(msg)"

test: ## Run backend tests
	cd $(BACKEND_DIR) && uv run --extra dev pytest -v

lint: ## Lint backend code
	cd $(BACKEND_DIR) && uvx ruff check .

fmt: ## Format backend code
	cd $(BACKEND_DIR) && uvx ruff format .

clean: ## Remove generated files
	rm -rf $(BACKEND_DIR)/.venv $(BACKEND_DIR)/labo.db $(BACKEND_DIR)/storage $(FRONTEND_DIR)/dist $(FRONTEND_DIR)/node_modules
