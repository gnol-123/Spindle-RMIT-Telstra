"""Login/refresh must not park a session on the shared client; logout revokes the caller's own."""

import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import auth as auth_router
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.services import supabase as sb

_USER = {
    "id": "11111111-1111-1111-1111-111111111111",
    "aud": "authenticated",
    "email": "u@example.com",
    "created_at": "2026-01-01T00:00:00Z",
    "app_metadata": {},
    "user_metadata": {},
}


def _token_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": "at-" + request.url.params.get("grant_type", ""),
            "refresh_token": "rt",
            "token_type": "bearer",
            "expires_in": 3600,
            "expires_at": int(time.time()) + 3600,
            "user": _USER,
        },
    )


@pytest.fixture
def fake_supabase(monkeypatch):
    monkeypatch.setattr(sb.settings, "supabase_url", "https://fake.supabase.co")
    monkeypatch.setattr(sb.settings, "supabase_key", "anon-key")
    mock = httpx.Client(transport=httpx.MockTransport(_token_response))
    monkeypatch.setattr(sb, "_http", lambda *a, **k: mock)
    sb._user_http.cache_clear()
    sb.get_client.cache_clear()
    monkeypatch.setattr(sb, "_user_http", lambda: mock)
    yield sb.get_client()
    sb.get_client.cache_clear()


def _shared_session(shared):
    return shared.auth._in_memory_session, shared.auth._refresh_token_timer


def test_login_leaves_no_session_on_shared_client(fake_supabase):
    response = TestClient(app).post(
        "/auth/login", json={"email": "u@example.com", "password": "pw"}
    )
    assert response.status_code == 200
    assert response.json()["access_token"] == "at-password"  # noqa: S105
    assert _shared_session(fake_supabase) == (None, None)


def test_refresh_leaves_no_session_on_shared_client(fake_supabase):
    response = TestClient(app).post("/auth/refresh", json={"refresh_token": "rt"})
    assert response.status_code == 200
    assert response.json()["access_token"] == "at-refresh_token"  # noqa: S105
    assert _shared_session(fake_supabase) == (None, None)


def test_auth_client_is_fresh_and_inert(fake_supabase):
    a, b = sb.get_auth_client(), sb.get_auth_client()
    assert a is not b
    assert a is not fake_supabase
    assert a.auth._auto_refresh_token is False
    assert a.auth._persist_session is False


def test_logout_revokes_callers_token_locally(monkeypatch):
    calls = []

    class Admin:
        def sign_out(self, jwt, scope="global"):
            calls.append((jwt, scope))

    class Client:
        class auth:  # noqa: N801 - mirrors supabase client shape
            admin = Admin()

            @staticmethod
            def sign_out(*a, **k):
                raise AssertionError("must not sign out the shared client's session")

    monkeypatch.setattr(auth_router, "get_client", lambda: Client)
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user=UserResponse(id="user-1"),
        token="callers-jwt",  # noqa: S106 - test fixture
    )
    try:
        response = TestClient(app).post("/auth/logout")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 204
    assert calls == [("callers-jwt", "local")]
