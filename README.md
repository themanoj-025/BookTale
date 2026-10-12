<p align="center">
  <img src="https://img.shields.io/badge/Book--Tale-Library%20Management-blue?style=for-the-badge" alt="Book-Tale Logo" />
</p>

<h1 align="center">Book-Tale</h1>

<p align="center">
  <strong>Comprehensive library management system with catalog browsing, transactional lending, reading challenges, social feeds, and ML-powered book recommendations.</strong>
</p>

<p align="center">
  <a href="https://github.com/themanoj-025/BookTale/actions"><img src="https://img.shields.io/github/actions/workflow/status/themanoj-025/BookTale/ci.yml?style=flat-square&label=CI" alt="CI Status" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License MIT" /></a>
  <a href="https://github.com/themanoj-025/BookTale/stargazers"><img src="https://img.shields.io/github/stars/themanoj-025/BookTale?style=social" alt="GitHub Stars" /></a>
  <a href="https://github.com/themanoj-025/BookTale/issues"><img src="https://img.shields.io/github/issues/themanoj-025/BookTale?style=flat-square" alt="GitHub Issues" /></a>
  <a href="https://github.com/themanoj-025/BookTale/pulls"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square" alt="PRs Welcome" /></a>
</p>

---

## Overview

Book-Tale provides an end-to-end library operations platform supporting both an interactive web dashboard and a command-line interface. Built on Flask, SQLAlchemy, and Flask-SocketIO, it handles catalog discovery, reservations, concurrency-safe lending, overdue fines calculation, and community reading challenges.

The platform integrates a machine learning recommendation pipeline capable of scoring personalized book suggestions across a curated catalog of 11,000+ titles.

---

## Table of Contents

- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation & Quick Start](#installation--quick-start)
- [Configuration](#configuration)
- [Testing](#testing)
- [ML Recommendation Pipeline](#ml-recommendation-pipeline)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)
- [Support](#support)

---

## Key Features

- **Concurrency-Safe Lending Operations**: Book issue, return, and reservation flows run inside ACID database transactions to prevent overselling inventory under concurrent requests.
- **Automated Fine & Overdue Tracking**: Computes late-return fees based on configurable daily rates and manages borrowing quota restrictions.
- **ML Book Recommendations**: Hybrid content and collaborative filtering models surface personalized book recommendations based on user reading history and genre similarity.
- **Real-Time Community & Social Feeds**: Flask-SocketIO powers instant notifications for reservation availability, due date warnings, and peer reading challenges.
- **Dual Interface Modes**: Supports both a Jinja2 web interface (with esbuild asset bundling) and a terminal-based CLI interface.

---

## Architecture

```text
               ┌───────────────────────────────┐
               │    Clients: Web UI / CLI      │
               └───────────────┬───────────────┘
                               │
                               ▼
               ┌───────────────────────────────┐
               │    Flask Application Layer    │
               │  (REST Endpoints & SocketIO)  │
               └───────────────┬───────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│ Core Services │      │  SQLAlchemy   │      │ Recommendation│
│ (Lending,     │      │   ORM Layer   │      │  ML Pipeline  │
│ Fines, Feed)  │      │(SQLite/Postgre│      │(scikit-learn) │
└───────────────┘      └───────┬───────┘      └───────────────┘
                               ▼
                       Alembic Migrations
```

---

## Tech Stack

| Component | Technology |
| :--- | :--- |
| **Backend Framework** | Flask 3.x, Flask-SocketIO |
| **Database & ORM** | SQLAlchemy 2.x, SQLite (development), PostgreSQL (production) |
| **Schema Migrations** | Alembic |
| **Machine Learning** | scikit-learn, pandas, numpy |
| **Frontend** | Jinja2 templates, esbuild bundled JavaScript |
| **Quality & CI** | Pytest, Ruff, GitHub Actions CI |

---

## Project Structure

```text
Book-Tale/
├── app/
│   ├── api/                    # REST route controllers
│   ├── config/                 # Pydantic and settings modules
│   ├── core/                   # Lending, catalog, and fine business logic
│   ├── db/                     # SQLAlchemy models and database sessions
│   ├── routes/                 # Blueprint definitions and web handlers
│   ├── services/               # Recommendation engine and catalog seeders
│   ├── static/                 # Styles, scripts, and bundled web assets
│   └── templates/              # Jinja2 HTML templates
├── migrations/                 # Alembic database migration revisions
├── tests/                      # Pytest unit and concurrency test suite
├── docs/                       # Architecture decisions and API documentation
├── main.py                     # CLI application entry point
├── web_app.py                  # Web application entry point (Flask + SocketIO)
├── Dockerfile                  # Container build configuration
├── docker-compose.yml          # Containerized development orchestration
├── pyproject.toml              # Build backend and test settings
├── requirements.txt            # Python dependencies
└── README.md                   # Project documentation
```

---

## Prerequisites

- **Python**: `>= 3.10`
- **Node.js**: `>= 18.0` (required only if rebuilding frontend assets with esbuild)
- **Database**: SQLite (built-in default) or PostgreSQL 14+ for production

---

## Installation & Quick Start

### 1. Clone & Set Up Environment

```bash
# Clone repository
git clone https://github.com/themanoj-025/BookTale.git
cd BookTale

# Create virtual environment
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

### 2. Database Migration

```bash
# Apply database migrations to head
alembic upgrade head
```

### 3. Run the Application

**Run Web Interface**:
```bash
python web_app.py
```
*Open http://localhost:5000 in your browser.*

**Run CLI Interface**:
```bash
python main.py
```

---

## Configuration

Settings can be specified in `.env` (or via environment variables):

| Variable | Default | Required | Purpose |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | `sqlite:///booktale.db` | No | Connection string for database |
| `SECRET_KEY` | `dev-secret-key-change-me` | Yes (prod) | Session and cryptographic signing key |
| `FLASK_HOST` | `127.0.0.1` | No | Server listen address |
| `FLASK_PORT` | `5000` | No | Server listen port |
| `FLASK_DEBUG` | `False` | No | Enables hot reload and debug output |

---

## Testing

```bash
# Run unit and integration tests
pytest tests/ -v

# Run with test coverage
pytest --cov=app tests/
```

---

## ML Recommendation Pipeline

The recommendation subsystem is located in `app/services/recommendations/`:
- **Catalog Dataset**: Features a seed dataset of 11,000+ titles (`books.csv`).
- **Model Training**: `python -m app.services.recommendations.train` generates model artifacts for nearest-neighbor similarity and genre affinity scoring.
- **Inference**: Endpoints match reader history against candidate titles to return ranked recommendations.

---

## Roadmap

- [x] Full catalog management with availability tracking
- [x] Concurrency-safe issue/return/reserve operations
- [x] Overdue fine calculation and quota enforcement
- [x] Recommendation pipeline baseline models
- [x] Realtime activity notifications via WebSockets
- [ ] Automated email digests for overdue books <!-- TODO: Track via GitHub issue -->
- [ ] Integration with barcode/RFID scanner hardware <!-- TODO: Track via GitHub issue -->

---

## Contributing

Contributions are welcome! Please consult [CONTRIBUTING.md](CONTRIBUTING.md) for pull request guidelines and coding standards.

---

## Security

Please report vulnerabilities responsibly as outlined in [SECURITY.md](SECURITY.md).

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Support

- 🐛 **Issue Tracker**: [GitHub Issues](https://github.com/themanoj-025/BookTale/issues)
- 💬 **Discussions & Feedback**: [GitHub Pull Requests](https://github.com/themanoj-025/BookTale/pulls)
