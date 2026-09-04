"""
start.py - Library Management System Launcher (Entry Point)

This is a thin entry point that imports the launcher from the app package.
The actual launcher logic lives in app/routes/start.py.
"""

import os
import sys

# Ensure we're in the project directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# Add the project root to sys.path

from app.routes.start import main

if __name__ == "__main__":
    main()
