"""
app/db/ - SQLAlchemy data layer

Replaces the hand-rolled JSON storage with a relational schema that is a strict
superset of the old data. SQLite is the default (dev), PostgreSQL is supported
via the DATABASE_URL environment variable with the same schema.

Layout:
    models.py       - SQLAlchemy 2.0 declarative models (one table per JSON entity)
    database.py     - engine / session factory, WAL + busy_timeout for SQLite
    repositories.py - indexed queries replacing the O(n) JSON scans
    service.py      - transactional checkout / return / reserve (oversell-proof)

One-shot JSON -> DB migration lives in scripts/migrate_json_to_db.py.
"""
