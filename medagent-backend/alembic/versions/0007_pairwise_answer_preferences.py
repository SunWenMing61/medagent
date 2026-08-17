"""Pairwise answer variants and adaptive user preference profile.

Revision ID: 0007_pairwise_answer_preferences
Revises: 0006_memory_retrieval_v2
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_pairwise_answer_preferences"
down_revision = "0006_memory_retrieval_v2"
branch_labels = None
depends_on = None


def upgrade(database: str = "postgres") -> None:
    if database == "postgres":
        return
    op.add_column("chat_message", sa.Column("answer_variants_json", sa.JSON(), nullable=True))
    op.add_column("chat_message", sa.Column("recommended_variant_id", sa.String(64), nullable=True))
    op.add_column("chat_message", sa.Column("selected_variant_id", sa.String(64), nullable=True))
    op.create_table(
        "answer_preference",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("request_id", sa.String(64)),
        sa.Column("chosen_variant_id", sa.String(64), nullable=False),
        sa.Column("rejected_variant_id", sa.String(64), nullable=False),
        sa.Column("chosen_style", sa.String(32), nullable=False),
        sa.Column("rejected_style", sa.String(32), nullable=False),
        sa.Column("context_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "message_id", name="uq_answer_preference_user_message"),
    )
    for column in ("tenant_id", "user_id", "session_id", "message_id", "request_id", "chosen_style"):
        op.create_index(f"ix_answer_preference_{column}", "answer_preference", [column])
    op.create_table(
        "user_answer_preference_profile",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("concise_votes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detailed_votes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_choices", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preferred_style", sa.String(32), nullable=False, server_default="concise_evidence"),
        sa.Column("preference_strength", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("profile_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_user_answer_preference_profile"),
    )
    op.create_index("ix_user_answer_preference_profile_tenant_id", "user_answer_preference_profile", ["tenant_id"])
    op.create_index("ix_user_answer_preference_profile_user_id", "user_answer_preference_profile", ["user_id"])


def downgrade(database: str = "postgres") -> None:
    if database == "postgres":
        return
    op.drop_table("user_answer_preference_profile")
    op.drop_table("answer_preference")
    op.drop_column("chat_message", "selected_variant_id")
    op.drop_column("chat_message", "recommended_variant_id")
    op.drop_column("chat_message", "answer_variants_json")
