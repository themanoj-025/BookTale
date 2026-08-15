# Book-Tale — Copilot Instructions

## Code conventions
- Python with 4-space indentation, Flask routes
- HTML templates with Jinja2 in `templates/`
- JSON file-based storage (no database)
- Session-based auth with werkzeug password hashing

## Key commands
- Start server: `python web_app.py`
- Seed data: `python seed_data.py`
- Tests: `pytest tests/ -v`

## Key patterns
- Config via `config.py` with .env overrides and settings_override.json
- Routes split across `page_routes.py`, `social_routes.py`, `api.py`
- Three roles: member, librarian, admin
- Token-based email verification and password reset (1-hour expiry)
