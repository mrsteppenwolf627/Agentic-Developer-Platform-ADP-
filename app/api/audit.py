"""Audit log endpoints (FASE 4.3).

GET /audit       — authenticated user's own action log (paginated, newest first)
GET /audit/all   — admin-only full log with optional user_id filter
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.security import get_current_user, require_role
from app.models.schemas import User, UserAction, UserActionResponse, UserRole

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=List[UserActionResponse])
async def get_my_audit_log(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[UserActionResponse]:
    result = await db.execute(
        select(UserAction)
        .where(UserAction.user_id == current_user.id)
        .order_by(UserAction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/all", response_model=List[UserActionResponse])
async def get_all_audit_log(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: Optional[uuid.UUID] = Query(None),
    current_user: User = Depends(require_role([UserRole.admin])),
    db: AsyncSession = Depends(get_db),
) -> List[UserActionResponse]:
    query = select(UserAction).order_by(UserAction.created_at.desc())
    if user_id is not None:
        query = query.where(UserAction.user_id == user_id)
    result = await db.execute(query.limit(limit).offset(offset))
    return result.scalars().all()
