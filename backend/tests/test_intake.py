"""Jev intent classification, idea titles, and the classify/build routes."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic_ai import Agent
from pydantic_ai.models.function import FunctionModel

from app.main import app
from app.repositories.project_repo import AgentType, Project
from app.routers import projects as projects_router
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.deps import (
    get_environment_repository,
    get_project_repository,
    get_tool_repository,
)
from app.services import intake

_P1 = "11111111-1111-1111-1111-111111111111"
_N1 = "33333333-3333-3333-3333-333333333333"


def _jev(monkeypatch, handler):
    monkeypatch.setattr(intake.settings, "jev_api_key", "k")
    monkeypatch.setattr(intake, "_transport", httpx.MockTransport(handler))


def _answer(choice, confidence):
    return {
        "model": "jev-1.13.0",
        "answers": {"intent": {"type": "choice", "choice": choice, "confidence": confidence}},
    }


@pytest.mark.anyio
async def test_classify_build_above_threshold(monkeypatch):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json=_answer("build", 0.91))

    _jev(monkeypatch, handler)
    assert await intake.classify("make me a todo app") == "build"
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1/systemone"
    assert seen[0].headers["authorization"] == "Bearer k"
    assert body["state"] == "make me a todo app"
    assert set(body["questions"]["intent"]["criteria"]) == {"name", "build"}


@pytest.mark.anyio
async def test_classify_low_confidence_is_name(monkeypatch):
    _jev(monkeypatch, lambda req: httpx.Response(200, json=_answer("build", 0.42)))
    assert await intake.classify("todo") == "name"


@pytest.mark.anyio
async def test_classify_no_key_is_name(monkeypatch):
    def handler(req):
        raise AssertionError("no request without a key")

    monkeypatch.setattr(intake, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(intake.settings, "jev_api_key", "")
    assert await intake.classify("make me an app") == "name"


@pytest.mark.anyio
async def test_classify_http_error_is_name(monkeypatch):
    _jev(monkeypatch, lambda req: httpx.Response(503))
    assert await intake.classify("make me an app") == "name"


@pytest.mark.anyio
async def test_classify_malformed_is_name(monkeypatch):
    _jev(monkeypatch, lambda req: httpx.Response(200, json={}))
    assert await intake.classify("make me an app") == "name"


@pytest.mark.anyio
async def test_title_fallback_on_model_error(monkeypatch):
    def boom(messages, info):
        raise RuntimeError("model down")

    monkeypatch.setattr(intake, "_title_agent", lambda: Agent(FunctionModel(boom), output_type=str))
    title = await intake.title_for("hey build me a finance tracker app now")
    assert title == "Hey Build Me A Finance"


class _Repo:
    def __init__(self):
        self.names = []
        self.deleted = []

    def create_project(self, name, description=None):
        self.names.append(name)
        return Project(id=_P1, name=name)

    def delete_project(self, pid):
        self.deleted.append(pid)
        return True

    def get_agent_type(self, slug):
        return AgentType(
            id="at1",
            slug=slug,
            name="Orchestrator",
            description="d",
            system_prompt="x",
            model="m",
            default_presets=[],
        )


def _client(monkeypatch, repo, provision):
    async def fake_title(idea):
        return "Finance Tracker"

    monkeypatch.setattr(projects_router.intake, "title_for", fake_title)
    monkeypatch.setattr(projects_router, "provision_agent", provision)
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user=UserResponse(id="user-1", email="u@example.com"),
        token="fake-token",  # noqa: S106 - test fixture
    )
    app.dependency_overrides[get_project_repository] = lambda: repo
    app.dependency_overrides[get_environment_repository] = lambda: object()
    app.dependency_overrides[get_tool_repository] = lambda: object()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_build_route_creates_project_and_orchestrator(monkeypatch):
    calls = []

    async def fake_provision(project_id, agent_type, name, **kw):
        calls.append((project_id, agent_type.slug, kw))
        return _N1

    repo = _Repo()
    res = _client(monkeypatch, repo, fake_provision).post(
        "/projects/build", json={"idea": "build me a finance tracker"}
    )

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["project"]["name"] == "Finance Tracker"
    assert body["orchestrator_node_id"] == _N1
    assert repo.names == ["Finance Tracker"]
    pid, slug, kw = calls[0]
    assert (pid, slug) == (_P1, "orchestrator")
    assert kw["tool_policy"] == "auto"
    assert (kw["position_x"], kw["position_y"]) == (0, 0)


def test_build_deletes_project_when_provision_fails(monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("provision failed")

    repo = _Repo()
    res = _client(monkeypatch, repo, boom).post("/projects/build", json={"idea": "an app"})
    assert res.status_code == 500
    assert repo.deleted == [_P1]


@pytest.mark.parametrize(
    "path,field", [("/projects/build", "idea"), ("/projects/classify", "text")]
)
def test_blank_prompt_is_422(monkeypatch, path, field):
    async def never(*_a, **_k):
        raise AssertionError("must not provision")

    res = _client(monkeypatch, _Repo(), never).post(path, json={field: "   "})
    assert res.status_code == 422


def test_classify_requires_auth():
    res = TestClient(app).post("/projects/classify", json={"text": "todo"})
    assert res.status_code == 401


@pytest.mark.anyio
async def test_classify_bad_base_url_is_name(monkeypatch):
    monkeypatch.setattr(intake.settings, "jev_api_key", "k")
    monkeypatch.setattr(intake.settings, "jev_api_base", "http://[::1")
    assert await intake.classify("make me an app") == "name"


@pytest.mark.anyio
async def test_title_fallback_never_empty(monkeypatch):
    def boom(messages, info):
        raise RuntimeError("model down")

    monkeypatch.setattr(intake, "_title_agent", lambda: Agent(FunctionModel(boom), output_type=str))
    assert await intake.title_for("   ") == "New Project"


def _title_reply(text):
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    def reply(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"name": text})])

    return lambda: intake._make_title_agent(FunctionModel(reply))


@pytest.mark.parametrize(
    "reply, expected",
    [
        ('Ledger Lite\n```html\n<!doctype html>\n<html lang="en">', "Ledger Lite"),
        ('**Title:** "Habit Streaks"', "Habit Streaks"),
        ("Recipe Box Planner For Busy Families", "Recipe Box Planner For"),
    ],
)
async def test_title_is_cleaned(monkeypatch, reply, expected):
    monkeypatch.setattr(intake, "_title_agent", _title_reply(reply))
    assert await intake.title_for("build me something") == expected


async def test_title_code_only_falls_back(monkeypatch):
    monkeypatch.setattr(intake, "_title_agent", _title_reply("```html\n<div>hi</div>"))
    assert await intake.title_for("make a habit app") == "Make A Habit App"


async def test_title_chatty_reply_falls_back(monkeypatch):
    monkeypatch.setattr(
        intake,
        "_title_agent",
        _title_reply("Here's a complete HTML document for a finance tracker:"),
    )
    assert await intake.title_for("build me a finance tracker") == "Build Me A Finance Tracker"


def test_title_agent_uses_structured_output():
    assert intake._title_agent().output_type is intake.ProjectTitle
