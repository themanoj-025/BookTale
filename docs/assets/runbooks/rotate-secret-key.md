# Runbook: Rotate SECRET_KEY

Rotating the session-signing key invalidates every existing session cookie —
users must log in again. Plan for a brief logout spike.

## When to rotate

- Suspected or confirmed leakage of the key (logs, repo history, a
  co-worker's laptop).
- Periodic hygiene (e.g. every 90 days).

## Steps

1. Generate a new key:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
2. Set `SECRET_KEY=<new>` in the environment/secrets manager for **every**
   app instance (all workers must share the same key or sessions will be
   signed with different keys).
3. Restart the app (rolling restart to avoid downtime).
4. Verify: `/healthz` 200; log in as a user and as the admin.
5. If the leak was confirmed, also rotate `DEFAULT_ADMIN_PASSWORD` and any
   SMTP password, and review the audit log for anomalous admin activity.

## Never

- Commit the key to version control.
- Use the documented default (`change-this-secret-key-in-production`) — the
  app refuses to boot with it.
