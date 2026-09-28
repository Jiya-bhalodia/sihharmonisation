from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api import auth
from app import security


def _request() -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "headers": [],
        "query_string": b"",
        "client": ("192.0.2.10", 1234),
    })


def _settings(free_demo: bool) -> SimpleNamespace:
    return SimpleNamespace(
        FREE_DEMO_MODE=free_demo,
        is_local_demo_mode=False,
        AUTH_ENABLED=True,
        REDIS_URL="rediss://placeholder.invalid",
        LOGIN_RATE_LIMIT_ATTEMPTS=5,
        LOGIN_RATE_LIMIT_IP_ATTEMPTS=30,
        LOGIN_RATE_LIMIT_WINDOW_SECONDS=900,
        AUTH_TOKEN_TTL_MINUTES=60,
    )


def _login_request(email="person@example.com", password="long-enough-password"):
    return auth.LoginRequest(email=email, password=password)


def _valid_demo_login(monkeypatch, email, password):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(free_demo=True))
    monkeypatch.setattr(auth, "issue_token", lambda user: f"signed-token:{user.id}:{user.role}")

    def unexpected_redis(*args, **kwargs):
        raise AssertionError("FREE_DEMO_MODE login must not contact Redis")

    def unexpected_authenticate(*args, **kwargs):
        raise AssertionError("FREE_DEMO_MODE login must not look up a registered user")

    monkeypatch.setattr(auth.Redis, "from_url", unexpected_redis)
    monkeypatch.setattr(auth, "authenticate", unexpected_authenticate)
    return auth.login(_login_request(email, password), _request(), db=object())


def test_free_demo_accepts_valid_email_and_password(monkeypatch):
    response = _valid_demo_login(monkeypatch, "first@example.com", "password-123")

    assert response["access_token"] == "signed-token:US_FREE_DEMO_EVALUATOR:evaluator"
    assert response["token_type"] == "bearer"
    assert response["user"] == {
        "id": "US_FREE_DEMO_EVALUATOR",
        "email": "demo@bhumi-x.local",
        "full_name": "BHUMI-X Demo Evaluator",
        "role": "evaluator",
    }


def test_free_demo_maps_different_credentials_to_same_demo_identity(monkeypatch):
    response = _valid_demo_login(monkeypatch, "another@example.org", "different-password")

    assert response["user"]["id"] == "US_FREE_DEMO_EVALUATOR"
    assert response["user"]["email"] == "demo@bhumi-x.local"
    assert response["user"]["role"] == "evaluator"


def test_free_demo_rejects_invalid_email(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(free_demo=True))

    with pytest.raises(ValidationError, match="Enter a valid email address"):
        _login_request("not-an-email", "long-enough-password")


def test_free_demo_rejects_password_shorter_than_eight_characters(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(free_demo=True))

    with pytest.raises(ValidationError, match="Password must be at least 8 characters"):
        _login_request("person@example.com", "short7")


def test_production_login_password_validation_is_unchanged(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(free_demo=False))

    assert _login_request("person@example.com", "short").password == "short"


def test_free_demo_token_resolves_to_fixed_evaluator_without_database_lookup(monkeypatch):
    settings = _settings(free_demo=True)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "_token_claims", lambda token: {
        "sub": security.FREE_DEMO_USER_ID,
        "role": "administrator",  # The role claim cannot elevate this fixed identity.
    })

    class NoDatabaseLookup:
        def query(self, *args, **kwargs):
            raise AssertionError("fixed demo identity must not be looked up in the database")

    user = security.current_user(
        _request(),
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="signed-token"),
        db=NoDatabaseLookup(),
    )

    assert user.id == security.FREE_DEMO_USER_ID
    assert user.email == "demo@bhumi-x.local"
    assert user.role == "evaluator"


def test_production_login_keeps_rate_limit_and_real_user_authentication(monkeypatch):
    settings = _settings(free_demo=False)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    calls = []

    class RedisClient:
        def eval(self, *args):
            return [0, 0]

        def close(self):
            calls.append("redis-close")

    def redis_from_url(url, **kwargs):
        calls.append(("redis", url))
        return RedisClient()

    user = SimpleNamespace(id="US42", email="person@example.com", full_name="Real User", role="reviewer")

    def authenticate(db, email, password):
        calls.append(("authenticate", db, email, password))
        return user

    monkeypatch.setattr(auth.Redis, "from_url", redis_from_url)
    monkeypatch.setattr(auth, "authenticate", authenticate)
    monkeypatch.setattr(auth, "issue_token", lambda value: "normal-token")

    response = auth.login(_login_request("Person@Example.com", "unchanged-password"), _request(), db="db-session")

    assert response["access_token"] == "normal-token"
    assert response["user"]["id"] == "US42"
    assert ("authenticate", "db-session", "person@example.com", "unchanged-password") in calls
    assert any(isinstance(call, tuple) and call[0] == "redis" for call in calls)


def test_production_login_keeps_503_when_redis_fails(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(free_demo=False))
    monkeypatch.setattr(auth.Redis, "from_url", lambda *args, **kwargs: (_ for _ in ()).throw(
        RedisConnectionError("unavailable")
    ))
    monkeypatch.setattr(auth, "authenticate", lambda *args: pytest.fail("must not authenticate before limiter"))

    with pytest.raises(HTTPException) as error:
        auth.login(_login_request(), _request(), db=object())

    assert error.value.status_code == 503
