"""0002_audit_log

Revision ID: a1b2c3d4e5f6
Revises: 5f42e5bb1bda
Create Date: 2026-08-01 12:00:00.000000

Adds the append-only admin audit trail table (who changed what admin setting,
when, and from where) — see db/models.py AuditLog.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "5f42e5bb1bda"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("admin_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_action_created", "audit_logs", ["action", "created_at"], unique=False)
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_admin_id"), "audit_logs", ["admin_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False)
    op.create_index(op.f("ix_audit_logs_ip_address"), "audit_logs", ["ip_address"], unique=False)
    op.create_index(
        "ix_audit_admin_created", "audit_logs", ["admin_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_audit_admin_created", table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_ip_address"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_admin_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_index("ix_audit_action_created", table_name="audit_logs")
    op.drop_table("audit_logs")
