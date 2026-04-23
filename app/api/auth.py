"""FastAPI router — /auth endpoints.

POST /auth/register          → create user (email + password)
POST /auth/login             → email/password → JWT token
GET  /auth/me                → current user info (requires valid JWT)
POST /auth/admin/users       → admin-only: create user with explicit role
"""
from __future__ import annotations

import logging
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies.security import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
    verify_refresh_token,
)
from app.models.schemas import User, UserCreate, UserLogin, UserResponse, UserRole


class UserAdminCreate(BaseModel):
    email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=255)
    role: UserRole = UserRole.user

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("Invalid email format")
        return v.lower()

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)) -> UserResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    try:
        user = User(
            email=body.email,
            password_hash=hash_password(body.password),
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    logger.info("register | new user email=%s id=%s", user.email, user.id)
    return UserResponse.model_validate(user)


@router.post("/login")
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Login endpoint.

    Returns:
    - access_token (JSON): Short-lived token (15 min) for API access.
    - user (JSON): Authenticated user data.
    - refresh_token (Cookie, HttpOnly): Long-lived token (7 days) for silent renewal.

    Security:
    - refresh_token is HttpOnly (inaccessible from JavaScript).
    - secure=True in production (HTTPS only).
    - samesite="strict" (CSRF protection).
    """
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive",
        )

    settings = get_settings()
    access_token = create_access_token(user.id, user.email)
    refresh_token_value = create_refresh_token(user.id)
    logger.info("login | user=%s id=%s", user.email, user.id)

    response = JSONResponse({
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_expiration_minutes * 60,
        "user": jsonable_encoder(UserResponse.model_validate(user)),
    })
    response.set_cookie(
        key="refresh_token",
        value=refresh_token_value,
        max_age=settings.jwt_refresh_token_expiration_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
    )
    return response


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post("/admin/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    body: UserAdminCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role([UserRole.admin])),
) -> UserResponse:
    """Admin-only endpoint to create users with an explicit role assignment."""
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    try:
        user = User(
            email=body.email,
            password_hash=hash_password(body.password),
            role=body.role,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    logger.info("admin_create_user | email=%s role=%s by admin", user.email, user.role)
    return UserResponse.model_validate(user)


@router.post("/refresh")
async def refresh_access_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Exchange the HttpOnly refresh-token cookie for a new access token."""
    cookie_token = request.cookies.get("refresh_token")
    if not cookie_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = verify_refresh_token(cookie_token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == _uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    settings = get_settings()
    new_access_token = create_access_token(user.id, user.email)
    logger.info("refresh | user=%s id=%s", user.email, user.id)
    return JSONResponse({
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_expiration_minutes * 60,
    })
