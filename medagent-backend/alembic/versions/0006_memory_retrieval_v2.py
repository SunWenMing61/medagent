"""Layered Agent Memory, restart checkpoints and ACL-first retrieval metadata.

Revision ID: 0006_memory_retrieval_v2
Revises: 0005_pdf_tooling_v2
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_memory_retrieval_v2"
down_revision = "0005_pdf_tooling_v2"
branch_labels = None
depends_on = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    ]


def upgrade(database: str = "postgres") -> None:
    if database == "postgres":
        for column in (
            sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
            sa.Column("title", sa.String(500)), sa.Column("section_title", sa.String(500)),
            sa.Column("embedding_version", sa.String(64)), sa.Column("embedded_at", sa.DateTime()),
            sa.Column("medical_entities", postgresql.JSONB()), sa.Column("normalized_drug_names", postgresql.JSONB()),
            sa.Column("disease_names", postgresql.JSONB()), sa.Column("medical_codes", postgresql.JSONB()),
            sa.Column("keywords", postgresql.JSONB()),
            sa.Column("source_type", sa.String(32), nullable=False, server_default="local_knowledge_base"),
            sa.Column("authority_level", sa.Integer(), nullable=False, server_default="7"),
            sa.Column("document_version", sa.String(64)), sa.Column("publication_date", sa.DateTime()),
        ):
            op.add_column("document_chunk", column)
        op.create_index("ix_document_chunk_acl_route", "document_chunk", ["tenant_id", "kb_id", "chunk_type"])
        op.create_index("ix_document_chunk_embedding_version", "document_chunk", ["embedding_version"])
        op.create_index("ix_document_chunk_document_version", "document_chunk", ["document_version"])
        op.create_index("ix_document_chunk_source_type", "document_chunk", ["source_type"])
        op.execute("CREATE INDEX ix_document_chunk_medical_entities_gin ON document_chunk USING gin (medical_entities)")
        op.execute("CREATE INDEX ix_document_chunk_medical_codes_gin ON document_chunk USING gin (medical_codes)")
        op.execute("CREATE INDEX ix_document_chunk_keywords_gin ON document_chunk USING gin (keywords)")
        # The base schema permits multiple vector dimensions, so index the configured
        # 1024-dimensional production partition explicitly instead of creating an
        # invalid HNSW index on an unbounded vector column.
        op.execute("CREATE INDEX ix_document_chunk_embedding_hnsw ON document_chunk USING hnsw ((embedding::vector(1024)) vector_cosine_ops) WHERE embedding IS NOT NULL AND embedding_dimensions = 1024")
        op.create_table(
            "agent_workflow_checkpoint",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("request_id", sa.String(64), nullable=False), sa.Column("thread_id", sa.String(128), nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False), sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("node_name", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False), sa.Column("state_version", sa.String(32), nullable=False),
            sa.Column("state_json", sa.JSON(), nullable=False), sa.Column("expires_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("request_id", "sequence", name="uq_workflow_checkpoint_sequence"),
        )
        op.create_index("ix_workflow_checkpoint_thread", "agent_workflow_checkpoint", ["tenant_id", "user_id", "thread_id", "sequence"])
        op.create_index("ix_agent_workflow_checkpoint_request_id", "agent_workflow_checkpoint", ["request_id"])
        op.create_index("ix_agent_workflow_checkpoint_expires_at", "agent_workflow_checkpoint", ["expires_at"])
        return

    op.create_table(
        "agent_session", sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False), sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("thread_id", sa.String(128), nullable=False), sa.Column("recent_messages_json", sa.JSON(), nullable=False),
        sa.Column("rolling_summary", sa.Text(), nullable=False), sa.Column("active_topic", sa.String(500)),
        sa.Column("active_entities_json", sa.JSON(), nullable=False), sa.Column("unresolved_questions_json", sa.JSON(), nullable=False),
        sa.Column("confirmed_constraints_json", sa.JSON(), nullable=False), sa.Column("latest_corrections_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"), *_timestamps(),
        sa.UniqueConstraint("tenant_id", "user_id", "thread_id", name="uq_agent_session_namespace"),
    )
    op.create_index("ix_agent_session_owner_status", "agent_session", ["tenant_id", "user_id", "status"])

    op.create_table(
        "agent_memory", sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False), sa.Column("user_id", sa.BigInteger()),
        sa.Column("agent_name", sa.String(128)), sa.Column("namespace", sa.String(500), nullable=False),
        sa.Column("memory_type", sa.String(32), nullable=False), sa.Column("category", sa.String(64), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False), sa.Column("predicate", sa.String(255), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False), sa.Column("searchable_text", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False), sa.Column("source_message_ids_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"), sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("sensitivity", sa.String(32), nullable=False, server_default="normal"), sa.Column("trust_level", sa.String(16), nullable=False, server_default="high"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"), sa.Column("valid_from", sa.DateTime()),
        sa.Column("valid_to", sa.DateTime()), sa.Column("expires_at", sa.DateTime()), sa.Column("embedding_json", sa.JSON()),
        sa.Column("embedding_model", sa.String(128)), sa.Column("embedding_dimension", sa.Integer()), sa.Column("embedding_version", sa.String(32)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("can_support_medical_claim", sa.Boolean(), nullable=False, server_default=sa.false()), *_timestamps(),
    )
    op.create_index("ix_agent_memory_owner", "agent_memory", ["tenant_id", "user_id", "memory_type", "status"])
    op.create_index("ix_agent_memory_agent", "agent_memory", ["tenant_id", "agent_name", "memory_type", "status"])
    op.create_index("ix_agent_memory_fact", "agent_memory", ["tenant_id", "user_id", "subject", "predicate", "status"])
    op.create_index("ix_agent_memory_namespace", "agent_memory", ["namespace"])
    op.create_index("ix_agent_memory_expires_at", "agent_memory", ["expires_at"])

    op.create_table(
        "agent_episode", sa.Column("id", sa.String(64), primary_key=True), sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger()), sa.Column("thread_id", sa.String(128)), sa.Column("request_id", sa.String(128)),
        sa.Column("event_type", sa.String(64), nullable=False), sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("situation_summary", sa.Text(), nullable=False), sa.Column("action_summary", sa.Text(), nullable=False),
        sa.Column("outcome_summary", sa.Text(), nullable=False), sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("quality_score", sa.Float()), sa.Column("related_entities_json", sa.JSON(), nullable=False),
        sa.Column("source_run_ids_json", sa.JSON(), nullable=False), sa.Column("reusable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime()), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_episode_scope", "agent_episode", ["tenant_id", "user_id", "event_type", "reusable"])

    op.create_table(
        "agent_procedure", sa.Column("id", sa.String(64), primary_key=True), sa.Column("tenant_id", sa.BigInteger()),
        sa.Column("scope", sa.String(32), nullable=False), sa.Column("agent_name", sa.String(128)),
        sa.Column("task_type", sa.String(64), nullable=False), sa.Column("trigger_conditions_json", sa.JSON(), nullable=False),
        sa.Column("recommended_steps_json", sa.JSON(), nullable=False), sa.Column("prohibited_actions_json", sa.JSON(), nullable=False),
        sa.Column("required_tools_json", sa.JSON(), nullable=False), sa.Column("fallback_strategy_json", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False), sa.Column("evaluation_score", sa.Float()),
        sa.Column("version", sa.String(32), nullable=False), sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("approved_by", sa.BigInteger()), *_timestamps(),
    )
    op.create_index("ix_agent_procedure_route", "agent_procedure", ["tenant_id", "agent_name", "task_type", "status"])

    op.create_table(
        "agent_memory_audit", sa.Column("id", sa.String(64), primary_key=True), sa.Column("memory_id", sa.String(64)),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False), sa.Column("user_id", sa.BigInteger()),
        sa.Column("operation", sa.String(32), nullable=False), sa.Column("operator_type", sa.String(32), nullable=False),
        sa.Column("operator_id", sa.String(128)), sa.Column("before_value_json", sa.JSON()), sa.Column("after_value_json", sa.JSON()),
        sa.Column("reason", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_memory_audit_owner", "agent_memory_audit", ["tenant_id", "user_id", "created_at"])
    op.create_index("ix_agent_memory_audit_memory_id", "agent_memory_audit", ["memory_id"])

    op.create_table(
        "user_memory_setting", sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False), sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("long_term_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("medical_sensitive_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_user_memory_setting_owner"),
    )

    op.create_table(
        "memory_retrieval_trace", sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("request_id", sa.String(128), nullable=False), sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False), sa.Column("agent_name", sa.String(128), nullable=False),
        sa.Column("memory_types_json", sa.JSON(), nullable=False), sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False), sa.Column("selected_count", sa.Integer(), nullable=False),
        sa.Column("memory_tokens", sa.Integer(), nullable=False), sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_memory_retrieval_trace_request_id", "memory_retrieval_trace", ["request_id"])

    op.create_table(
        "retrieval_trace", sa.Column("request_id", sa.String(128), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False), sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("original_query_hash", sa.String(64), nullable=False), sa.Column("standalone_query", sa.Text(), nullable=False),
        sa.Column("routes_json", sa.JSON(), nullable=False), sa.Column("entities_json", sa.JSON(), nullable=False),
        sa.Column("constraints_json", sa.JSON(), nullable=False), sa.Column("rankings_json", sa.JSON(), nullable=False),
        sa.Column("filtered_json", sa.JSON(), nullable=False), sa.Column("final_evidence_json", sa.JSON(), nullable=False),
        sa.Column("timings_json", sa.JSON(), nullable=False), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_json", sa.JSON()), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_retrieval_trace_owner", "retrieval_trace", ["tenant_id", "user_id", "created_at"])
    op.create_index("ix_retrieval_trace_status", "retrieval_trace", ["status"])


def downgrade(database: str = "postgres") -> None:
    if database == "postgres":
        op.drop_table("agent_workflow_checkpoint")
        for name in (
            "ix_document_chunk_embedding_hnsw", "ix_document_chunk_keywords_gin",
            "ix_document_chunk_medical_codes_gin", "ix_document_chunk_medical_entities_gin",
            "ix_document_chunk_source_type", "ix_document_chunk_document_version",
            "ix_document_chunk_embedding_version", "ix_document_chunk_acl_route",
        ):
            op.execute(f"DROP INDEX IF EXISTS {name}")
        for name in (
            "publication_date", "document_version", "authority_level", "source_type", "keywords",
            "medical_codes", "disease_names", "normalized_drug_names", "medical_entities",
            "embedded_at", "embedding_version", "section_title", "title", "tenant_id",
        ):
            op.drop_column("document_chunk", name)
        return
    for table in (
        "retrieval_trace", "memory_retrieval_trace", "user_memory_setting", "agent_memory_audit",
        "agent_procedure", "agent_episode", "agent_memory", "agent_session",
    ):
        op.drop_table(table)
