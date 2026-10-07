# AGENTS.md — Book-Tale

> Canonical project instructions. Pointers like `CLAUDE.md` or
> `.github/copilot-instructions.md` should say "See AGENTS.md".

---

## Project overview

**Book-Tale** — a reading-challenge and book-recommendation platform
that gamifies reading for schools. Core components:

- **Flask API** (`app/api.py`) — REST endpoints for users, communities,
  reading progress, and recommendations.
- **Web UI** (`web_app.py`) — Streamlit-based dashboard and admin pages.
- **ML pipeline** (`app/services/recommendations/ml_pkg/`) — content-
  based and collaborative recommenders.
- **Scheduler** — background jobs (weekly activity triggers, radar
  balance updates).

Stack: Python 3.11+ · Flask · SQLAlchemy · scikit-learn · Streamlit.

---

## Exact commands

```bash
# Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Env
cp .env.example .env   # set SECRET_KEY, DB_URL

# Lint / typecheck / test
make lint
pre-commit run --all-files
python -m mypy . --ignore-missing-imports
python -m pytest tests/ -v --cov=. --cov-fail-under=80

# Run
python main.py
```

---

## Folder map

| Path | Purpose |
|------|---------|
| `app/` | Flask API, ML package, services |
| `web_app.py` | Streamlit dashboard (entry) |
| `main.py` | CLI/entry point |
| `tests/` | pytest suite (route, model, service, integration) |
| `.github/workflows/` | CI (ruff, mypy, pytest, gitleaks, trivy) |

## Do / don't

- **Do** treat `app/services/` as the single business-logic layer.
- **Do not** commit `secrets/` or `*.pem` — the `.gitignore` enforces it.
- **Do not** add new ML models without updating `ml_pkg/__init__.py`.
- **Do** keep the recommendation data in `data/generated/` (gitignored).

## Security rules

- The `SECRET_KEY` is loaded from environment variables; never commit it.
- Rate-limit the API endpoints per IP.
- The gitleaks CI gate is exit-code `1` on hit.

## AI-assistance convention

Commits authored by AI must carry the trailer:

```text
AI-Assisted: yes | no | partial
```

See `.gitmessage` for the template. Do not rewrite historic commits
retroactively.
