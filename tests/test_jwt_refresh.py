"""JWT Refresh Token tests — FASE 4.4."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import get_settings
from app.dependencies.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_refresh_token,
)
from app.models.schemas import User, UserRole
from tests.conftest import ScalarResult


def _make_user(role: UserRole = UserRole.user) -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        email=f"{role.value}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("password123"),
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Token creation / verification — unit tests (no HTTP)
# ---------------------------------------------------------------------------

def test_create_access_token_has_access_type():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "u@example.com")
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert payload["type"] == "access"
    assert payload["sub"] == str(user_id)


def test_create_refresh_token_has_refresh_type():
    user_id = uuid.uuid4()
    token = create_refresh_token(user_id)
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert payload["type"] == "refresh"
    assert payload["sub"] == str(user_id)


def test_access_token_expires_in_15_minutes():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "u@example.com")
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
    delta_minutes = (exp - iat).total_seconds() / 60
    assert abs(delta_minutes - settings.jwt_expiration_minutes) < 1


def test_refresh_token_expires_in_7_days():
    user_id = uuid.uuid4()
    token = create_refresh_token(user_id)
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
    delta_days = (exp - iat).total_seconds() / 86400
    assert abs(delta_days - settings.jwt_refresh_token_expiration_days) < 0.1


def test_verify_refresh_token_returns_user_id():
    user_id = uuid.uuid4()
    token = create_refresh_token(user_id)
    assert verify_refresh_token(token) == str(user_id)


def test_verify_refresh_token_rejects_access_token():
    token = create_access_token(uuid.uuid4(), "u@example.com")
    assert verify_refresh_token(token) is None


def test_verify_refresh_token_rejects_garbage():
    assert verify_refresh_token("not.a.token") is None


def test_verify_refresh_token_rejects_expired():
    settings = get_settings()
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "refresh",
        "iat": datetime.now(timezone.utc) - timedelta(days=8),
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    expired = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    assert verify_refresh_token(expired) is None


# ---------------------------------------------------------------------------
# Access token must be rejected at protected endpoints if type != "access"
# ---------------------------------------------------------------------------

def test_refresh_token_rejected_at_protected_endpoint(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    token = create_refresh_token(user.id)
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /auth/login — now returns refresh token
# ---------------------------------------------------------------------------

def test_login_returns_both_tokens(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    response = client.post("/auth/login", json={"email": user.email, "password": "password123"})
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900


def test_login_refresh_token_is_valid(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    response = client.post("/auth/login", json={"email": user.email, "password": "password123"})
    assert response.status_code == 200
    refresh_token = response.json()["refresh_token"]
    assert verify_refresh_token(refresh_token) == str(user.id)


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------

def test_refresh_returns_new_access_token(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    token = create_refresh_token(user.id)
    response = client.post("/auth/refresh", json={"refresh_token": token})
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900


def test_refresh_with_invalid_token_returns_401(client):
    response = client.post("/auth/refresh", json={"refresh_token": "invalid.token"})
    assert response.status_code == 401


def test_refresh_with_access_token_returns_401(client):
    token = create_access_token(uuid.uuid4(), "u@example.com")
    response = client.post("/auth/refresh", json={"refresh_token": token})
    assert response.status_code == 401


def test_refresh_with_expired_token_returns_401(client):
    settings = get_settings()
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "refresh",
        "iat": datetime.now(timezone.utc) - timedelta(days=8),
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    expired = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    response = client.post("/auth/refresh", json={"refresh_token": expired})
    assert response.status_code == 401


def test_refresh_for_inactive_user_returns_401(client, mock_db):
    user = _make_user()
    user.is_active = False
    mock_db.execute.return_value = ScalarResult(user)
    token = create_refresh_token(user.id)
    response = client.post("/auth/refresh", json={"refresh_token": token})
    assert response.status_code == 401


def test_new_access_token_accesses_protected_endpoint(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    token = create_refresh_token(user.id)

    refresh_response = client.post("/auth/refresh", json={"refresh_token": token})
    assert refresh_response.status_code == 200
    new_access_token = refresh_response.json()["access_token"]

    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {new_access_token}"})
    assert me_response.status_code == 200
