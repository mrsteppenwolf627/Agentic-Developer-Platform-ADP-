"""SQLAlchemy 2.0 ORM models and Pydantic v2 schemas for ADP.

Structure:
  1. Python enums (source of truth for ENUM columns)
  2. SQLAlchemy Base + ORM models
  3. Pydantic schemas (Base / Create / Update / Response per entity)

ADR compliance:
  - ADR-001: UUID PKs via gen_random_uuid(), JSONB for structured data
  - ADR-002: agent_model ENUM {gemini, claude, codex}
  - ADR-003: evaluations mandatory, score in [0.0, 1.0]
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSON, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ===========================================================================
# 1. Python Enums
# ===========================================================================

class TicketStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TicketPriority(str, enum.Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class AgentModel(str, enum.Enum):
    gemini = "gemini"
    claude = "claude"
    codex = "codex"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


class EvaluationType(str, enum.Enum):
    security = "security"
    quality = "quality"
    performance = "performance"
    compliance = "compliance"
    functional = "functional"


class EvaluationModel(str, enum.Enum):
    codex = "codex"
    claude = "claude"
    gemini = "gemini"
    braintrust = "braintrust"


class RollbackState(str, enum.Enum):
    active = "active"
    rolled_back = "rolled_back"
    superseded = "superseded"


class AdrStatus(str, enum.Enum):
    proposed = "proposed"
    accepted = "accepted"
    deprecated = "deprecated"
    superseded = "superseded"


class SessionStatus(str, enum.Enum):
    started = "started"
    completed = "completed"
    failed = "failed"
    timeout = "timeout"


# ===========================================================================
# 2. SQLAlchemy Base
# ===========================================================================

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Helper: reusable SA Enum factory (references existing DB type, no create)
# ---------------------------------------------------------------------------

def _sa_enum(enum_cls: type, pg_name: str) -> sa.Enum:
    return sa.Enum(
        enum_cls,
        name=pg_name,
        create_constraint=False,
        native_enum=True,
    )


# ===========================================================================
# 3. ORM Models
# ===========================================================================

class Ticket(Base):
    """Root entity. Represents a unit of work from the backlog/CRM."""
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[TicketStatus] = mapped_column(
        _sa_enum(TicketStatus, "ticket_status"),
        nullable=False,
        server_default="pending",
        index=True,
    )
    priority: Mapped[TicketPriority] = mapped_column(
        _sa_enum(TicketPriority, "ticket_priority"),
        nullable=False,
        server_default="P2",
        index=True,
    )
    # JSON list of model names required: ["claude", "codex"]
    required_models: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    # JSONB snapshot of CONTEXT.md state at ticket creation
    context_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.text("NOW()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.text("NOW()"),
        nullable=False,
    )

    tasks: Mapped[List["Task"]] = relationship(
        "Task", back_populates="ticket", cascade="all, delete-orphan"
    )


class Task(Base):
    """Decomposed unit of work assigned to a specific agent model."""
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_model: Mapped[AgentModel] = mapped_column(
        _sa_enum(AgentModel, "agent_model"),
        nullable=False,
        index=True,
    )
    status: Mapped[TaskStatus] = mapped_column(
        _sa_enum(TaskStatus, "task_status"),
        nullable=False,
        server_default="pending",
        index=True,
    )
    # ARRAY of UUIDs for tasks that must complete before this task starts
    dependencies: Mapped[Optional[List[uuid.UUID]]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        server_default="{}",
    )
    prompt_sent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSONB: {steps: [...], errors: [...], timing: {start, end, duration_ms}}
    execution_log: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.text("NOW()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.text("NOW()"),
        nullable=False,
    )

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="tasks")
    evaluations: Mapped[List["Evaluation"]] = relationship(
        "Evaluation", back_populates="task", cascade="all, delete-orphan"
    )
    rollback_entries: Mapped[List["RollbackStack"]] = relationship(
        "RollbackStack", back_populates="task", cascade="all, delete-orphan"
    )
    agent_sessions: Mapped[List["AgentSession"]] = relationship(
        "AgentSession", back_populates="task", cascade="all, delete-orphan"
    )


class Evaluation(Base):
    """Governance gate output. Required before task can be marked completed (ADR-003)."""
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluation_type: Mapped[EvaluationType] = mapped_column(
        _sa_enum(EvaluationType, "evaluation_type"),
        nullable=False,
        index=True,
    )
    # Score in [0.0, 1.0] — ADR-003 mandates float, not percentage
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # JSONB: {issues: [{severity, description, line}], recommendations: [], raw_output: ""}
    findings: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    passed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=sa.text("false"),
        index=True,
    )
    evaluated_by: Mapped[EvaluationModel] = mapped_column(
        _sa_enum(EvaluationModel, "evaluation_model"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.text("NOW()"),
        nullable=False,
    )

    task: Mapped["Task"] = relationship("Task", back_populates="evaluations")


class RollbackStack(Base):
    """Context snapshot stack for automatic recovery on task failure."""
    __tablename__ = "rollback_stack"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    context_md_before: Mapped[str] = mapped_column(Text, nullable=False)
    context_md_after: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    git_commit_hash: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    state: Mapped[RollbackState] = mapped_column(
        _sa_enum(RollbackState, "rollback_state"),
        nullable=False,
        server_default="active",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.text("NOW()"),
        nullable=False,
    )

    task: Mapped["Task"] = relationship("Task", back_populates="rollback_entries")


class Adr(Base):
    """Frozen architectural decisions. INT PK by ADR numbering convention."""
    __tablename__ = "adrs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[AdrStatus] = mapped_column(
        _sa_enum(AdrStatus, "adr_status"),
        nullable=False,
        server_default="proposed",
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    impact_area: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.text("NOW()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.text("NOW()"),
        nullable=False,
    )


class AgentSession(Base):
    """Audit log for every LLM invocation. Required per ADR-002."""
    __tablename__ = "agent_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_used: Mapped[AgentModel] = mapped_column(
        _sa_enum(AgentModel, "agent_model"),
        nullable=False,
        index=True,
    )
    model_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[SessionStatus] = mapped_column(
        _sa_enum(SessionStatus, "session_status"),
        nullable=False,
        server_default="started",
        index=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.text("NOW()"),
        nullable=False,
    )

    task: Mapped["Task"] = relationship("Task", back_populates="agent_sessions")


# ===========================================================================
# 4. Pydantic Schemas
# ===========================================================================

_ORM_CONFIG = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Ticket schemas
# ---------------------------------------------------------------------------

class TicketBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: TicketStatus = TicketStatus.pending
    priority: TicketPriority = TicketPriority.P2
    required_models: Optional[List[AgentModel]] = None
    context_snapshot: Optional[Dict[str, Any]] = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title cannot be blank")
        return normalized


class TicketCreate(TicketBase):
    pass


class TicketUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    required_models: Optional[List[AgentModel]] = None
    context_snapshot: Optional[Dict[str, Any]] = None


class TicketResponse(TicketBase):
    model_config = _ORM_CONFIG

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Task schemas
# ---------------------------------------------------------------------------

class TaskBase(BaseModel):
    ticket_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    assigned_model: AgentModel
    status: TaskStatus = TaskStatus.pending
    dependencies: Optional[List[uuid.UUID]] = Field(default_factory=list)
    prompt_sent: Optional[str] = None
    output: Optional[str] = None
    execution_log: Optional[Dict[str, Any]] = None


class TaskCreate(BaseModel):
    ticket_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    assigned_model: AgentModel
    dependencies: Optional[List[uuid.UUID]] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    status: Optional[TaskStatus] = None
    prompt_sent: Optional[str] = None
    output: Optional[str] = None
    execution_log: Optional[Dict[str, Any]] = None
    # assigned_model is IMMUTABLE per ADR-002 — intentionally excluded

    @field_validator("output")
    @classmethod
    def validate_output(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("output cannot be blank when provided")
        return normalized


class TaskResponse(TaskBase):
    model_config = _ORM_CONFIG

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Evaluation schemas
# ---------------------------------------------------------------------------

class EvaluationBase(BaseModel):
    task_id: uuid.UUID
    evaluation_type: EvaluationType
    evaluated_by: EvaluationModel
    score: Optional[float] = Field(None, ge=0.0, le=1.0)
    findings: Optional[Dict[str, Any]] = None
    passed: bool = False

    @field_validator("score")
    @classmethod
    def score_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError("score must be in [0.0, 1.0] — ADR-003")
        return v


class EvaluationCreate(EvaluationBase):
    pass


class EvaluationResponse(EvaluationBase):
    model_config = _ORM_CONFIG

    id: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# RollbackStack schemas
# ---------------------------------------------------------------------------

class RollbackStackBase(BaseModel):
    task_id: uuid.UUID
    context_md_before: str
    context_md_after: Optional[str] = None
    git_commit_hash: Optional[str] = Field(None, max_length=40)
    state: RollbackState = RollbackState.active


class RollbackStackCreate(BaseModel):
    task_id: uuid.UUID
    context_md_before: str
    git_commit_hash: Optional[str] = Field(None, max_length=40)


class RollbackStackUpdate(BaseModel):
    context_md_after: Optional[str] = None
    state: Optional[RollbackState] = None


class RollbackStackResponse(RollbackStackBase):
    model_config = _ORM_CONFIG

    id: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# ADR schemas
# ---------------------------------------------------------------------------

class AdrBase(BaseModel):
    id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=255)
    status: AdrStatus = AdrStatus.proposed
    content: str
    impact_area: Optional[str] = Field(None, max_length=255)
    approved_by: Optional[str] = Field(None, max_length=255)


class AdrCreate(AdrBase):
    pass


class AdrUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[AdrStatus] = None
    content: Optional[str] = None
    impact_area: Optional[str] = Field(None, max_length=255)
    approved_by: Optional[str] = Field(None, max_length=255)


class AdrResponse(AdrBase):
    model_config = _ORM_CONFIG

    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# AgentSession schemas
# ---------------------------------------------------------------------------

class AgentSessionBase(BaseModel):
    task_id: uuid.UUID
    model_used: AgentModel
    model_version: Optional[str] = Field(None, max_length=100)
    tokens_used: Optional[int] = Field(None, ge=0)
    latency_ms: Optional[int] = Field(None, ge=0)
    status: SessionStatus = SessionStatus.started
    error_message: Optional[str] = None


class AgentSessionCreate(BaseModel):
    task_id: uuid.UUID
    model_used: AgentModel
    model_version: Optional[str] = Field(None, max_length=100)


class AgentSessionUpdate(BaseModel):
    tokens_used: Optional[int] = Field(None, ge=0)
    latency_ms: Optional[int] = Field(None, ge=0)
    status: Optional[SessionStatus] = None
    error_message: Optional[str] = None


class AgentSessionResponse(AgentSessionBase):
    model_config = _ORM_CONFIG

    id: uuid.UUID
    created_at: datetime
