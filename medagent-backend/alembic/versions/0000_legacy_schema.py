"""Establish the legacy application schema under Alembic control.

Revision ID: 0000_legacy_schema
Revises: None
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0000_legacy_schema"
down_revision = None
branch_labels = None
depends_on = None


def _create(name: str, *columns, indexes=()) -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(name):
        return
    op.create_table(name, *columns)
    for index_name, fields, unique in indexes:
        op.create_index(index_name, name, fields, unique=unique)


def upgrade(database: str = "postgres") -> None:
    if database == "postgres":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        _create(
            "document_chunk",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("document_id", sa.BigInteger(), nullable=False),
            sa.Column("kb_id", sa.BigInteger(), nullable=False),
            sa.Column("chunk_index", sa.Integer(), server_default="0"),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("page_num", sa.Integer(), nullable=True),
            sa.Column("embedding", Vector(1024), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            indexes=(
                ("ix_document_chunk_document_id", ["document_id"], False),
                ("ix_document_chunk_kb_id", ["kb_id"], False),
            ),
        )
        return

    _create(
        "user",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("role", sa.String(20), server_default="user"),
        sa.Column("status", sa.Integer(), server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        indexes=(("ix_user_username", ["username"], True),),
    )
    _create(
        "knowledge_base",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("type", sa.String(20), server_default="general"),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("visibility", sa.String(20), server_default="private"),
        sa.Column("status", sa.Integer(), server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        indexes=(("ix_knowledge_base_owner_id", ["owner_id"], False),),
    )
    _create(
        "document",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("kb_id", sa.BigInteger(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("file_size", sa.BigInteger(), server_default="0"),
        sa.Column("file_path", sa.String(500)),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("parse_status", sa.String(20), server_default="pending"),
        sa.Column("vector_status", sa.String(20), server_default="pending"),
        sa.Column("uploader_id", sa.BigInteger(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        indexes=(("ix_document_kb_id", ["kb_id"], False),),
    )
    _create(
        "chat_session",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(255)),
        sa.Column("session_type", sa.String(20), server_default="qa"),
        sa.Column("summary", sa.Text()),
        sa.Column("kb_ids_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        indexes=(("ix_chat_session_user_id", ["user_id"], False),),
    )
    inspector = sa.inspect(op.get_bind())
    if "chat_session" in inspector.get_table_names() and "kb_ids_json" not in {
        column["name"] for column in inspector.get_columns("chat_session")
    }:
        op.add_column("chat_session", sa.Column("kb_ids_json", sa.Text(), nullable=True))
    _create(
        "chat_message",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("references_json", sa.JSON()),
        sa.Column("safety_flag", sa.String(50)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        indexes=(("ix_chat_message_session_id", ["session_id"], False),),
    )
    _create(
        "feedback",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("feedback_type", sa.String(50), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        indexes=(("ix_feedback_user_id", ["user_id"], False),),
    )
    _create(
        "system_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger()),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("status", sa.String(20), server_default="success"),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    _create(
        "model_config",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("llm_model", sa.String(100), server_default="gpt-4o-mini"),
        sa.Column("embedding_model", sa.String(100), server_default="text-embedding-3-small"),
        sa.Column("top_k", sa.Integer(), server_default="5"),
        sa.Column("similarity_threshold", sa.Float(), server_default="0.5"),
        sa.Column("temperature", sa.Float(), server_default="0.7"),
        sa.Column("max_tokens", sa.Integer(), server_default="2048"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    _create(
        "graph_entity",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("kb_id", sa.BigInteger(), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("metadata_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        indexes=(
            ("ix_graph_entity_kb_id", ["kb_id"], False),
            ("ix_graph_entity_entity_type", ["entity_type"], False),
        ),
    )
    _create(
        "graph_relation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_entity_id", sa.BigInteger(), nullable=False),
        sa.Column("target_entity_id", sa.BigInteger(), nullable=False),
        sa.Column("relation_type", sa.String(50), nullable=False),
        sa.Column("metadata_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        indexes=(
            ("ix_graph_relation_source_entity_id", ["source_entity_id"], False),
            ("ix_graph_relation_target_entity_id", ["target_entity_id"], False),
            ("ix_graph_relation_relation_type", ["relation_type"], False),
        ),
    )


def downgrade(database: str = "postgres") -> None:
    if database == "postgres":
        op.drop_table("document_chunk")
        return
    for table in (
        "graph_relation", "graph_entity", "model_config", "system_log", "feedback",
        "chat_message", "chat_session", "document", "knowledge_base", "user",
    ):
        op.drop_table(table)
