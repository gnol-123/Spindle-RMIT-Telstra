"""/auth/me exposes the Google display name from user_metadata."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


def _me(metadata):
    user = SimpleNamespace(id="u1", email="a@b.c", user_metadata=metadata)
    client = MagicMock()
    client.auth.get_user.return_value = SimpleNamespace(user=user)
    with patch("app.routers.auth.get_client", return_value=client):
        return TestClient(app).get("/auth/me", headers={"Authorization": "Bearer t"}).json()


def test_me_includes_google_name():
    assert _me({"full_name": "Sayber Te"})["name"] == "Sayber Te"


def test_me_falls_back_to_name_key():
    assert _me({"name": "Sayber"})["name"] == "Sayber"


def test_me_name_none_without_metadata():
    assert _me({})["name"] is None
    assert _me(None)["name"] is None
