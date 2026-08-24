# Runbook: Deploy BookTale

## Prerequisites

- Docker + Docker Compose (local parity stack: app + worker + Postgres + Redis).
- `SECRET_KEY` (32+ random chars), `DATABASE_URL`, `REDIS_URL` — the app
  refuses to boot with a default/empty `SECRET_KEY` (fail-fast).

## Local (docker compose)

```bash
docker compose up --build -d
docker compose exec app alembic upgrade head   # first boot only
```

The app seeds an admin on first boot; the password is printed once to the
server logs (set `DEFAULT_ADMIN_PASSWORD` beforehand to control it).

## Production

1. Run migrations against the target DB **before** deploying new code:
   ```bash
   alembic upgrade head
   ```
2. Deploy the image (Fly.io / Render / Railway / your platform), with the
   `cd.yml` pipeline: build → push → migrate → deploy → smoke-test the live
   URL → auto-rollback on smoke failure.
3. Health checks: wire the platform to probe `/healthz` (liveness) and
   `/readyz` (readiness — verifies the DB is reachable).

## Post-deploy verification

- `GET /healthz` → 200
- `GET /readyz` → 200
- Log in, browse `/books`, run `scripts/smoke_checklist.py` against the URL.
