# ADR 0001 — Fail-fast `SECRET_KEY` validation

- **Status:** Accepted
- **Date:** 2026-08-01
- **Deciders:** Security audit findings; P0 remediation
- **Related code:** `config.py` (`Config.SECRET_KEY`, `_INSECURE_SECRET_KEYS`, `validate_secure_config()`), `web_app.py:51`

## Context

`Config.SECRET_KEY` defaulted to a known, publicly documented literal
(`"change-this-secret-key-in-production"`). The app signs Flask session cookies
with this key, and the session carries the authenticated `role` claim. If the
app was ever deployed without an override:

1. Anyone who read the README (or guessed the well-known default) could forge a
   session cookie with `role=admin`.
2. The failure mode was **silent**: the app booted fine and behaved normally,
   so nothing alerted the operator that the key was insecure.

A security review classified this as **P0 — critical** because it enables full
privilege escalation with zero interaction beyond knowing the default.

## Decision

- Remove the insecure default: `SECRET_KEY` now defaults to an empty string
  (`os.getenv("SECRET_KEY", "")`).
- Add `_INSECURE_SECRET_KEYS`, a denylist of every known default (empty string
  plus the two historical placeholder values).
- Add `validate_secure_config()`, which raises `RuntimeError` if the effective
  key is in the denylist. `web_app.py` calls it at module import, so **the web
  server refuses to boot** — never starts with a forgeable key. Note the scope:
  only the web server path enforces this — the CLI entry points
  (`main.py`/`start.py`) never import `web_app.py` and therefore don't
  validate, which is correct since they never sign session cookies.
- The error message tells the operator exactly how to fix it:
  `python -c 'import secrets; print(secrets.token_hex(32))'` and set
  `SECRET_KEY` in the environment / `.env`.

This is the "fail fast at startup" pattern used by Django
(`SECRET_KEY` required), Rails (`secret_key_base` required in production), and
12-factor apps: **misconfiguration is an error, not a warning.**

## Consequences

### Positive

- Session-cookie forgery via a default key is impossible; the app cannot run
  insecurely by accident.
- Detection is immediate (boot failure) rather than a latent vulnerability.
- The denylist approach is extensible — future known-bad values can be added.

### Negative

- **Every environment must now supply a `SECRET_KEY`**, including local dev
  and CI. This is a deliberate cost: it forces the operator to generate a real
  key instead of relying on a default.
- Tests that import `web_app.py` must set `SECRET_KEY` first — handled by the
  security test fixture (`tests/security/test_web_security.py`).

### Regression coverage

- `TestBootSecurity` asserts that importing the app with an unset or
  known-default `SECRET_KEY` raises `RuntimeError`, and that a valid key boots
  cleanly. This test would have failed against the pre-fix code.

## Alternatives considered

- **Generate a random key at boot if unset.** Rejected: a random key per boot
  invalidates all sessions on restart and hides configuration drift; it also
  makes multi-worker deployments inconsistent.
- **Warn instead of raise.** Rejected: warnings are ignored in production logs;
  the whole point is that an insecure boot must be impossible.
