"""Add controlled multi-agent runtime persistence.

Revision ID: 0004_controlled_multi_agent
Revises: 0003_task_outbox
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_controlled_multi_agent"
down_revision = "0003_task_outbox"
branch_labels = None
depends_on = None


def upgrade(database: str = "postgres") -> None:
    if database == "postgres":
        return

    op.add_column("user", sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"))
    op.add_column("knowledge_base", sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"))
    op.create_index("ix_user_tenant_id", "user", ["tenant_id"])
    op.create_index("ix_knowledge_base_tenant_id", "knowledge_base", ["tenant_id"])

    op.create_table(
        "agent_run",
        sa.Column("request_id", sa.String(64), primary_key=True),
        sa.Column("thread_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("current_node", sa.String(64), nullable=False, server_default="input_safety"),
        sa.Column("state_version", sa.String(32), nullable=False, server_default="ma-v1"),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("final_answer", sa.Text()),
        sa.Column("citations_json", sa.JSON()),
        sa.Column("error_json", sa.JSON()),
        sa.Column("agent_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    for name, columns in (
        ("ix_agent_run_thread_id", ["thread_id"]),
        ("ix_agent_run_user_id", ["user_id"]),
        ("ix_agent_run_tenant_id", ["tenant_id"]),
        ("ix_agent_run_status", ["status"]),
    ):
        op.create_index(name, "agent_run", columns)

    op.create_table(
        "agent_step",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("agent_version", sa.String(32), nullable=False),
        sa.Column("prompt_version", sa.String(64)),
        sa.Column("model", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("next_node", sa.String(64)),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("trace_summary", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_step_request_id", "agent_step", ["request_id"])
    op.create_index("ix_agent_step_agent_name", "agent_step", ["agent_name"])

    op.create_table(
        "agent_tool_call",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(64)),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_tool_call_request_id", "agent_tool_call", ["request_id"])
    op.create_index("ix_agent_tool_call_tool_name", "agent_tool_call", ["tool_name"])
    op.create_index("ix_agent_tool_call_arguments_hash", "agent_tool_call", ["arguments_hash"])

    op.create_table(
        "agent_checkpoint",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("node_name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("state_version", sa.String(32), nullable=False),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("request_id", "sequence", name="uq_agent_checkpoint_request_sequence"),
    )
    op.create_index("ix_agent_checkpoint_request_id", "agent_checkpoint", ["request_id"])
    op.create_index("ix_agent_checkpoint_expires_at", "agent_checkpoint", ["expires_at"])

    op.create_table(
        "human_review",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reviewer_id", sa.BigInteger()),
        sa.Column("decision", sa.String(32)),
        sa.Column("edited_answer", sa.Text()),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime()),
    )
    op.create_index("ix_human_review_request_id", "human_review", ["request_id"], unique=True)
    op.create_index("ix_human_review_status", "human_review", ["status"])

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
    )
    for name, columns, unique in (
        ("ix_conversation_memory_memory_id", ["memory_id"], True),
        ("ix_conversation_memory_thread_id", ["thread_id"], False),
        ("ix_conversation_memory_user_id", ["user_id"], False),
        ("ix_conversation_memory_tenant_id", ["tenant_id"], False),
        ("ix_conversation_memory_expires_at", ["expires_at"], False),
    ):
        op.create_index(name, "conversation_memory", columns, unique=unique)


def downgrade(database: str = "postgres") -> None:
    if database == "postgres":
        return
    for table in (
        "conversation_memory", "human_review", "agent_checkpoint",
        "agent_tool_call", "agent_step", "agent_run",
    ):
        op.drop_table(table)
    op.drop_index("ix_knowledge_base_tenant_id", table_name="knowledge_base")
    op.drop_index("ix_user_tenant_id", table_name="user")
    op.drop_column("knowledge_base", "tenant_id")
    op.drop_column("user", "tenant_id")
