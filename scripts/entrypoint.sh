#!/usr/bin/env sh
# scripts/entrypoint.sh - Book-Tale container entrypoint.
#
# Wires log rotation + age-based retention (app/scripts/rotate_logs.py) before
# handing over to the production web server (gunicorn) or the dev server, so
# app/logs/ stays bounded regardless of runtime duration.
#
# Usage (Dockerfile):
#   CMD ["sh", "-c", "scripts/entrypoint.sh 'gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 web_app:app'"]
#
set -e

LOGS_DIR="/app/logs"

echo "[entrypoint] rotating + pruning logs under ${LOGS_DIR} ..."

# Rotate-and-prune the files managed by RotatingFileHandler. The handler
# (5 MB / 5 backups) is the final runtime guard; this sweep applies the
# age-based policy (LOG_RETENTION_DAYS / LOG_RETENTION_KEEP).
if [ -d "${LOGS_DIR}" ]; then
    python - <<'PY'
import os
import sys

sys.path.insert(0, "/app")
from app.config.settings import Config
from scripts.rotate_logs import rotate_logs

rotate_logs(
    retention_days=int(os.environ.get("LOG_RETENTION_DAYS", "30")),
    retention_keep=int(os.environ.get("LOG_RETENTION_KEEP", "10")),
)
PY
    rc=$?
    if [ ${rc} -ne 0 ]; then
        echo "[entrypoint] WARNING: log rotation returned ${rc}; continuing with service start."
    fi
fi

echo "[entrypoint] starting service: $*"
exec "$@"
