"""Rate limiting tests â€” FASE 4.2."""
from __future__ import annotations

import concurrent.futures
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.config import get_settings
from app.dependencies.security import create_access_token, hash_password
from app.main import app, rate_limit_store
from app.middleware.rate_limiter import RateLimitMiddleware, RateLimitStore
from app.models.schemas import User, UserRole
from tests.conftest import ScalarResult


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


def _prefill_user_limit(store: RateLimitStore, user: User, count: int) -> None:
    for _ in range(count):
        store.consume(str(user.id), limit=100)


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-with-32-plus-bytes")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("JWT_EXPIRATION_MINUTES", "15")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_store():
    rate_limit_store.clear()
    yield
    rate_limit_store.clear()


def test_user_can_make_100_requests(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    _prefill_user_limit(rate_limit_store, user, 99)

    response = client.get("/auth/me", headers=_headers(user))

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "100"
    assert response.headers["X-RateLimit-Remaining"] == "0"


def test_user_gets_429_on_101st_request(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    _prefill_user_limit(rate_limit_store, user, 100)

    response = client.get("/auth/me", headers=_headers(user))

    assert response.status_code == 429


def test_429_response_has_correct_headers(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    _prefill_user_limit(rate_limit_store, user, 100)

    response = client.get("/auth/me", headers=_headers(user))

    assert response.status_code == 429
    assert response.headers["X-RateLimit-Limit"] == "100"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert response.headers["Retry-After"].isdigit()
    assert response.headers["X-RateLimit-Reset"].isdigit()


def test_different_users_have_separate_limits(client, mock_db):
    user_a = _make_user(email="a@example.com")
    user_b = _make_user(email="b@example.com")
    _prefill_user_limit(rate_limit_store, user_a, 100)

    mock_db.execute.return_value = ScalarResult(user_a)
    response_a = client.get("/auth/me", headers=_headers(user_a))

    mock_db.execute.return_value = ScalarResult(user_b)
    response_b = client.get("/auth/me", headers=_headers(user_b))

    assert response_a.status_code == 429
    assert response_b.status_code == 200
    assert response_b.headers["X-RateLimit-Remaining"] == "99"


def test_health_endpoint_not_rate_limited(client):
    for _ in range(3):
        response = client.get("/health")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" not in response.headers


def test_webhooks_not_rate_limited(client):
    user = _make_user()
    _prefill_user_limit(rate_limit_store, user, 100)

    for _ in range(3):
        response = client.post("/webhooks/slack", json={})
        assert response.status_code != 429
        assert "X-RateLimit-Limit" not in response.headers


def test_unauthenticated_requests_not_limited(client):
    for _ in range(3):
        missing = client.get("/auth/me")
        invalid = client.get("/auth/me", headers={"Authorization": "Bearer invalid-token"})

        assert missing.status_code == 401
        assert invalid.status_code == 401
        assert "X-RateLimit-Limit" not in missing.headers
        assert "X-RateLimit-Limit" not in invalid.headers


def test_429_response_body_is_valid_json(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)
    _prefill_user_limit(rate_limit_store, user, 100)

    response = client.get("/auth/me", headers=_headers(user))

    assert response.status_code == 429
    assert response.json() == {
        "detail": f"Rate limit exceeded. Retry after {response.headers['Retry-After']} seconds"
    }


def test_rate_limit_header_format_correct(client, mock_db, monkeypatch):
    local_app = FastAPI()
    local_store = RateLimitStore()

    @local_app.get("/limited")
    async def limited():
        return JSONResponse({"ok": True})

    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    get_settings.cache_clear()
    local_app.add_middleware(
        RateLimitMiddleware,
        rate_limit_store=local_store,
        limit=get_settings().rate_limit_per_minute,
    )

    user = _make_user()
    with TestClient(local_app) as local_client:
        response = local_client.get("/limited", headers=_headers(user))

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "3"
    assert response.headers["X-RateLimit-Remaining"] == "2"
    assert response.headers["X-RateLimit-Reset"].isdigit()
    assert int(response.headers["X-RateLimit-Reset"]) >= int(datetime.now(timezone.utc).timestamp())


def test_concurrent_requests_from_same_user():
    store = RateLimitStore()
    user_id = str(uuid.uuid4())
    base_time = datetime.now(timezone.utc)

    def consume_once():
        return store.consume(user_id, limit=3, now=base_time).allowed

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda _: consume_once(), range(5)))

    assert sum(results) == 3
    assert store.data[user_id].count == 3


def test_rate_limit_accurate_to_second():
    store = RateLimitStore()
    user_id = str(uuid.uuid4())
    start = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)

    first = store.consume(user_id, limit=1, now=start)
    blocked = store.consume(user_id, limit=1, now=start + timedelta(seconds=59))
    allowed_again = store.consume(user_id, limit=1, now=start + timedelta(seconds=60))

    assert first.allowed is True
    assert first.remaining == 0
    assert blocked.allowed is False
    assert blocked.retry_after == 1
    assert int(blocked.reset_at.timestamp()) == int((start + timedelta(seconds=60)).timestamp())
    assert allowed_again.allowed is True
