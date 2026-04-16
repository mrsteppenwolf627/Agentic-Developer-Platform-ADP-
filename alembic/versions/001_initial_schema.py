"""Initial schema: tickets, tasks, evaluations, rollback_stack, adrs, agent_sessions

Revision ID: 001
Revises: (none — first migration)
Create Date: 2026-04-16

ADR refs:
  - ADR-001: PostgreSQL + SQLAlchemy 2.0 + Alembic (accepted)
  - ADR-002: agent_model ENUM {gemini, claude, codex} (accepted)
  - ADR-003: evaluations mandatory gate, findings JSONB (accepted)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def _drop_enum(bind, name: str) -> None:
    sa.Enum(name=name).drop(bind, checkfirst=True)


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Create ENUM types (PostgreSQL native, shared across tables)
    # ------------------------------------------------------------------
    postgresql.ENUM(
        "pending", "in_progress", "completed", "failed", "cancelled",
        name="ticket_status",
    ).create(bind, checkfirst=True)

    postgresql.ENUM(
        "P0", "P1", "P2", "P3",
        name="ticket_priority",
    ).create(bind, checkfirst=True)

    postgresql.ENUM(
        "gemini", "claude", "codex",
        name="agent_model",
    ).create(bind, checkfirst=True)

    postgresql.ENUM(
        "pending", "in_progress", "completed", "failed",
        name="task_status",
    ).create(bind, checkfirst=True)

    postgresql.ENUM(
        "security", "quality", "performance", "compliance", "functional",
        name="evaluation_type",
    ).create(bind, checkfirst=True)

    postgresql.ENUM(
        "codex", "claude", "gemini", "braintrust",
        name="evaluation_model",
    ).create(bind, checkfirst=True)

    postgresql.ENUM(
        "active", "rolled_back", "superseded",
        name="rollback_state",
    ).create(bind, checkfirst=True)

    postgresql.ENUM(
        "proposed", "accepted", "deprecated", "superseded",
        name="adr_status",
    ).create(bind, checkfirst=True)

    postgresql.ENUM(
        "started", "completed", "failed", "timeout",
        name="session_status",
    ).create(bind, checkfirst=True)

    # ------------------------------------------------------------------
    # 2. updated_at trigger function (applied to tickets, tasks, adrs)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ------------------------------------------------------------------
    # 3. tickets — root entity, source of all work
    # ------------------------------------------------------------------
    op.create_table(
        "tickets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "status",
            _create_enum("ticket_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "priority",
            _create_enum("ticket_priority"),
            nullable=False,
            server_default="P2",
        ),
        # JSON: list of model names required, e.g. ["claude", "codex"]
        sa.Column("required_models", postgresql.JSON, nullable=True),
        # JSONB: full snapshot of CONTEXT.md at ticket creation time
        sa.Column("context_snapshot", postgresql.JSONB, nullable=True),
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
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_tickets_priority", "tickets", ["priority"])
    op.create_index("ix_tickets_created_at", "tickets", ["created_at"])
    op.execute("""
        CREATE TRIGGER trg_tickets_updated_at
        BEFORE UPDATE ON tickets
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # ------------------------------------------------------------------
    # 4. tasks — decomposed units of work derived from a ticket
    # ------------------------------------------------------------------
    op.create_table(
        "tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "assigned_model",
            _create_enum("agent_model"),
            nullable=False,
        ),
        sa.Column(
            "status",
            _create_enum("task_status"),
            nullable=False,
            server_default="pending",
        ),
        # ARRAY of UUID: task IDs that must complete before this task starts
        sa.Column(
            "dependencies",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
            server_default="{}",
        ),
        sa.Column("prompt_sent", sa.Text, nullable=True),
        sa.Column("output", sa.Text, nullable=True),
        # JSONB: structured execution log {steps: [], errors: [], timing: {}}
        sa.Column("execution_log", postgresql.JSONB, nullable=True),
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
    op.create_index("ix_tasks_ticket_id", "tasks", ["ticket_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_assigned_model", "tasks", ["assigned_model"])
    op.create_index("ix_tasks_ticket_status", "tasks", ["ticket_id", "status"])
    op.execute("""
        CREATE TRIGGER trg_tasks_updated_at
        BEFORE UPDATE ON tasks
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # ------------------------------------------------------------------
    # 5. evaluations — mandatory governance gate (ADR-003)
    # ------------------------------------------------------------------
    op.create_table(
        "evaluations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evaluation_type",
            _create_enum("evaluation_type"),
            nullable=False,
        ),
        # Score in [0.0, 1.0] float — NOT percentage (ADR-003)
        sa.Column("score", sa.Float, nullable=True),
        # JSONB: {issues: [{severity, description, line}], recommendations: [], raw_output: ""}
        sa.Column("findings", postgresql.JSONB, nullable=True),
        sa.Column(
            "passed",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "evaluated_by",
            _create_enum("evaluation_model"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_evaluations_task_id", "evaluations", ["task_id"])
    op.create_index("ix_evaluations_evaluation_type", "evaluations", ["evaluation_type"])
    op.create_index("ix_evaluations_passed", "evaluations", ["passed"])
    op.create_index(
        "ix_evaluations_task_type",
        "evaluations",
        ["task_id", "evaluation_type"],
        unique=True,
    )

    # ------------------------------------------------------------------
    # 6. rollback_stack — context snapshots for automatic recovery
    # ------------------------------------------------------------------
    op.create_table(
        "rollback_stack",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Full content of CONTEXT.md before task execution
        sa.Column("context_md_before", sa.Text, nullable=False),
        # Full content of CONTEXT.md after task execution (null if not yet applied)
        sa.Column("context_md_after", sa.Text, nullable=True),
        # SHA-1 git commit hash (40 chars)
        sa.Column("git_commit_hash", sa.String(40), nullable=True),
        sa.Column(
            "state",
            _create_enum("rollback_state"),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_rollback_stack_task_id", "rollback_stack", ["task_id"])
    op.create_index("ix_rollback_stack_state", "rollback_stack", ["state"])

    # ------------------------------------------------------------------
    # 7. adrs — frozen architectural decisions (INT PK by convention)
    # ------------------------------------------------------------------
    op.create_table(
        "adrs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column(
            "status",
            _create_enum("adr_status"),
            nullable=False,
            server_default="proposed",
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("impact_area", sa.String(255), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
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
    op.create_index("ix_adrs_status", "adrs", ["status"])
    op.execute("""
        CREATE TRIGGER trg_adrs_updated_at
        BEFORE UPDATE ON adrs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    # ------------------------------------------------------------------
    # 8. agent_sessions — audit log for every model invocation (ADR-002)
    # ------------------------------------------------------------------
    op.create_table(
        "agent_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "model_used",
            _create_enum("agent_model"),
            nullable=False,
        ),
        sa.Column("model_version", sa.String(100), nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column(
            "status",
            _create_enum("session_status"),
            nullable=False,
            server_default="started",
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_agent_sessions_task_id", "agent_sessions", ["task_id"])
    op.create_index("ix_agent_sessions_model_used", "agent_sessions", ["model_used"])
    op.create_index("ix_agent_sessions_status", "agent_sessions", ["status"])
    op.create_index(
        "ix_agent_sessions_task_model",
        "agent_sessions",
        ["task_id", "model_used"],
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    bind = op.get_bind()

    # Drop triggers first
    for tbl, trg in [
        ("adrs", "trg_adrs_updated_at"),
        ("tasks", "trg_tasks_updated_at"),
        ("tickets", "trg_tickets_updated_at"),
    ]:
        op.execute(f"DROP TRIGGER IF EXISTS {trg} ON {tbl};")

    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")

    # Drop tables in FK-safe reverse order
    op.drop_table("agent_sessions")
    op.drop_table("adrs")
    op.drop_table("rollback_stack")
    op.drop_table("evaluations")
    op.drop_table("tasks")
    op.drop_table("tickets")

    # Drop ENUM types
    for enum_name in [
        "session_status",
        "adr_status",
        "rollback_state",
        "evaluation_model",
        "evaluation_type",
        "task_status",
        "agent_model",
        "ticket_priority",
        "ticket_status",
    ]:
        _drop_enum(bind, enum_name)
