"""
gamification_routes.py — Backward-compatible re-exporter.

All page routes live in ``gamification_pkg/`` as focused modules.
This file re-exports the registration function so existing
``from app.routes.gamification_routes import register_gamification_routes``
continues to work unchanged.
"""

from app.routes.gamification_pkg import register_gamification_routes  # noqa: F401
