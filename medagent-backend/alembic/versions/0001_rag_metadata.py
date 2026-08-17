"""Add versioned parsing and chunk provenance fields.

Revision ID: 0001_rag_metadata
Revises: None
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0001_rag_metadata"
down_revision = "0000_legacy_schema"
branch_labels = None
depends_on = None


def upgrade(database: str = "postgres") -> None:
    if database == "postgres":
        op.alter_column("document_chunk", "embedding", type_=Vector(), existing_type=Vector(1024))
        for column in (
            sa.Column("logical_id", sa.String(64), nullable=True),
            sa.Column("parent_chunk_id", sa.BigInteger(), nullable=True),
            sa.Column("chunk_type", sa.String(16), nullable=False, server_default="child"),
            sa.Column("page_start", sa.Integer(), nullable=True),
            sa.Column("page_end", sa.Integer(), nullable=True),
            sa.Column("section_path", postgresql.JSONB(), nullable=True),
            sa.Column("start_offset", sa.Integer(), nullable=True),
            sa.Column("end_offset", sa.Integer(), nullable=True),
            sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("content_sha256", sa.String(64), nullable=True),
            sa.Column("parser_version", sa.String(64), nullable=True),
            sa.Column("chunker_version", sa.String(64), nullable=True),
            sa.Column("embedding_model", sa.String(128), nullable=True),
            sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
            sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
            sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        ):
            op.add_column("document_chunk", column)
        op.create_foreign_key(
            "fk_document_chunk_parent", "document_chunk", "document_chunk",
            ["parent_chunk_id"], ["id"], ondelete="CASCADE",
        )
        op.create_index("ix_document_chunk_logical_id", "document_chunk", ["logical_id"])
        op.create_unique_constraint(
            "uq_document_chunk_document_logical",
            "document_chunk",
            ["document_id", "logical_id"],
        )
        op.create_index("ix_document_chunk_parent_chunk_id", "document_chunk", ["parent_chunk_id"])
        op.create_index("ix_document_chunk_chunk_type", "document_chunk", ["chunk_type"])
        op.create_index("ix_document_chunk_content_sha256", "document_chunk", ["content_sha256"])
        op.create_index(
            "ix_document_chunk_search_vector", "document_chunk", ["search_vector"],
            postgresql_using="gin",
        )
        return

    for column in (
        sa.Column("content_sha256", sa.String(64), nullable=True),
        sa.Column("parser_version", sa.String(64), nullable=True),
        sa.Column("chunker_version", sa.String(64), nullable=True),
        sa.Column("embedding_model", sa.String(128), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ocr_page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processing_warnings", sa.JSON(), nullable=True),
        sa.Column("processing_task_id", sa.String(100), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(), nullable=True),
    ):
        op.add_column("document", column)
    op.create_index("ix_document_content_sha256", "document", ["content_sha256"])
    op.create_index("ix_document_processing_task_id", "document", ["processing_task_id"])


def downgrade(database: str = "postgres") -> None:
    if database == "postgres":
        op.drop_index("ix_document_chunk_search_vector", table_name="document_chunk")
        op.drop_index("ix_document_chunk_content_sha256", table_name="document_chunk")
        op.drop_index("ix_document_chunk_chunk_type", table_name="document_chunk")
        op.drop_index("ix_document_chunk_parent_chunk_id", table_name="document_chunk")
        op.drop_constraint("uq_document_chunk_document_logical", "document_chunk", type_="unique")
        op.drop_index("ix_document_chunk_logical_id", table_name="document_chunk")
        op.drop_constraint("fk_document_chunk_parent", "document_chunk", type_="foreignkey")
        for name in (
            "search_vector", "metadata_json", "embedding_dimensions", "embedding_model",
            "chunker_version", "parser_version", "content_sha256", "token_count",
            "end_offset", "start_offset", "section_path", "page_end", "page_start",
            "chunk_type", "parent_chunk_id", "logical_id",
        ):
            op.drop_column("document_chunk", name)
        op.alter_column("document_chunk", "embedding", type_=Vector(1024), existing_type=Vector())
        return

    op.drop_index("ix_document_processing_task_id", table_name="document")
    op.drop_index("ix_document_content_sha256", table_name="document")
    for name in (
        "processing_completed_at", "processing_started_at", "processing_task_id",
        "processing_warnings", "chunk_count", "ocr_page_count", "page_count",
        "embedding_dimensions", "embedding_model", "chunker_version", "parser_version",
        "content_sha256",
    ):
        op.drop_column("document", name)
