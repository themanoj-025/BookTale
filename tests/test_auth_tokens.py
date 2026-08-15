"""test_auth_tokens.py - DB-backed one-time token regression tests.

Regression for the Phase 4 P1 finding: reset/verify tokens lived in
class-level in-memory dicts on AuthManager — lost on every restart (users
stranded with a valid-but-dead link after a deploy) and verify tokens never
expired. They now persist in the auth_tokens table with an explicit purpose
and expires_at (15 min reset / 24 h verify), survive a cold engine restart,
and stale rows are reaped by purge_expired_tokens().
"""

import os
import sys
from datetime import datetime, timedelta

# This file lives at tests/test_auth_tokens.py — one level below the root.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

# NOTE: this module deliberately does NOT mutate Config.DATA_DIR at import
# time. Other test modules (e.g. test_web_security) also redirect that path,
# and the module-global SQLAlchemy engine is cached by URL — the last import
# to touch Config would otherwise hijack every later test's database. Each
# test isolates itself via the _isolated_db fixture and restores the previous
# value in a finally.

import pytest
from sqlalchemy import select, update

import app.services.auth.auth as authmod
from app.config.settings import Config
from app.db.database import session_scope
from app.db.models import AuthToken


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    """Run each test against its own temp SQLite DB; restore global state.

    The auth token functions go through db.database.session_scope (the
    module-global engine keyed by Config.DATA_DIR), so this fixture redirects
    DATA_DIR to a per-test temp dir, seeds the FK-referenced users, and
    restores the previous value afterwards — leaving the shared
    Config/engine state other test modules rely on untouched.
    """
    from app.db.database import create_all
    from app.db.models import User

    original_data_dir = Config.DATA_DIR
    data_dir = str(tmp_path / "data")
    try:
        Config.DATA_DIR = data_dir
        os.makedirs(data_dir, exist_ok=True)
        create_all()
        # Tokens carry a users.user_id FK; the real app only mints tokens for
        # existing users, so seed the members these tests reference.
        test_uids = ["MEM-%d" % i for i in range(1, 10)] + ["MEM-RESTART"]
        with session_scope() as db:
            db.execute(AuthToken.__table__.delete())
            db.execute(User.__table__.delete())
            for uid in test_uids:
                db.add(
                    User(
                        user_id=uid,
                        name="Token Test User",
                        email="%s@t.io" % uid.lower(),
                        role="user",
                        password_hash="unused",
                        membership_status="Active",
                    )
                )
        yield data_dir
    finally:
        Config.DATA_DIR = original_data_dir


def _force_expiry(token: str) -> None:
    with session_scope() as db:
        db.execute(
            update(AuthToken)
            .where(AuthToken.token == token)
            .values(expires_at=(datetime.now() - timedelta(minutes=1)).isoformat())
        )


class TestResetToken:
    def test_round_trip(self):
        tok = authmod.generate_reset_token("MEM-1")
        assert authmod.verify_reset_token(tok) == "MEM-1"

    def test_consumed_once(self):
        tok = authmod.generate_reset_token("MEM-2")
        assert authmod.consume_reset_token(tok) == "MEM-2"
        # Single-use: a second consume (or verify) finds nothing.
        assert authmod.verify_reset_token(tok) is None
        assert authmod.consume_reset_token(tok) is None

    def test_unknown_token_rejected(self):
        assert authmod.verify_reset_token("does-not-exist") is None

    def test_expired_token_rejected_and_reaped(self):
        tok = authmod.generate_reset_token("MEM-4")
        _force_expiry(tok)
        assert authmod.verify_reset_token(tok) is None
        # The expired row is garbage-collected on first touch.
        with session_scope() as db:
            row = db.scalar(select(AuthToken).where(AuthToken.token == tok))
            assert row is None


class TestVerifyToken:
    def test_round_trip(self):
        tok = authmod.generate_verify_token("MEM-3")
        assert authmod.verify_email_token(tok) == "MEM-3"
        assert authmod.consume_verify_token(tok) == "MEM-3"
        assert authmod.verify_email_token(tok) is None

    def test_expired_verify_token_rejected(self):
        tok = authmod.generate_verify_token("MEM-5")
        _force_expiry(tok)
        assert authmod.verify_email_token(tok) is None

    def test_purpose_isolation(self):
        """A reset token must never validate as an email-verify token."""
        tok = authmod.generate_reset_token("MEM-9")
        assert authmod.verify_email_token(tok) is None


class TestPersistenceAndCleanup:
    def test_token_lives_in_db_not_memory(self):
        """The token must be a DB row — the whole point vs. in-memory dicts."""
        tok = authmod.generate_reset_token("MEM-6")
        with session_scope() as db:
            row = db.scalar(select(AuthToken).where(AuthToken.token == tok))
            assert row is not None
            assert row.user_id == "MEM-6"
            assert row.purpose == "reset"
            assert row.expires_at > datetime.now().isoformat()

    def test_token_survives_process_restart(self, _isolated_db):
        """A brand-new process pointed at the same DB file must verify it.

        This is the P1 regression: in-memory dicts lost every token on
        restart. A cold interpreter re-reading the same SQLite file must
        still resolve the token.
        """
        import subprocess
        import sys as _sys

        tok = authmod.generate_reset_token("MEM-RESTART")
        code = (
            "import sys\n"
            "sys.path.insert(0, %r)\n"
            "from app.config.settings import Config\n"
            "Config.DATA_DIR = %r\n"
            "import app.services.auth.auth as auth\n"
            "ok = auth.verify_reset_token(%r)\n"
            "print('OK' if ok == 'MEM-RESTART' else 'MISSING:' + repr(ok))\n"
        ) % (PROJECT_ROOT, _isolated_db, tok)
        r = subprocess.run(
            [_sys.executable, "-c", code],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=PROJECT_ROOT,
            timeout=90,
        )
        assert "OK" in (
            r.stdout or ""
        ), f"token lost on restart: stdout={r.stdout!r} stderr={r.stderr!r}"

    def test_purge_removes_only_expired(self):
        fresh = authmod.generate_reset_token("MEM-7")
        stale = authmod.generate_reset_token("MEM-8")
        _force_expiry(stale)
        removed = authmod.purge_expired_tokens()
        assert removed >= 1
        assert authmod.verify_reset_token(fresh) == "MEM-7"
        assert authmod.verify_reset_token(stale) is None
