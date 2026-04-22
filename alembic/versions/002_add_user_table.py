"""Add users table with bcrypt password hash and role enum (PRE-4.0)

Revision ID: 002
Revises: 001
Create Date: 2026-04-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Create user_role ENUM
    postgresql.ENUM(
        "admin", "developer", "user",
        name="user_role",
    ).create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("admin", "developer", "user", name="user_role", create_type=False),
            nullable=False,
            server_default="user",
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_is_active", "users", ["is_active"])

    op.execute("""
        CREATE TRIGGER trg_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    bind = op.get_bind()

    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users;")
    op.drop_table("users")
    sa.Enum(name="user_role").drop(bind, checkfirst=True)
