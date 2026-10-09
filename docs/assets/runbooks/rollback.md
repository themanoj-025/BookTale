# Runbook: Rollback

## Before you roll back

1. **Stop traffic to the new version** (scale the new release to 0 / route
   away) — never migrate data mid-rollback.
2. **Identify the schema delta**: if the failing release added a migration
   (e.g. `0003_auth_tokens`), decide whether to keep or revert it. Reverting
   a migration that added a table is safe; reverting one that dropped data is
   not. Prefer keeping new tables and rolling back only the application code.

## Steps

1. Redeploy the previous known-good image/tag.
2. If the failing release's migrations must be undone **and no data depends
   on them**, run:
   ```bash
   alembic downgrade -1
   ```
   Otherwise leave the schema in place — forward-only is the safer default.
3. Verify `/healthz` + `/readyz` and run `scripts/smoke_checklist.py`.
4. File the incident (see `incident-response.md`).

## Notes

- Schema changes are designed to be backward-compatible (additive tables /
  nullable columns), so app rollback is normally sufficient.
- Never `DROP`/destructive-migrate without a confirmed backup
  (`restore-from-backup.md`).
