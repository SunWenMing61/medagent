"""Add traceable PDF layers and governed tool runtime.

Revision ID: 0005_pdf_tooling_v2
Revises: 0004_controlled_multi_agent
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_pdf_tooling_v2"
down_revision = "0004_controlled_multi_agent"
branch_labels = None
depends_on = None


def upgrade(database: str = "postgres") -> None:
    if database == "postgres":
        for name, column in (
            ("source_block_ids", sa.Column("source_block_ids", sa.JSON())),
            ("content_type", sa.Column("content_type", sa.String(24), nullable=False, server_default="paragraph")),
            ("cleaning_version", sa.Column("cleaning_version", sa.String(64))),
            ("extraction_method", sa.Column("extraction_method", sa.String(32))),
            ("ocr_confidence", sa.Column("ocr_confidence", sa.Float())),
            ("quality_status", sa.Column("quality_status", sa.String(32), nullable=False, server_default="good")),
        ):
            op.add_column("document_chunk", column)
        op.create_index("ix_document_chunk_content_type", "document_chunk", ["content_type"])
        op.create_index("ix_document_chunk_quality_status", "document_chunk", ["quality_status"])
        return

    for column in (
        sa.Column("normalized_text_sha256", sa.String(64)),
        sa.Column("cleaning_version", sa.String(64)),
        sa.Column("quality_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("document_version", sa.String(64)),
        sa.Column("version_status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("supersedes_document_id", sa.BigInteger()),
    ):
        op.add_column("document", column)
    op.create_index("ix_document_normalized_text_sha256", "document", ["normalized_text_sha256"])
    op.create_index("ix_document_quality_status", "document", ["quality_status"])
    op.create_index("ix_document_version_status", "document", ["version_status"])
    op.create_index("ix_document_supersedes_document_id", "document", ["supersedes_document_id"])

    op.create_table(
        "document_page",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("page_num", sa.Integer(), nullable=False),
        sa.Column("page_type", sa.String(32), nullable=False),
        sa.Column("extraction_method", sa.String(32), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("cleaned_text", sa.Text(), nullable=False),
        sa.Column("width", sa.Float()), sa.Column("height", sa.Float()),
        sa.Column("classification_json", sa.JSON()), sa.Column("ocr_spans_json", sa.JSON()),
        sa.Column("ocr_confidence", sa.Float()), sa.Column("quality_score", sa.Float()),
        sa.Column("quality_status", sa.String(32), nullable=False, server_default="good"),
        sa.Column("warnings_json", sa.JSON()), sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "page_num", name="uq_document_page_number"),
    )
    op.create_index("ix_document_page_document_id", "document_page", ["document_id"])
    op.create_index("ix_document_page_page_type", "document_page", ["page_type"])
    op.create_index("ix_document_page_quality_status", "document_page", ["quality_status"])

    for table_name, clean in (("document_raw_block", False), ("document_clean_block", True)):
        columns = [
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("document_id", sa.BigInteger(), nullable=False),
        ]
        if clean:
            columns.append(sa.Column("raw_block_id", sa.BigInteger()))
        columns += [
            sa.Column("page_num", sa.Integer(), nullable=False),
            sa.Column("block_id", sa.String(96), nullable=False),
            sa.Column("block_type", sa.String(32), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("bbox_json", sa.JSON()),
        ]
        if clean:
            columns.append(sa.Column("section_path_json", sa.JSON()))
        else:
            columns.append(sa.Column("spans_json", sa.JSON()))
        columns += [
            sa.Column("reading_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("extraction_method", sa.String(32), nullable=False),
        ]
        if not clean:
            columns.append(sa.Column("confidence", sa.Float()))
        columns += [sa.Column("metadata_json", sa.JSON()), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now())]
        columns.append(sa.UniqueConstraint("document_id", "block_id", name=f"uq_{table_name}"))
        op.create_table(table_name, *columns)
        op.create_index(f"ix_{table_name}_document_id", table_name, ["document_id"])
        op.create_index(f"ix_{table_name}_page_num", table_name, ["page_num"])
        if clean:
            op.create_index("ix_document_clean_block_raw_block_id", table_name, ["raw_block_id"])
            op.create_index("ix_document_clean_block_block_type", table_name, ["block_type"])

    op.create_table(
        "document_table",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.BigInteger(), nullable=False), sa.Column("table_id", sa.String(96), nullable=False),
        sa.Column("title", sa.String(500)), sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False), sa.Column("section_path_json", sa.JSON()),
        sa.Column("headers_json", sa.JSON()), sa.Column("rows_json", sa.JSON()), sa.Column("units_json", sa.JSON()),
        sa.Column("footnotes_json", sa.JSON()), sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("bbox_json", sa.JSON()), sa.Column("extraction_method", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "table_id", name="uq_document_table"),
    )
    op.create_index("ix_document_table_document_id", "document_table", ["document_id"])

    op.create_table(
        "document_quality_report",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("report_json", sa.JSON(), nullable=False), sa.Column("overall_quality", sa.String(32), nullable=False),
        sa.Column("average_ocr_confidence", sa.Float()), sa.Column("low_quality_pages_json", sa.JSON()),
        sa.Column("warnings_json", sa.JSON()), sa.Column("reviewed_by", sa.BigInteger()),
        sa.Column("review_status", sa.String(32), nullable=False, server_default="not_required"),
        sa.Column("review_comment", sa.Text()), sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_document_quality_report_document_id", "document_quality_report", ["document_id"], unique=True)
    op.create_index("ix_document_quality_report_overall_quality", "document_quality_report", ["overall_quality"])
    op.create_index("ix_document_quality_report_review_status", "document_quality_report", ["review_status"])

    op.create_table(
        "document_cleaning_action",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.BigInteger(), nullable=False), sa.Column("page_num", sa.Integer(), nullable=False),
        sa.Column("block_id", sa.String(96), nullable=False), sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False), sa.Column("cleaned_text", sa.Text(), nullable=False),
        sa.Column("rule", sa.String(255), nullable=False), sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    for name in ("document_id", "page_num", "block_id", "action_type"):
        op.create_index(f"ix_document_cleaning_action_{name}", "document_cleaning_action", [name])

    op.create_table(
        "tool_registry",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(96), nullable=False), sa.Column("version", sa.String(32), nullable=False),
        sa.Column("category", sa.String(32), nullable=False), sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("gray_percentage", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("name", "version", name="uq_tool_registry_name_version"),
    )
    op.create_index("ix_tool_registry_name", "tool_registry", ["name"])
    op.create_index("ix_tool_registry_category", "tool_registry", ["category"])
    op.create_index("ix_tool_registry_enabled", "tool_registry", ["enabled"])

    op.create_table(
        "tool_call",
        sa.Column("tool_call_id", sa.String(64), primary_key=True), sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("thread_id", sa.String(64), nullable=False), sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(96), nullable=False), sa.Column("tool_version", sa.String(32), nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False), sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False), sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"), sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    for name in ("request_id", "thread_id", "agent_name", "tool_name", "arguments_hash", "user_id", "tenant_id", "status"):
        op.create_index(f"ix_tool_call_{name}", "tool_call", [name])

    op.create_table(
        "tool_health",
        sa.Column("tool_name", sa.String(96), primary_key=True), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_success_at", sa.DateTime()), sa.Column("error_rate_5m", sa.Float(), nullable=False, server_default="0"),
        sa.Column("p95_latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("circuit_state", sa.String(16), nullable=False, server_default="closed"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_tool_health_status", "tool_health", ["status"])

    op.create_table(
        "tool_error",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tool_call_id", sa.String(64), nullable=False), sa.Column("tool_name", sa.String(96), nullable=False),
        sa.Column("code", sa.String(64), nullable=False), sa.Column("message", sa.Text(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("details_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    for name in ("tool_call_id", "tool_name", "code"):
        op.create_index(f"ix_tool_error_{name}", "tool_error", [name])

    op.create_table(
        "tool_policy_audit",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(64), nullable=False), sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(96), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text(), nullable=False), sa.Column("context_summary_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    for name in ("request_id", "agent_name", "tool_name"):
        op.create_index(f"ix_tool_policy_audit_{name}", "tool_policy_audit", [name])


def downgrade(database: str = "postgres") -> None:
    if database == "postgres":
        op.drop_index("ix_document_chunk_quality_status", table_name="document_chunk")
        op.drop_index("ix_document_chunk_content_type", table_name="document_chunk")
        for name in ("quality_status", "ocr_confidence", "extraction_method", "cleaning_version", "content_type", "source_block_ids"):
            op.drop_column("document_chunk", name)
        return

    for table in (
        "tool_policy_audit", "tool_error", "tool_health", "tool_call", "tool_registry",
        "document_cleaning_action", "document_quality_report", "document_table",
        "document_clean_block", "document_raw_block", "document_page",
    ):
        op.drop_table(table)
    for name in ("supersedes_document_id", "version_status", "document_version", "quality_status", "cleaning_version", "normalized_text_sha256"):
        op.drop_column("document", name)
