# Agent Instructions

## File exploration

- Use `rg` (ripgrep) for searching — it respects `.gitignore` automatically.
- When using `find`, always exclude build artifacts and dependencies: `node_modules`, `.venv`, `__pycache__`, `dist`, `build`, `storage`, `.pytest_cache`, `.ruff_cache`, `*.egg-info`.
  - Example: `find . -not -path '*/node_modules/*' -not -path '*/.venv/*' -not -path '*/__pycache__/*'`
  - Or use `fd` if available (respects `.gitignore` by default).

## Python

- Always use `uv` for Python tasks: `uv run`, `uvx`, `uv add`, `uv pip`, etc.
- Do not use bare `python`, `pip`, or `pytest` — use `uv run python`, `uv run pytest`, etc.
