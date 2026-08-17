"""Add durable task outbox.

Revision ID: 0003_task_outbox
Revises: 0002_lexical_index
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_task_outbox"
down_revision = "0002_lexical_index"
branch_labels = None
depends_on = None


def upgrade(database: str = "postgres") -> None:
    if database != "mysql":
        return
    op.create_table(
        "task_outbox",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("task_id", sa.String(100), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("dispatched_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_task_outbox_event_type", "task_outbox", ["event_type"])
    op.create_index("ix_task_outbox_idempotency_key", "task_outbox", ["idempotency_key"], unique=True)
    op.create_index("ix_task_outbox_status", "task_outbox", ["status"])


def downgrade(database: str = "postgres") -> None:
    if database == "mysql":
        op.drop_table("task_outbox")
