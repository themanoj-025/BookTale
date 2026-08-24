# ADR 0009 — Multi-Stage Dockerfile + Compose Stack

- **Status:** Accepted (2026-08-01)
- **Deciders:** Project owner, acting senior staff engineer
- **Related code:** `Dockerfile`, `docker-compose.yml`, `package.json`,
  `scripts/build_frontend.mjs`
- **Related ADRs:** ADR 0008 (the image `HEALTHCHECK` probes `/healthz`),
  ADR 0007 (compose carries CSRF/rate-limit env flags), ADR 0004 (compose
  defaults to the DB storage backend)

---

## Context

The project had no container story:

1. Dev ran the Flask dev server against SQLite/JSON; there was no pinned,
   reproducible runtime for production.
2. The frontend build (esbuild → `static/dist/manifest.json`) was a manual,
   developer-machine step — nothing produced it inside a CI/registry pipeline.
3. No health probes, no non-root user, no declared runtime deps — the app
   wasn't a buildable, deployable artifact.

## Decision

**Multi-stage `Dockerfile`** (base `python:3.12-slim`):

- **Builder stage:** installs the Python virtualenv (`/opt/venv`) from
  `requirements.txt`, installs Node 20, runs `scripts/build_frontend.mjs` to
  produce the content-hashed frontend bundle.
- **Runtime stage:** copies only the venv + built `static/dist/` + app code,
  creates a non-root `booktale` user, sets env defaults
  (`STORAGE_BACKEND=db`, `FLASK_DEBUG=False`, `PYTHONUNBUFFERED=1`),
  declares `EXPOSE 5000`, and adds a `HEALTHCHECK` that hits `/healthz`
  (ADR 0008). Runs `gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 web_app:app`
  with a `python web_app.py` dev fallback.

**`docker-compose.yml` full stack:**

- `db` (postgres:16-alpine, named volume, `pg_isready` healthcheck);
- `redis` (redis:7-alpine, named volume, `redis-cli ping` healthcheck) — used
  later for caching / Socket.IO pub-sub / rate-limit storage;
- `app` (builds the Dockerfile, depends on healthy db/redis, `/healthz`
  healthcheck, named volumes for data/logs);
- `worker` (same image; currently a stub that logs "Worker started" — the real
  RQ/Celery worker is a later phase);
- `nginx` (optional reverse proxy; intended to terminate TLS).

## Consequences

### Positive

- `docker compose up` boots the whole stack with prod parity in one command.
- The runtime image is slim: build toolchain + node_modules never enter it.
- Named volumes persist Postgres data, Redis data, app data, and logs across
  restarts.
- `HEALTHCHECK` wiring makes the image ready for orchestrators and registries.

### Negative / Trade-offs (known gaps, documented honestly)

- **Worker is a stub** — `command: ["python", "-c", "from logger import log; …"]`
  only logs a startup line; real background jobs (overdue emails, cover-fetch
  pooling, backups) are a later phase.
- **`nginx` service mounts `./docker/nginx.conf`, which does not exist yet** —
  the nginx service will fail to start until that file is added (or the service
  is removed). The app/db/redis services work without it.
- **Compose `SECRET_KEY` default is `change-me-in-production`** — this literal
  is *not* in `validate_secure_config()`'s denylist (which covers the empty
  string and two historical placeholders), so the stack would boot with a weak
  key. Operators must export `SECRET_KEY` (documented in compose); adding the
  compose default to the denylist is a recommended follow-up.
- **`CMD` swallows gunicorn stderr** (`2>/dev/null`) before the fallback,
  which hides boot errors; the fallback to the dev server also masks gunicorn
  failures in production.

## Alternatives considered

- **Single-stage image** — rejected: bloats the runtime with gcc, libpq-dev,
  Node, and node_modules that only the build needs.
- **Distroless runtime** — rejected: the app needs a Python interpreter plus
  runtime libraries (psycopg2/libpq, sqlite); `python:3.12-slim` is the
  pragmatic floor.
- **Compose-only, no Dockerfile** — rejected: there must be a buildable,
  pushable image for CI/CD and registry-based deploys.

## Verification

- `docker compose config` validates the YAML and service graph.
- The image `HEALTHCHECK` exercises `/healthz` (ADR 0008), tying the container
  story to the observability story.
