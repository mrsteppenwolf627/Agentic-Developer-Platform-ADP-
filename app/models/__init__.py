"""ORM models and Pydantic schemas — public API for app.models package."""

# SQLAlchemy Base (needed by alembic env.py)
from app.models.schemas import Base

# ORM Models
from app.models.schemas import (
    Ticket,
    Task,
    Evaluation,
    RollbackStack,
    Adr,
    AgentSession,
    User,
)

# Python Enums
from app.models.schemas import (
    TicketStatus,
    TicketPriority,
    AgentModel,
    TaskStatus,
    EvaluationType,
    EvaluationModel,
    RollbackState,
    AdrStatus,
    SessionStatus,
    UserRole,
)

# Pydantic Schemas — Tickets
from app.models.schemas import (
    TicketBase,
    TicketCreate,
    TicketUpdate,
    TicketResponse,
)

# Pydantic Schemas — Tasks
from app.models.schemas import (
    TaskBase,
    TaskCreate,
    TaskUpdate,
    TaskResponse,
)

# Pydantic Schemas — Evaluations
from app.models.schemas import (
    EvaluationBase,
    EvaluationCreate,
    EvaluationResponse,
)

# Pydantic Schemas — Rollback Stack
from app.models.schemas import (
    RollbackStackBase,
    RollbackStackCreate,
    RollbackStackUpdate,
    RollbackStackResponse,
)

# Pydantic Schemas — ADRs
from app.models.schemas import (
    AdrBase,
    AdrCreate,
    AdrUpdate,
    AdrResponse,
)

# Pydantic Schemas — Agent Sessions
from app.models.schemas import (
    AgentSessionBase,
    AgentSessionCreate,
    AgentSessionUpdate,
    AgentSessionResponse,
)

# Pydantic Schemas — User
from app.models.schemas import (
    UserCreate,
    UserLogin,
    UserResponse,
    UserInDB,
)

__all__ = [
    # Base
    "Base",
    # ORM Models
    "Ticket", "Task", "Evaluation", "RollbackStack", "Adr", "AgentSession", "User",
    # Enums
    "TicketStatus", "TicketPriority", "AgentModel", "TaskStatus",
    "EvaluationType", "EvaluationModel", "RollbackState", "AdrStatus", "SessionStatus",
    "UserRole",
    # Pydantic — Ticket
    "TicketBase", "TicketCreate", "TicketUpdate", "TicketResponse",
    # Pydantic — Task
    "TaskBase", "TaskCreate", "TaskUpdate", "TaskResponse",
    # Pydantic — Evaluation
    "EvaluationBase", "EvaluationCreate", "EvaluationResponse",
    # Pydantic — Rollback
    "RollbackStackBase", "RollbackStackCreate", "RollbackStackUpdate", "RollbackStackResponse",
    # Pydantic — ADR
    "AdrBase", "AdrCreate", "AdrUpdate", "AdrResponse",
    # Pydantic — AgentSession
    "AgentSessionBase", "AgentSessionCreate", "AgentSessionUpdate", "AgentSessionResponse",
    # Pydantic — User
    "UserCreate", "UserLogin", "UserResponse", "UserInDB",
]
