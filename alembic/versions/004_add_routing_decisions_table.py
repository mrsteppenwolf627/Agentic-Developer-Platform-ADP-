"""Add routing_decisions table for SmartRouter FASE 5.

Revision ID: 004
Revises: 003
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "routing_decisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("chosen_model", sa.String(length=100), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_routing_decisions_task_id", "routing_decisions", ["task_id"])
    op.create_index("ix_routing_decisions_task_type", "routing_decisions", ["task_type"])
    op.create_index("ix_routing_decisions_chosen_model", "routing_decisions", ["chosen_model"])
    op.create_index("ix_routing_decisions_created_at", "routing_decisions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_routing_decisions_created_at", table_name="routing_decisions")
    op.drop_index("ix_routing_decisions_chosen_model", table_name="routing_decisions")
    op.drop_index("ix_routing_decisions_task_type", table_name="routing_decisions")
    op.drop_index("ix_routing_decisions_task_id", table_name="routing_decisions")
    op.drop_table("routing_decisions")
