"""JWT authentication dependencies for FastAPI.

Usage:
    from app.dependencies.security import get_current_user, hash_password, verify_password, create_access_token
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.models.schemas import User, UserRole

_bearer = HTTPBearer(auto_error=False)


def _get_auth_settings() -> Settings:
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET must be set in the environment")
    return settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: uuid.UUID, email: str, expires_delta: Optional[timedelta] = None) -> str:
    settings = _get_auth_settings()
    delta = expires_delta or timedelta(minutes=settings.jwt_expiration_minutes)
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + delta,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: uuid.UUID) -> str:
    settings = _get_auth_settings()
    now = datetime.now(tz=timezone.utc)
    delta = timedelta(days=settings.jwt_refresh_token_expiration_days)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + delta,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_refresh_token(token: str) -> Optional[str]:
    """Verify a refresh token. Returns user_id (sub) or None if invalid."""
    try:
        settings = _get_auth_settings()
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "refresh":
            return None
        return payload.get("sub")
    except (TypeError, ValueError, RuntimeError, jwt.PyJWTError):
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    settings = _get_auth_settings()
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or not credentials.credentials:
        raise credentials_exception
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        token_type = payload.get("type")
        if token_type is not None and token_type != "access":
            raise credentials_exception
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        user_uuid = uuid.UUID(user_id)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (TypeError, ValueError, jwt.PyJWTError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def get_user_id_from_token(auth_header: Optional[str]) -> Optional[str]:
    """Extract user_id (sub claim) from a Bearer Authorization header."""
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        settings = _get_auth_settings()
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except (TypeError, ValueError, RuntimeError, jwt.PyJWTError):
        return None


def require_role(allowed_roles: List[UserRole]):
    """Return a FastAPI dependency that enforces role-based access.

    Usage:
        current_user: User = Depends(require_role([UserRole.admin, UserRole.developer]))
    """
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            roles_text = ", ".join(role.value for role in allowed_roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Se requieren roles: {roles_text}",
            )
        return current_user

    return role_checker
