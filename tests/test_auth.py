from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.config import get_settings
from app.dependencies.security import create_access_token, hash_password
from app.models.schemas import Ticket, TicketPriority, TicketStatus, User, UserRole
from tests.conftest import ScalarResult


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-with-32-plus-bytes")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("JWT_EXPIRATION_MINUTES", "15")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_user(email: str = "user@example.com", password: str = "password123") -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(password),
        role=UserRole.user,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _make_ticket() -> Ticket:
    now = datetime.now(timezone.utc)
    return Ticket(
        id=uuid.uuid4(),
        title="Protected ticket",
        description="Protected endpoint fixture",
        status=TicketStatus.pending,
        priority=TicketPriority.P2,
        required_models=[],
        context_snapshot=None,
        created_at=now,
        updated_at=now,
    )


def _auth_headers(user: User, expires_delta: timedelta | None = None) -> dict[str, str]:
    token = create_access_token(user.id, user.email, expires_delta=expires_delta)
    return {"Authorization": f"Bearer {token}"}


async def _assign_user_defaults(user: User) -> None:
    now = datetime.now(timezone.utc)
    user.id = uuid.uuid4()
    user.role = UserRole.user
    user.is_active = True
    user.created_at = now
    user.updated_at = now


def test_register_success(client, mock_db):
    mock_db.execute.return_value = ScalarResult(None)
    mock_db.refresh.side_effect = _assign_user_defaults

    response = client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "password123"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "user@example.com"
    assert "password_hash" not in payload
    assert mock_db._added[0].password_hash != "password123"


def test_register_duplicate_email(client, mock_db):
    mock_db.execute.return_value = ScalarResult(_make_user())

    response = client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "password123"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


def test_register_invalid_email(client, mock_db):
    response = client.post(
        "/auth/register",
        json={"email": "invalid-email", "password": "password123"},
    )

    assert response.status_code == 400
    assert mock_db.execute.await_count == 0


def test_register_short_password(client, mock_db):
    response = client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "short"},
    )

    assert response.status_code == 400
    assert mock_db.execute.await_count == 0


def test_login_success(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)

    response = client.post(
        "/auth/login",
        json={"email": user.email, "password": "password123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["user"]["email"] == user.email
    assert "refresh_token" not in payload


def test_login_sets_refresh_token_in_httponly_cookie(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)

    response = client.post(
        "/auth/login",
        json={"email": user.email, "password": "password123"},
    )

    assert response.status_code == 200
    assert "refresh_token" in response.cookies
    assert response.cookies["refresh_token"]  # not empty
    set_cookie = response.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()


def test_login_invalid_email(client, mock_db):
    mock_db.execute.return_value = ScalarResult(None)

    response = client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": "password123"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_login_invalid_password(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)

    response = client.post(
        "/auth/login",
        json={"email": user.email, "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_get_me_with_token(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)

    response = client.get("/auth/me", headers=_auth_headers(user))

    assert response.status_code == 200
    assert response.json()["email"] == user.email


def test_get_me_no_token(client):
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_get_me_expired_token(client, mock_db):
    user = _make_user()

    response = client.get(
        "/auth/me",
        headers=_auth_headers(user, expires_delta=timedelta(minutes=-1)),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token has expired"
    assert mock_db.execute.await_count == 0


def test_protected_endpoint_requires_token(client):
    response = client.get(f"/api/tasks/ticket/{uuid.uuid4()}")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_protected_endpoint_with_token(client, mock_db):
    user = _make_user()
    ticket = _make_ticket()
    mock_db.execute.side_effect = [ScalarResult(user), ScalarResult([])]

    with patch(
        "app.api.tasks._get_ticket_or_404",
        new=AsyncMock(return_value=ticket),
    ):
        response = client.get(
            f"/api/tasks/ticket/{ticket.id}",
            headers=_auth_headers(user),
        )

    assert response.status_code == 200
    assert response.json() == []
