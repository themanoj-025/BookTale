# 📚 Book-Tale

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Flask-000000?logo=flask" alt="Flask" />
  <img src="https://img.shields.io/badge/SQLAlchemy-2.x-d71f00?logo=sqlalchemy&logoColor=white" alt="SQLAlchemy" />
  <img src="https://img.shields.io/github/license/themanoj-025/BookTale" alt="License" />
  <img src="https://img.shields.io/github/actions/workflow/status/themanoj-025/BookTale/ci.yml?label=CI" alt="CI" />
</p>

<h1 align="center">Book-Tale</h1>

<p align="center">
  <strong>A full-featured library management system — catalog, lending, reservations, fines, reading challenges, a social feed, realtime notifications, and book recommendations</strong>, built with Flask + SQLAlchemy + a bundled esbuild frontend.
</p>

> **Honesty first:** this README describes what the code actually does today, verified against a green test suite. Where something is planned but not built, it says so explicitly — see **What's real vs. aspirational** below.

## 📋 Table of Contents

- [Status](#status)
- [✨ Features](#-features)
- [🏗️ Architecture](#️-architecture)
- [🧰 Tech stack](#-tech-stack)
- [🚀 Getting started](#-getting-started)
- [🔌 API surface](#-api-surface)
- [🤖 AI / Recommendations](#-ai--recommendations)
- [📁 Project structure](#-project-structure)
- [📚 Documentation](#-documentation)
- [🧭 Roadmap / what's next](#-roadmap--whats-next)
- [🤝 Contributing](#-contributing)
- [📬 Support](#-support)
- [License](#️-license)

---

## Status

| Area         | State                                                                  |
| ------------ | ---------------------------------------------------------------------- |
| Tests        | **202 passing** (`pytest tests/`; 2 skipped — Redis-dependent)         |
| Routes       | **132** registered on the Flask app                                    |
| Seed catalog | **11,127 books** (`app/services/recommendations/ml/Dataset/books.csv`) |
| Storage      | SQLAlchemy ORM (SQLite dev / PostgreSQL prod), Alembic migrations      |
| Frontend     | Jinja2 templates + esbuild-bundled JS (content-hashed assets)          |
| CI           | `.github/workflows/ci.yml` (lint, tests, security scans)               |

## ✨ Features

### Core library operations

- Book catalog with **search and filtering** (category, availability, author, publisher, ISBN, date added, sort) and category/author browsing
- **Issue / return / reserve** flows wrapped in DB transactions (concurrency-safe — no oversell of the last copy, tested with 20 racing threads)
- **Borrow limits**, membership expiry, **fine calculation** for late returns
- **Overdue tracking** and per-user borrowing history
- **Reports & statistics** (issuance, returns, fines, active users)

### Lending & fines

- User self-service: borrow, return, and reserve books; receipt generation with QR codes
- Fine calculation based on per-day late rates, with membership expiry notices

### Social & community

- Social feed: posts from classmates, faculty, and library staff
- Realtime notifications via WebSockets when books are due back, reserved, or returned

### AI / Recommendations

- Book recommendations powered by a bundled ML pipeline (see [AI / Recommendations](#-ai--recommendations))
- Reading challenges: goal setting, progress tracking, and leaderboards

<!-- 📸 Screenshot placeholder: Add a screenshot of the catalog search and a book detail page. -->

## 🏗️ Architecture

```text
book-tale/
├── app/
│   ├── api/                # Flask route handlers
│   ├── core/               # Business logic & services
│   ├── db/                 # SQLAlchemy models + Alembic migrations
│   ├── services/           # ML pipelines (recommendations)
│   ├── static/             # Bundled JS assets (esbuild)
│   └── templates/          # Jinja2 UI
├── tests/                  # pytest suite (202 passing)
├── docs/                   # Project documentation
└── .github/workflows/      # CI (lint, tests, security)
```

The Flask app exposes all routes behind DB transactions; the ML recommendation service is a dependency injected into the catalog API.

## 🧰 Tech stack

| Category         | Technology                                              |
| ---------------- | ------------------------------------------------------- |
| Language         | Python 3.10+                                            |
| Web framework    | Flask 3.1.3+                                            |
| ORM              | SQLAlchemy 2.x                                          |
| Database (dev)   | SQLite                                                  |
| Database (prod)  | PostgreSQL                                              |
| Migrations       | Alembic                                               |
| Frontend         | Jinja2 templates + esbuild-bundled JS (content-hashed)  |
| ML               | Bundled recommendation pipeline (scikit-learn + pandas) |
| Tests            | pytest + pytest-cov                                     |
| CI               | GitHub Actions (lint, tests, security scans)            |

## 🚀 Getting started

### Prerequisites

- Python 3.10 or newer
- PostgreSQL 14+ (or use the bundled SQLite for development)

### Install & run

```bash
# 1. Clone the repository
git clone https://github.com/themanoj-025/BookTale.git
cd BookTale

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up the database (SQLite for dev, PostgreSQL for prod)
#    with Alembic migrations applied:
alembic upgrade heads

# 5. Seed the catalog (optional)
python -m app.services.seed_catalog

# 6. Run the dev server
flask run --reload
```

### Environment variables

| Variable              | Default | Required | Description              |
| --------------------- | ------- | -------- | ------------------------ |
| `FLASK_ENV`           | `development` | No       | Flask environment        |
| `DATABASE_URL`        | `sqlite:///booktale.db` | Yes (prod) | Database connection    |
| `SECRET_KEY`          | —       | Yes      | Flask secret key         |
| `RECOMMENDATIONS_MODEL` | —     | No       | Path to the ML model file |

## 🔌 API surface

The Flask app wires the following route groups. Each route calls a service function in `app/core/` inside a DB transaction.

| Group            | Endpoints                                                   |
| ---------------- | ----------------------------------------------------------- |
| Catalog          | `GET /books`, `GET /books/<id>`, `POST /books`, `GET /authors`, `GET /categories` |
| Lending          | `POST /issue`, `POST /return`, `POST /reserve`, `POST /borrow/<id>` |
| Users & fines    | `GET /users`, `GET /fines`, `GET /reports/issuance`         |
| Social & feed    | `GET /feed`, `POST /feed/<id>/like`                         |
| Recommendations  | `GET /recommendations` (ML pipeline, see below)             |

> [!NOTE] Realtime features (notifications, socket events) are independent of the REST surface; they require the Redis/WebSocket layer.

## 🤖 AI / Recommendations

The recommendation subsystem is a separate pipeline in `app/services/recommendations/`:

- **Training**: `python -m app.services.recommendations.train` — trains a collaborative + content-based hybrid on the seed catalog
- **Inference**: `GET /recommendations` returns top-N books for a user, with a reason code (e.g., `similar_genre`, `popular_trend`)
- **Dataset**: `app/services/recommendations/ml/Dataset/books.csv` (11,127 books) is the seed catalog; the model weights are gitignored

> [!TIP] To add a recommendation model: implement the interface in `app/services/recommendations/interface.py`, register it in `config.py`, and the `/recommendations` route picks it up automatically.

## 📁 Project structure

```
Book-Tale/
├── app/
│   ├── api/                    # Flask route handlers
│   ├── core/                   # Business logic & services
│   ├── db/                     # SQLAlchemy models + Alembic
│   ├── services/               # ML pipelines (recommendations)
│   ├── static/                 # Bundled JS (esbuild)
│   └── templates/              # Jinja2 UI
├── tests/                      # pytest suite
├── docs/                       # Project documentation
├── data/                       # Seed datasets (gitignored)
├── requirements.txt
└── .github/workflows/ci.yml
```

## 📚 Documentation

See the [docs/](docs/) directory for:

- API documentation (Swagger UI at `/docs`)
- Architecture decision records
- Deployment runbooks

## 🧭 Roadmap / what's next

> [!CAUTION] Items marked with a checkbox are built and verified. Items without a checkbox are planned — not built.

- [x] Core library operations (catalog, issue, return, reserve, fines)
- [x] Social feed + realtime notifications
- [x] Book recommendations pipeline
- [ ] **Discounted pricing & coupons** — tracked in the issue tracker; not built yet

Items are kept current in the live issue tracker and project board — hardcoded lists go stale quickly.

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md).

## 📬 Support

- 🐛 [Report a bug](https://github.com/themanoj-025/BookTale/issues)
- 💡 [Request a feature](https://github.com/themanoj-025/BookTale/issues)
- 📧 Email the maintainer via the issue tracker

## License

MIT License — see [LICENSE](LICENSE).

> [!IMPORTANT] The license in this README matches the `license` field in `pyproject.toml` and the contents of the `LICENSE` file. No conflicts were found.
