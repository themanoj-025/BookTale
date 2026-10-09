# Runbook: Restore from Backup

## Backup strategy

- `backup.py` snapshots the data layer (JSON files when the legacy backend is
  used; SQLite file / Postgres dump on the relational backend) into
  `Config.BACKUPS_DIR` with a timestamp.
- A scheduled job (background worker) creates backups and prunes anything
  older than the retention window (keep last N).
- The CLI creates an auto-backup on exit (`main.py`).

## Restore

1. **Stop writes** — put the app in maintenance mode (scale to 0 / block
   traffic) so no new data lands mid-restore.
2. List available backups:
   ```bash
   python -c "from backup import list_backups; [print(b) for b in list_backups()]"
   ```
3. Restore the chosen backup:
   ```bash
   python -c "from backup import restore_backup; print(restore_backup('<path>'))"
   ```
   The current dataset is archived before overwrite.
4. Verify: log in as admin, spot-check a user, a book, and a transaction;
   run `/readyz` and `scripts/smoke_checklist.py`.

## Testing restores

Restores must be tested, not assumed. Schedule a monthly drill: restore into
a scratch copy of the environment and confirm row counts + a checkout flow
work before declaring the backup trustworthy.
