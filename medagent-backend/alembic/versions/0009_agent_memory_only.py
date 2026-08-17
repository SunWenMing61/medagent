"""Remove conversation-vector compatibility storage and retain key Agent Memory only.

Revision ID: 0009_agent_memory_only
Revises: 0008_agent_step_cost_usd
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_agent_memory_only"
down_revision = "0008_agent_step_cost_usd"
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {item["name"] for item in inspector.get_columns(table_name)}


def upgrade(database: str = "postgres") -> None:
    if database == "postgres":
        return

    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    # Preserve only structured session keys before removing duplicated raw messages.
    session_columns = _columns(bind, "agent_session")
    if "recent_messages_json" in session_columns:
        op.execute(
            """
            UPDATE agent_session
            SET rolling_summary = JSON_OBJECT(
                'active_topic', active_topic,
                'active_entities', active_entities_json,
                'confirmed_constraints', confirmed_constraints_json,
                'unresolved_questions', unresolved_questions_json,
                'latest_corrections', latest_corrections_json
            )
            """
        )
        op.drop_column("agent_session", "recent_messages_json")

    for column_name in (
        "embedding_json",
        "embedding_model",
        "embedding_dimension",
        "embedding_version",
    ):
        if column_name in _columns(bind, "agent_memory"):
            op.drop_column("agent_memory", column_name)

    if "conversation_memory" in tables:
        op.drop_table("conversation_memory")


def downgrade(database: str = "postgres") -> None:
    if database == "postgres":
        return

    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "conversation_memory" not in tables:
        op.create_table(
            "conversation_memory",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("memory_id", sa.String(64), nullable=False),
            sa.Column("thread_id", sa.String(64)),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("memory_type", sa.String(32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("source_message_ids", sa.JSON()),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
            sa.Column("expires_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("memory_id", name="uq_conversation_memory_memory_id"),
        )
        for name, columns in (
            ("ix_conversation_memory_thread_id", ["thread_id"]),
            ("ix_conversation_memory_user_id", ["user_id"]),
            ("ix_conversation_memory_tenant_id", ["tenant_id"]),
            ("ix_conversation_memory_expires_at", ["expires_at"]),
        ):
            op.create_index(name, "conversation_memory", columns)

    if "recent_messages_json" not in _columns(bind, "agent_session"):
        op.add_column(
            "agent_session",
            sa.Column("recent_messages_json", sa.JSON(), nullable=False, server_default="[]"),
        )

    memory_columns = _columns(bind, "agent_memory")
    for column in (
        sa.Column("embedding_json", sa.JSON()),
        sa.Column("embedding_model", sa.String(128)),
        sa.Column("embedding_dimension", sa.Integer()),
        sa.Column("embedding_version", sa.String(32)),
    ):
        if column.name not in memory_columns:
            op.add_column("agent_memory", column)
