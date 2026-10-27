from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.oauth import base as oauth_base
from app.oauth.base import TokenSet
from app.routers import oauth as oauth_router
from app.routers.auth import AuthContext, UserResponse, get_auth_context

_PROJECT_ID = "11111111-1111-1111-1111-111111111111"
_NODE_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _query(response) -> dict[str, list[str]]:
    return parse_qs(urlparse(response.headers["location"]).query)


def test_authorize_requires_auth(client):
    response = client.post(f"/projects/{_PROJECT_ID}/nodes/{_NODE_ID}/authorize")
    assert response.status_code == 401


def test_callback_forwards_code_and_state(client, monkeypatch):
    calls = []
    monkeypatch.setattr(oauth_router, "set_node_secret_as", lambda *a: calls.append(a))
    response = client.get(
        "/oauth/callback", params={"code": "a&b", "state": "s.t"}, follow_redirects=False
    )
    assert response.status_code in (302, 307)
    assert _query(response) == {"oauth_code": ["a&b"], "oauth_state": ["s.t"]}
    assert calls == []


def test_callback_google_error_redirects_error(client):
    response = client.get(
        "/oauth/callback",
        params={"error": "access_denied", "state": "s"},
        follow_redirects=False,
    )
    assert _query(response) == {"oauth": ["error"]}


def test_callback_missing_state_redirects_error(client):
    response = client.get("/oauth/callback", params={"code": "abc"}, follow_redirects=False)
    assert _query(response) == {"oauth": ["error"]}


def test_callback_missing_code_redirects_error(client):
    response = client.get("/oauth/callback", params={"state": "x"}, follow_redirects=False)
    assert _query(response) == {"oauth": ["error"]}


def test_complete_requires_auth(client):
    response = client.post("/oauth/complete", json={"code": "c", "state": "s"})
    assert response.status_code == 401


def _as(user_id: str) -> TestClient:
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user=UserResponse(id=user_id),
        token="fake-token",  # noqa: S106 - test fixture
    )
    return TestClient(app)


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setattr(oauth_base.settings, "oauth_state_secret", "shhh")
    saved: list[tuple] = []
    verified: list[tuple] = []

    async def exchange(code, redirect_uri):
        return TokenSet(access_token="at", refresh_token="rt", expires_at=0)  # noqa: S106 - test fixture

    async def verify_as_owner(node_id, owner_id):
        verified.append((node_id, owner_id))

    monkeypatch.setattr(oauth_router.google, "exchange_code", exchange)
    monkeypatch.setattr(oauth_router, "set_node_secret_as", lambda *a: saved.append(a))
    monkeypatch.setattr(oauth_router, "get_tool_node_for_owner", lambda n, o: object())
    monkeypatch.setattr(oauth_router, "_verify_as_owner", verify_as_owner)
    return saved, verified


def test_complete_saves_for_owner(fakes):
    saved, verified = fakes
    state = oauth_base.sign_state(_NODE_ID, "owner-1")
    response = _as("owner-1").post("/oauth/complete", json={"code": "c", "state": state})
    assert response.status_code == 200
    assert response.json() == {"status": "connected"}
    assert saved == [(_NODE_ID, "owner-1", "oauth_refresh_token", "rt")]
    assert verified == [(_NODE_ID, "owner-1")]


def test_complete_other_user_is_403(fakes):
    saved, _ = fakes
    state = oauth_base.sign_state(_NODE_ID, "attacker")
    response = _as("victim").post("/oauth/complete", json={"code": "c", "state": state})
    assert response.status_code == 403
    assert saved == []


def test_complete_tampered_state_is_400(fakes):
    state = oauth_base.sign_state(_NODE_ID, "owner-1")
    payload_b64, sig = state.split(".", 1)
    response = _as("owner-1").post(
        "/oauth/complete", json={"code": "c", "state": f"{payload_b64}x.{sig}"}
    )
    assert response.status_code == 400


def test_complete_expired_state_is_400(fakes, monkeypatch):
    monkeypatch.setattr(oauth_base, "STATE_TTL_SECONDS", -1)
    state = oauth_base.sign_state(_NODE_ID, "owner-1")
    response = _as("owner-1").post("/oauth/complete", json={"code": "c", "state": state})
    assert response.status_code == 400


def test_complete_missing_node_is_404(fakes, monkeypatch):
    monkeypatch.setattr(oauth_router, "get_tool_node_for_owner", lambda n, o: None)
    state = oauth_base.sign_state(_NODE_ID, "owner-1")
    response = _as("owner-1").post("/oauth/complete", json={"code": "c", "state": state})
    assert response.status_code == 404


def test_complete_no_refresh_token_is_422(fakes, monkeypatch):
    saved, _ = fakes

    async def exchange(code, redirect_uri):
        return TokenSet(access_token="at", refresh_token=None, expires_at=0)  # noqa: S106 - test fixture

    monkeypatch.setattr(oauth_router.google, "exchange_code", exchange)
    state = oauth_base.sign_state(_NODE_ID, "owner-1")
    response = _as("owner-1").post("/oauth/complete", json={"code": "c", "state": state})
    assert response.status_code == 422
    assert saved == []


def test_complete_exchange_failure_is_502(fakes, monkeypatch):
    async def exchange(code, redirect_uri):
        raise oauth_router.google.TokenExchangeError()

    monkeypatch.setattr(oauth_router.google, "exchange_code", exchange)
    state = oauth_base.sign_state(_NODE_ID, "owner-1")
    response = _as("owner-1").post("/oauth/complete", json={"code": "c", "state": state})
    assert response.status_code == 502


def test_complete_uses_callback_redirect_uri(fakes, monkeypatch):
    seen = []

    async def exchange(code, redirect_uri):
        seen.append(redirect_uri)
        return TokenSet(access_token="at", refresh_token="rt", expires_at=0)  # noqa: S106 - test fixture

    monkeypatch.setattr(oauth_router.google, "exchange_code", exchange)
    state = oauth_base.sign_state(_NODE_ID, "owner-1")
    _as("owner-1").post("/oauth/complete", json={"code": "c", "state": state})
    assert seen == ["http://testserver/oauth/callback"]
