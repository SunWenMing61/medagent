"""Hybrid runtime and continuous evaluation flywheel.

Revision ID: 0011_hybrid_eval
Revises: 0010_evaluation_platform
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_hybrid_eval"
down_revision = "0010_evaluation_platform"
branch_labels = None
depends_on = None


def upgrade(database: str = "postgres") -> None:
    if database == "postgres": return
    op.create_table("eval_dataset_version", sa.Column("id", sa.String(64), primary_key=True), sa.Column("dataset_id", sa.String(64), sa.ForeignKey("eval_dataset.id", ondelete="CASCADE"), nullable=False), sa.Column("version", sa.String(64), nullable=False), sa.Column("case_count", sa.Integer(), nullable=False), sa.Column("change_summary", sa.Text()), sa.Column("snapshot_json", sa.JSON(), nullable=False), sa.Column("created_by", sa.BigInteger()), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()), sa.UniqueConstraint("dataset_id", "version", name="uq_eval_dataset_version"))
    op.create_index("ix_eval_dataset_version_dataset_id", "eval_dataset_version", ["dataset_id"])
    op.create_table("evaluation_candidate", sa.Column("id", sa.String(64), primary_key=True), sa.Column("normalized_hash", sa.String(64), nullable=False), sa.Column("query_text", sa.Text(), nullable=False), sa.Column("source_request_id", sa.String(64)), sa.Column("cluster_key", sa.String(64)), sa.Column("category", sa.String(64), nullable=False), sa.Column("difficulty", sa.String(16), nullable=False), sa.Column("status", sa.String(24), nullable=False), sa.Column("score", sa.Float(), nullable=False), sa.Column("score_breakdown", sa.JSON(), nullable=False), sa.Column("runtime_metadata", sa.JSON(), nullable=False), sa.Column("review_comment", sa.Text()), sa.Column("reviewed_by", sa.BigInteger()), sa.Column("reviewed_at", sa.DateTime()), sa.Column("target_dataset_id", sa.String(64), sa.ForeignKey("eval_dataset.id")), sa.Column("target_case_id", sa.BigInteger(), sa.ForeignKey("eval_case.id")), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    for column in ("normalized_hash", "source_request_id", "cluster_key", "category", "status", "score", "created_at"): op.create_index(f"ix_evaluation_candidate_{column}", "evaluation_candidate", [column])
    op.create_table("dataset_change_log", sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True), sa.Column("dataset_id", sa.String(64), sa.ForeignKey("eval_dataset.id", ondelete="CASCADE"), nullable=False), sa.Column("version", sa.String(64), nullable=False), sa.Column("action", sa.String(32), nullable=False), sa.Column("case_key", sa.String(128)), sa.Column("candidate_id", sa.String(64)), sa.Column("actor_id", sa.BigInteger()), sa.Column("details_json", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_dataset_change_log_dataset_id", "dataset_change_log", ["dataset_id"])


def downgrade(database: str = "postgres") -> None:
    if database == "postgres": return
    for table in ("dataset_change_log", "evaluation_candidate", "eval_dataset_version"): op.drop_table(table)
