# ADR 0008 — Health Endpoints, Request Correlation & Security Headers

- **Status:** Accepted (2026-08-01)
- **Deciders:** Project owner, acting senior staff engineer
- **Related code:** `web_app.py` (`/healthz`, `/readyz`,
  `_request_id_middleware`, `apply_security_headers`), `logger.py`
  (`set_request_id`)
- **Related ADRs:** ADR 0006 (request-ID middleware feeds the JSON log
  formatter), ADR 0009 (Docker `HEALTHCHECK` probes `/healthz`)

---

## Context

The app had no liveness/readiness endpoints, no request-ID correlation in logs,
and no security response headers. Consequences:

1. **No deployability signals** — nothing for a Docker `HEALTHCHECK`, an
   orchestrator (K8s/ECS), or a load balancer to probe.
2. **No request correlation** — logs were a flat stream with no way to group
   all entries belonging to one HTTP request during triage.
3. **Info disclosure** — `/readyz` echoed `str(e)` on DB failure, leaking
   driver names (`psycopg2`), connection strings, and internal paths to clients.
4. **Missing baseline hardening** — no CSP, no `nosniff`, no frame protection.

## Decision

- **`/healthz` (liveness):** returns `{"status": "ok"}` (200) — proves the
  process is alive and the HTTP stack responds. No dependencies checked.
- **`/readyz` (readiness):** executes `SELECT 1` through a SQLAlchemy session;
  returns 200 `{"status": "ok", "database": "connected"}` on success. On
  failure it **logs the full detail** for operators and returns
  **503 `{"status": "not_ready", "error": "database unreachable"}`** — a
  generic message to clients, never `str(e)`.
- **Request-ID middleware:** a `before_request` hook calls `set_request_id()`
  (a `contextvars`-backed helper), so every log line in a request carries the
  same `request_id` (see ADR 0006).
- **Security headers on every response** (`after_request`):
  - `Content-Security-Policy` — `default-src 'self'`; scripts/styles/fonts
    pinned to self + specific CDN versions (note: `'unsafe-inline'` remains in
    `script-src`/`style-src` for the string-built pages, so CSP is layered
    defense, not a replacement for escaping); `frame-ancestors 'none'`;
  - `X-Content-Type-Options: nosniff`;
  - `X-Frame-Options: DENY`;
  - `Referrer-Policy: strict-origin-when-cross-origin`;
  - `Permissions-Policy` (camera/mic/geolocation off, `interest-cohort=()`);
  - `X-XSS-Protection: 0` (the legacy filter is itself a vector; real XSS
    defense is CSP + escaping).

## Consequences

### Positive

- Docker `HEALTHCHECK` and orchestrator probes work out of the box (ADR 0009
  wires them in).
- Logs correlate per request across all modules via `request_id`.
- Error responses stop leaking internals; the detail stays in server logs.
- Baseline clickjacking / MIME-sniffing / permissions-policy hardening is in
  place.

### Negative / Trade-offs

- `readyz` currently checks the DB only; Redis/SMTP readiness is a later
  enhancement (both exist in the compose stack but aren't probed yet).
- No Prometheus metrics or tracing yet — observability beyond logs/health is a
  later phase.
- The security headers are emitted by the Flask app itself; a future
  TLS-terminating proxy (nginx in the compose stack) may also set/merge them.

## Alternatives considered

- **Always-200 health endpoint** — rejected: masks a downed DB from the
  orchestrator and produces silent partial outages.
- **Return `str(e)` from `/readyz`** — rejected: info disclosure; this was the
  bug being fixed (the detailed error is logged instead).
- **Global/random request IDs** — rejected: `contextvars` is the
  thread/async-safe mechanism and matches the logger's design (ADR 0006).

## Regression coverage

`TestReadyz::test_readyz_hides_internal_error_details` monkeypatches
`db.database.get_session_factory` to raise and asserts the endpoint returns
503 with the generic `"database unreachable"` body and that
`psycopg2`/`db.internal`/`OperationalError` never appear in the response.
