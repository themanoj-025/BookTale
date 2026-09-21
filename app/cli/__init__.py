"""app.cli — terminal UI command modules.

Moved from app.routes/ (CLI is not a web layer): the TUI menu in
app.routes.main dispatches to these modules. Each module owns one menu
domain (books, users, operations, reports, recommendations,
notifications, backup/restore).
"""
