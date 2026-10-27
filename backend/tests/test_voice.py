"""POST /chat/transcribe and the Gemini call it wraps."""

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.main import app
from app.routers import chat as chat_router
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.services import voice


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(chat_router.settings, "gemini_api_key", "k")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user=UserResponse(id="user-1", email="u@example.com"),
        token="fake-token",  # noqa: S106 - test fixture
    )
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _post(client, body=b"abc", ctype="audio/webm;codecs=opus"):
    return client.post("/chat/transcribe", content=body, headers={"Content-Type": ctype})


def test_transcribe_returns_text(client, monkeypatch):
    seen = {}

    async def fake(audio, media_type):
        seen.update(audio=audio, media_type=media_type)
        return "hello world"

    monkeypatch.setattr(chat_router.voice, "transcribe", fake)
    res = _post(client)
    assert res.status_code == 200
    assert res.json() == {"text": "hello world"}
    assert seen == {"audio": b"abc", "media_type": "audio/webm;codecs=opus"}


def test_transcribe_rejects_non_audio(client):
    assert _post(client, ctype="application/json").status_code == 415


def test_transcribe_too_long(client, monkeypatch):
    monkeypatch.setattr(chat_router, "_MAX_VOICE_BYTES", 2)
    assert _post(client).status_code == 413


def test_transcribe_no_key_is_503(client, monkeypatch):
    monkeypatch.setattr(chat_router.settings, "gemini_api_key", "")
    assert _post(client).status_code == 503


def test_transcribe_model_error_is_502(client, monkeypatch):
    async def boom(audio, media_type):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(chat_router.voice, "transcribe", boom)
    assert _post(client).status_code == 502


def test_transcribe_requires_auth():
    res = TestClient(app).post(
        "/chat/transcribe", content=b"abc", headers={"Content-Type": "audio/webm"}
    )
    assert res.status_code == 401


async def test_voice_sends_audio_with_bare_mime(monkeypatch):
    seen = []

    def model(messages, info):
        seen.extend(p for p in messages[-1].parts[-1].content if isinstance(p, BinaryContent))
        return ModelResponse(parts=[TextPart(" Hi there. ")])

    monkeypatch.setattr(voice, "_agent", lambda: Agent(FunctionModel(model)))
    assert await voice.transcribe(b"abc", "audio/webm;codecs=opus") == "Hi there."
    assert seen[0].media_type == "audio/webm"
    assert seen[0].data == b"abc"
