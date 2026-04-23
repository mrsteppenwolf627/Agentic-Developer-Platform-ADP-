"""JWT Refresh Token tests — FASE 4.4 (HttpOnly cookie transport)."""
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
    assert abs((exp - iat).total_seconds() / 60 - settings.jwt_expiration_minutes) < 1


def test_refresh_token_expires_in_7_days():
    user_id = uuid.uuid4()
    token = create_refresh_token(user_id)
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
    assert abs((exp - iat).total_seconds() / 86400 - settings.jwt_refresh_token_expiration_days) < 0.1


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
# Refresh token must be rejected when used as Bearer at protected endpoints
# ---------------------------------------------------------------------------

def test_refresh_token_rejected_at_protected_endpoint(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    token = create_refresh_token(user.id)
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /auth/login — access_token in JSON, refresh_token in HttpOnly cookie
# ---------------------------------------------------------------------------

def test_login_returns_access_token_in_json_not_refresh(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    response = client.post("/auth/login", json={"email": user.email, "password": "password123"})
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" not in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900


def test_login_sets_refresh_token_as_httponly_cookie(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    response = client.post("/auth/login", json={"email": user.email, "password": "password123"})
    assert response.status_code == 200
    assert "refresh_token" in response.cookies
    set_cookie = response.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()


def test_login_refresh_cookie_contains_valid_token(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    response = client.post("/auth/login", json={"email": user.email, "password": "password123"})
    assert response.status_code == 200
    cookie_token = response.cookies["refresh_token"]
    assert verify_refresh_token(cookie_token) == str(user.id)


# ---------------------------------------------------------------------------
# POST /auth/refresh — reads refresh_token from HttpOnly cookie
# ---------------------------------------------------------------------------

def test_refresh_with_no_cookie_returns_401(client):
    response = client.post("/auth/refresh")
    assert response.status_code == 401
    assert response.json()["detail"] == "No refresh token found"


def test_refresh_returns_new_access_token(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    token = create_refresh_token(user.id)
    response = client.post("/auth/refresh", cookies={"refresh_token": token})
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900


def test_refresh_with_invalid_cookie_returns_401(client):
    response = client.post("/auth/refresh", cookies={"refresh_token": "invalid.token.here"})
    assert response.status_code == 401


def test_refresh_with_access_token_in_cookie_returns_401(client):
    token = create_access_token(uuid.uuid4(), "u@example.com")
    response = client.post("/auth/refresh", cookies={"refresh_token": token})
    assert response.status_code == 401


def test_refresh_with_expired_cookie_returns_401(client):
    settings = get_settings()
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "refresh",
        "iat": datetime.now(timezone.utc) - timedelta(days=8),
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    expired = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    response = client.post("/auth/refresh", cookies={"refresh_token": expired})
    assert response.status_code == 401


def test_refresh_for_inactive_user_returns_401(client, mock_db):
    user = _make_user()
    user.is_active = False
    mock_db.execute.return_value = ScalarResult(user)
    token = create_refresh_token(user.id)
    response = client.post("/auth/refresh", cookies={"refresh_token": token})
    assert response.status_code == 401


def test_new_access_token_accesses_protected_endpoint(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    token = create_refresh_token(user.id)

    refresh_response = client.post("/auth/refresh", cookies={"refresh_token": token})
    assert refresh_response.status_code == 200
    new_access_token = refresh_response.json()["access_token"]

    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {new_access_token}"})
    assert me_response.status_code == 200
