# Contributing to Book-Tale

Thank you for your interest in contributing to Book-Tale, the community-driven library management system!

## Getting Started

### Prerequisites
- Python 3.x
- pip

### Setup
1. Fork and clone the repository.
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   ```
5. Start the application:
   ```bash
   python web_app.py
   ```
   The app will be available at `http://localhost:5000`.

### Environment Variables
| Variable | Description |
| --- | --- |
| `SECRET_KEY` | Flask session secret key (required) |
| `SMTP_SERVER` | SMTP host for email notifications |
| `SMTP_PORT` | SMTP port (default: 587) |
| `SMTP_USERNAME` | SMTP login username |
| `SMTP_PASSWORD` | SMTP login password |
| `SMTP_FROM_EMAIL` | Sender email address |
| `DATA_DIR` | Directory for JSON data files (optional) |

## Code Style

- Follow PEP 8 conventions.
- Use 4-space indentation.
- Write docstrings for all public functions and classes.
- Use f-strings for string formatting (not `%` or `.format()`).
- Import ordering: standard library → third-party → local modules.

## Project Architecture

- **`web_app.py`** — Main Flask app setup, core auth routes, Socket.IO init
- **`services/`** — Business logic modules (library.py, social.py, recommender.py, etc.)
- **`routes/`** — Separate route files (social_routes.py, page_routes.py, new_features_routes.py)
- **`storage.py`** — JSON file persistence layer
- **`auth.py`** — Password hashing and token management
- **`realtime.py`** — Socket.IO event handlers

### Key Principles
- Keep business logic in service modules, not in route handlers.
- Route handlers should call service functions and render templates or return JSON.
- New API endpoints should be added to the appropriate route module.
- Use `@login_required` or `@admin_required` decorators for protected routes.

## Running Tests

```bash
pytest
pytest --cov  # with coverage report
```

Test files are located in the `tests/` directory. When adding new features, please add corresponding tests.

## Submitting Changes

1. Create a feature branch:
   ```bash
   git checkout -b feat/my-feature
   ```
2. Make focused, minimal changes.
3. Run the test suite to verify nothing is broken.
4. Commit with a descriptive message:
   - Format: `type(scope): description`
   - Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
   - Example: `feat(social): add post reporting functionality`
   - Example: `fix(library): correct fine calculation for leap years`
5. Push and open a Pull Request.

## Reporting Issues

Include in your report:
- Steps to reproduce the issue
- Expected vs actual behavior
- Browser/OS information
- Error messages from the console or logs

## Adding Features

### Adding a new API endpoint
1. Add the route to the appropriate route file (e.g., `social_routes.py` for social features).
2. Use `@login_required` for authenticated endpoints.
3. Return JSON responses with appropriate status codes.

### Adding a new page
1. Add the route in `page_routes.py` or `web_app.py`.
2. Use `render_page()` to render the base template.
3. Add JavaScript/CSS inline or in the static directory.

### Adding a new storage entity
1. Define the data structure.
2. Add load/save methods to `storage.py` if needed.
3. Reference the data directory via `Config.DATA_DIR`.

## Database

Book-Tale uses JSON file-based storage (no SQL database). When modifying data structures:
- Ensure backward compatibility with existing JSON files.
- Provide migration logic if the schema changes.
- Test with both empty and populated data directories.

## Code of Conduct

This project and everyone participating in it is governed by the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.
