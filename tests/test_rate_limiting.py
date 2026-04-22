"""Rate limiting tests — FASE 4.2.

Strategy:
  - Pre-set store counters directly instead of making 100 real HTTP calls
    so the suite runs in < 1 second.
  - Only a few tests make multiple real requests (≤ 5) to verify the counter
    increments correctly end-to-end.

Coverage:
  - Authenticated requests consume the counter.
  - /health, /webhooks/* and unauthenticated requests are NOT counted.
  - HTTP 429 with correct headers is returned when the limit is reached.
  - Different users have independent counters.
  - Counter resets after the window expires.
  - X-RateLimit-* headers appear on normal responses.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.dependencies.security import create_access_token, hash_password
from app.middleware.rate_limiter import RateLimitEntry, RateLimitStore
from app.models.schemas import User, UserRole
from tests.conftest import ScalarResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(role: UserRole = UserRole.user, email: str | None = None) -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        email=email or f"{role.value}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("password123"),
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}


def _at_limit(store: RateLimitStore, user: User, limit: int = 100) -> None:
    """Pre-fill the store so the next request is the (limit+1)th."""
    entry = store.get_or_create(str(user.id))
    entry.count = limit
    entry.reset_at = datetime.now(timezone.utc) + timedelta(minutes=1)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_store():
    """Isolate each test — clear the shared in-memory store."""
    from app.main import rate_limit_store
    rate_limit_store.clear()
    yield
    rate_limit_store.clear()


# ---------------------------------------------------------------------------
# /health and /webhooks/* — excluded from rate limiting
# ---------------------------------------------------------------------------

def test_health_endpoint_not_rate_limited(client):
    for _ in range(5):
        r = client.get("/health")
        assert r.status_code == 200
        assert "X-RateLimit-Limit" not in r.headers


def test_webhooks_not_rate_limited(client):
    from app.main import rate_limit_store
    user = _make_user()
    _at_limit(rate_limit_store, user)

    # Even though this user is at the limit, /webhooks/* is excluded
    for _ in range(3):
        r = client.post("/webhooks/slack", json={})
        assert r.status_code != 429


# ---------------------------------------------------------------------------
# Unauthenticated requests — not counted
# ---------------------------------------------------------------------------

def test_unauthenticated_requests_not_rate_limited(client):
    """No token → rate limiter bypasses → endpoint returns 401, never 429."""
    for _ in range(5):
        r = client.get("/auth/me")
        assert r.status_code == 401
        assert "X-RateLimit-Limit" not in r.headers


def test_invalid_token_requests_not_rate_limited(client):
    """Malformed token can't be decoded → rate limiter treats as anonymous."""
    bad_headers = {"Authorization": "Bearer not-a-real-jwt"}
    for _ in range(5):
        r = client.get("/auth/me", headers=bad_headers)
        assert r.status_code == 401
        assert "X-RateLimit-Limit" not in r.headers


# ---------------------------------------------------------------------------
# Authenticated requests — rate limit headers present
# ---------------------------------------------------------------------------

def test_authenticated_request_has_rate_limit_headers(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)

    r = client.get("/auth/me", headers=_headers(user))

    assert r.status_code == 200
    assert r.headers.get("X-RateLimit-Limit") == "100"
    assert r.headers.get("X-RateLimit-Remaining") == "99"
    assert "X-RateLimit-Reset" in r.headers


def test_rate_limit_remaining_decrements(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    h = _headers(user)

    r1 = client.get("/auth/me", headers=h)
    r2 = client.get("/auth/me", headers=h)
    r3 = client.get("/auth/me", headers=h)

    assert int(r1.headers["X-RateLimit-Remaining"]) == 99
    assert int(r2.headers["X-RateLimit-Remaining"]) == 98
    assert int(r3.headers["X-RateLimit-Remaining"]) == 97


# ---------------------------------------------------------------------------
# HTTP 429 — triggered when limit is reached
# ---------------------------------------------------------------------------

def test_user_gets_429_when_limit_exceeded(client, mock_db):
    from app.main import rate_limit_store
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    _at_limit(rate_limit_store, user)

    r = client.get("/auth/me", headers=_headers(user))

    assert r.status_code == 429
    assert "Rate limit exceeded" in r.json()["detail"]


def test_429_response_has_correct_headers(client, mock_db):
    from app.main import rate_limit_store
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    _at_limit(rate_limit_store, user)

    r = client.get("/auth/me", headers=_headers(user))

    assert r.status_code == 429
    assert r.headers.get("X-RateLimit-Limit") == "100"
    assert r.headers.get("X-RateLimit-Remaining") == "0"
    assert "Retry-After" in r.headers
    assert "X-RateLimit-Reset" in r.headers
    retry_after = int(r.headers["Retry-After"])
    assert 0 <= retry_after <= 60


def test_429_response_body_has_detail(client, mock_db):
    from app.main import rate_limit_store
    user = _make_user()
    _at_limit(rate_limit_store, user)

    r = client.get("/auth/me", headers=_headers(user))

    assert r.status_code == 429
    body = r.json()
    assert "detail" in body


# ---------------------------------------------------------------------------
# Different users have independent counters
# ---------------------------------------------------------------------------

def test_different_users_have_separate_limits(client, mock_db):
    from app.main import rate_limit_store
    user_a = _make_user(email="a@example.com")
    user_b = _make_user(email="b@example.com")

    # Fill user_a to the limit
    _at_limit(rate_limit_store, user_a)

    # user_a should get 429
    mock_db.execute.return_value = ScalarResult(user_a)
    r_a = client.get("/auth/me", headers=_headers(user_a))
    assert r_a.status_code == 429

    # user_b still has full quota
    mock_db.execute.return_value = ScalarResult(user_b)
    r_b = client.get("/auth/me", headers=_headers(user_b))
    assert r_b.status_code == 200
    assert int(r_b.headers["X-RateLimit-Remaining"]) == 99


# ---------------------------------------------------------------------------
# Window reset
# ---------------------------------------------------------------------------

def test_rate_limit_resets_after_window_expires(client, mock_db):
    from app.main import rate_limit_store
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    h = _headers(user)

    # Fill to limit
    _at_limit(rate_limit_store, user)
    assert client.get("/auth/me", headers=h).status_code == 429

    # Simulate window expiry without sleeping
    entry = rate_limit_store.data[str(user.id)]
    entry.reset_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    # Next request should succeed and reset the counter
    r = client.get("/auth/me", headers=h)
    assert r.status_code == 200
    assert int(r.headers["X-RateLimit-Remaining"]) == 99
