---
inclusion: always
---

# Project Conventions — NotebookLM Dashboard

## Python Environment

- The project uses a local virtualenv at `.venv/`
- Always use `.venv/bin/python` or `.venv/bin/<tool>` to run Python commands
- `python` is NOT available on this macOS system — use `python3` or `.venv/bin/python`
- To run pytest: `.venv/bin/pytest tests/ -x -q`
- To run uvicorn: `.venv/bin/uvicorn app.main:app --reload`
- The `--timeout` pytest flag requires `pytest-timeout` which is NOT installed. Do not use it.

## Dependency Management

- Dependencies are listed in `requirements.txt` with pinned versions
- After adding a new dependency to `requirements.txt`, always install it: `.venv/bin/pip install -r requirements.txt`
- Never assume a package in requirements.txt is already installed in the venv

## Running the Dev Server

- Use `controlBashProcess` with `.venv/bin/uvicorn app.main:app --reload` (no host/port flags needed, defaults to 127.0.0.1:8000)
- The server auto-reloads on file changes
- Check process output after starting to confirm no import errors

## Testing

- Test runner: `.venv/bin/pytest`
- Property tests use Hypothesis
- Async tests use pytest-asyncio with `asyncio_mode = "auto"` (configured in pyproject.toml)
- Test files are in `tests/unit/` and `tests/property/`

## Project Structure

- FastAPI app entry point: `app/main.py` → `app = create_app()`
- Routes: `app/routes/` with routers registered in `app/routes/__init__.py`
- Templates: `app/templates/` (Jinja2)
- Static files: `static/css/` and `static/js/`
- Database: `data/dashboard.db` (SQLite via aiosqlite)
- Specs: `.kiro/specs/`
