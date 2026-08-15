"""
worker.py - Background job worker (Entry Point)

Thin entry point for the RQ worker + cron scheduler. docker-compose's
`worker` service runs `python worker.py`. The actual implementation lives in
app/jobs/worker.py.
"""

import os
import sys

# Add the project root to sys.path so app package imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.jobs.worker import main

if __name__ == "__main__":
    main()
