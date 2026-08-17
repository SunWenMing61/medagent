"""Repair the Agent trace schema used by the chat workflow.

Revision ID: 0008_agent_step_cost_usd
Revises: 0007_pairwise_answer_preferences
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_agent_step_cost_usd"
down_revision = "0007_pairwise_answer_preferences"
branch_labels = None
depends_on = None


def upgrade(database: str = "postgres") -> None:
    if database == "postgres":
        return

    # Some deployed databases created agent_step from an older form of 0004
    # that did not contain cost_usd.  Fresh databases already have the column,
    # so keep this repair migration safe for both histories.
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("agent_step")}
    if "cost_usd" not in columns:
        op.add_column(
            "agent_step",
            sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        )


def downgrade(database: str = "postgres") -> None:
    # 0004 defines cost_usd as part of the base Agent trace contract.  Removing
    # it while downgrading only this repair would recreate the broken schema.
    return
