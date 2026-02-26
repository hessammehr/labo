.PHONY: help dev run serve migrate migrate-new test lint fmt clean

BACKEND_DIR := backend

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev: ## Run backend dev server with reload
	cd $(BACKEND_DIR) && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

run: ## Run backend server (production)
	cd $(BACKEND_DIR) && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

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

test: ## Run tests
	cd $(BACKEND_DIR) && uv run --extra dev pytest -v

lint: ## Lint code
	cd $(BACKEND_DIR) && uvx ruff check .

fmt: ## Format code
	cd $(BACKEND_DIR) && uvx ruff format .

clean: ## Remove generated files
	rm -rf $(BACKEND_DIR)/.venv $(BACKEND_DIR)/labo.db $(BACKEND_DIR)/storage
