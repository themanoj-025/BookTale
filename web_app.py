"""
web_app.py - Library Management System Web Interface (Entry Point)

Thin entry point that re-exports the Flask application from the app package.
The actual application logic lives in app/routes/web_app.py.

Every public name from the real module is re-exported so existing imports
(`from web_app import app`, `from web_app import storage, lib, asset, ...`)
keep working unchanged after the restructure.
"""

import os
import sys

# Add the project root to sys.path so app package imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.routes import web_app as _web_app

# Re-export every public name from the real module (tests and CLI scripts
# import views, helpers, and module-level singletons directly from web_app).
# This includes `app`, `socketio`, `storage`, `lib`, `asset`, views, and
# underscore helpers such as `_user_key` that tests reference.
globals().update({_k: _v for _k, _v in vars(_web_app).items() if not _k.startswith("__")})

# Explicit bindings for the __main__ block below (self-documenting and
# robust even if the re-export list changes).
app = _web_app.app
socketio = _web_app.socketio

if __name__ == "__main__":
    from app.config.settings import Config

    socketio.run(
        app,
        host=Config.FLASK_HOST,
        port=Config.FLASK_PORT,
        debug=Config.FLASK_DEBUG,
        allow_unsafe_werkzeug=True,
    )
