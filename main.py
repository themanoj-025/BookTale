"""
main.py - Library Management System CLI (Entry Point)

This is a thin entry point that imports the CLI logic from the app package.
The actual application logic lives in app/routes/main.py.
"""

import os
import sys

# Add the project root to sys.path so app package imports work

from app.routes.main import main

if __name__ == "__main__":
    main()
