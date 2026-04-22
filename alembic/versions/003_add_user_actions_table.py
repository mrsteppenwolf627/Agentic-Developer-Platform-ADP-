"""Add user_actions audit table (FASE 4.3)

Revision ID: 003
Revises: 002
Create Date: 2026-04-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_actions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("request_body", postgresql.JSONB, nullable=True),
        sa.Column("response_body", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_index("ix_user_actions_user_id", "user_actions", ["user_id"])
    op.create_index("ix_user_actions_method", "user_actions", ["method"])
    op.create_index("ix_user_actions_status_code", "user_actions", ["status_code"])
    op.create_index("ix_user_actions_created_at", "user_actions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_actions_created_at", table_name="user_actions")
    op.drop_index("ix_user_actions_status_code", table_name="user_actions")
    op.drop_index("ix_user_actions_method", table_name="user_actions")
    op.drop_index("ix_user_actions_user_id", table_name="user_actions")
    op.drop_table("user_actions")
