"""Cancel, attach, and the busy/paused edges of /chat, /chat/stream, /chat/resume.

Fakes mirror test_chat_approval.py's pattern: in-memory repos, FunctionModel
for the LLM, dependency_overrides for auth and repos.
"""

import json
import threading
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import app.workflows as workflows
from app.main import app
from app.repositories.project_repo import Inbound, Message, Node
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.chat import chat_attach
from app.routers.deps import (
    TurnRepositories,
    get_environment_repository,
    get_project_repository,
    get_tool_repository,
    get_turn_repositories,
)
from app.services import runs
from app.services.runs import RunningTurn

_NODE_ID = "22222222-2222-2222-2222-222222222222"
_OTHER_NODE_ID = "55555555-5555-5555-5555-555555555555"
_PROJECT_ID = "11111111-1111-1111-1111-111111111111"
_CONVERSATION_ID = "33333333-3333-3333-3333-333333333333"


@pytest.fixture(autouse=True)
def clean_runs():
    runs._RUNS.clear()
    yield
    runs._RUNS.clear()


class _FakeChatRepo:
    def __init__(self) -> None:
        self.messages: list[Message] = []
        self.conversation_created = False

    def get_agent_node(self, node_id: str) -> Node | None:
        if node_id != _NODE_ID:
            return None
        return Node(
            id=_NODE_ID,
            project_id=_PROJECT_ID,
            name="Agent",
            agent_type_id=None,
            system_prompt="You are a test agent.",
            model="test-model",
            tool_policy="ask",
            position_x=0,
            position_y=0,
        )

    def get_or_create_conversation(self, node_id: str, project_id: str) -> str:
        self.conversation_created = True
        return _CONVERSATION_ID

    def get_conversation_for_node(self, node_id: str) -> str | None:
        if node_id != _NODE_ID:
            return None
        return _CONVERSATION_ID if self.conversation_created else None

    def list_inbound_context(self, node_id: str) -> list:
        return []

    def list_inbound_environment_node_ids(self, node_id: str) -> list[str]:
        return []

    def list_inbound_tool_node_ids(self, node_id: str) -> list[str]:
        return []

    def list_inbound(self, node_id: str) -> Inbound:
        return Inbound([], [], [])

    def list_messages(self, conversation_id: str, limit=50) -> list[Message]:
        return list(self.messages)

    def add_message(self, conversation_id: str, role: str, content: str, **kwargs) -> Message:
        message = Message(
            id=str(uuid4()),
            role=role,
            content=content,
            seq=len(self.messages),
            status=kwargs.get("status", "complete"),
            created_at="2026-09-10T00:00:00Z",
        )
        self.messages.append(message)
        return message

    def update_message(self, message_id: str, **fields) -> Message:
        for i, m in enumerate(self.messages):
            if m.id == message_id:
                updated = Message(
                    id=m.id,
                    role=m.role,
                    content=fields.get("content", m.content),
                    seq=m.seq,
                    status=fields.get("status", m.status),
                    created_at=m.created_at,
                    tool_calls=fields.get("tool_calls", m.tool_calls),
                )
                self.messages[i] = updated
                return updated
        raise KeyError(message_id)

    def set_agent_status(self, node_id: str, status: str) -> None:
        pass

    def latest_message_with_status(self, conversation_id: str, status: str) -> Message | None:
        return next((m for m in reversed(self.messages) if m.status == status), None)


class _FakeEnvRepo:
    def get_environment_nodes(self, ids):
        return [n for n in map(self.get_environment_node, ids) if n is not None]

    def get_environment_node(self, node_id):
        return None


class _FakeToolRepo:
    def __init__(self) -> None:
        self.calls: dict[str, dict] = {}
        self.pending_run: str | None = None
        self.pending_run_at: datetime | None = None
        self.cancelled_statuses: list[str] | None = None

    def get_tool_nodes(self, ids):
        return [n for n in map(self.get_tool_node, ids) if n is not None]

    def get_tool_node(self, node_id: str):
        return None

    def secret_keys(self, node_id: str) -> list[str]:
        return []

    def secret_keys_for_nodes(self, ids):
        return {}

    def record_call(self, **kwargs) -> str:
        self.calls[kwargs["tool_call_id"]] = dict(kwargs)
        return kwargs["tool_call_id"]

    def set_calls_status(self, conversation_id, ids, status):
        for t in ids:
            self.finish_call_by_tool_call_id(conversation_id, t, status=status)

    def finish_call_by_tool_call_id(self, conversation_id, tool_call_id, *, status, **kwargs):
        row = self.calls.setdefault(tool_call_id, {"tool_call_id": tool_call_id})
        row["status"] = status

    def get_calls_by_tool_call_ids(self, conversation_id, ids):
        rows = {t: self.get_call_by_tool_call_id(conversation_id, t) for t in ids}
        return {t: r for t, r in rows.items() if r is not None}

    def get_call_by_tool_call_id(self, conversation_id, tool_call_id):
        return self.calls.get(tool_call_id)

    def set_pending_run(self, conversation_id: str, payload: str | None) -> None:
        self.pending_run = payload
        self.pending_run_at = datetime.now(UTC) if payload else None

    def get_pending_run(self, conversation_id: str):
        if not self.pending_run or not self.pending_run_at:
            return None
        return self.pending_run, self.pending_run_at

    def cancel_calls(self, conversation_id: str, statuses: list[str]) -> None:
        self.cancelled_statuses = statuses


def _override_auth():
    return AuthContext(
        user=UserResponse(id="user-1", email="u@example.com"),
        token="fake-token",  # noqa: S106 - test fixture, not a real credential
    )


@pytest.fixture
def client_with_fakes(monkeypatch):
    chat_repo = _FakeChatRepo()
    tool_repo = _FakeToolRepo()

    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_project_repository] = lambda: chat_repo
    app.dependency_overrides[get_tool_repository] = lambda: tool_repo
    app.dependency_overrides[get_environment_repository] = lambda: _FakeEnvRepo()
    app.dependency_overrides[get_turn_repositories] = lambda: TurnRepositories(
        project=chat_repo, tool=tool_repo, env=_FakeEnvRepo(), user_id="user-1"
    )
    try:
        yield TestClient(app), chat_repo, tool_repo
    finally:
        app.dependency_overrides.clear()


def _script_answer(messages: list[ModelMessage], info: AgentInfo):
    return ModelResponse(parts=[TextPart(content="done")])


def _use_model(monkeypatch, script) -> None:
    def fake_get_agent_for(system_prompt: str, model: str):
        return Agent(FunctionModel(script), output_type=[str, DeferredToolRequests])

    monkeypatch.setattr(workflows, "get_agent_for", fake_get_agent_for)


def _use_gated_streaming_model(monkeypatch, event: threading.Event, text: str = "partial") -> None:
    """A stream function that yields one chunk, then blocks until `event` is set."""
    import asyncio

    async def stream(messages: list[ModelMessage], info: AgentInfo):
        yield text

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, event.wait)
        yield " done"

    def fake_get_agent_for(system_prompt: str, model: str):
        model_obj = FunctionModel(_script_answer, stream_function=stream)
        return Agent(model_obj, output_type=[str, DeferredToolRequests])

    monkeypatch.setattr(workflows, "get_agent_for", fake_get_agent_for)


# -- cancel -------------------------------------------------------------------


def test_cancel_unknown_node_404(client_with_fakes):
    client, chat_repo, tool_repo = client_with_fakes
    response = client.post("/chat/cancel", json={"node_id": _OTHER_NODE_ID})
    assert response.status_code == 404


def test_cancel_nothing_running_409(client_with_fakes):
    client, chat_repo, tool_repo = client_with_fakes
    response = client.post("/chat/cancel", json={"node_id": _NODE_ID})
    assert response.status_code == 409
    assert response.json()["detail"] == "Nothing running"


def test_cancel_running_202(client_with_fakes, monkeypatch):
    client, chat_repo, tool_repo = client_with_fakes
    gate = threading.Event()
    _use_gated_streaming_model(monkeypatch, gate)

    result = {}

    def run_stream():
        with client.stream("POST", "/chat/stream", json={"node_id": _NODE_ID, "prompt": "hi"}) as r:
            result["status"] = r.status_code
            for _ in r.iter_lines():
                pass

    thread = threading.Thread(target=run_stream)
    thread.start()
    try:
        # Wait for the run to register and the assistant row to exist.
        deadline = time.monotonic() + 5
        running_message = None
        while time.monotonic() < deadline:
            assistants = [m for m in chat_repo.messages if m.role == "assistant"]
            if assistants:
                running_message = assistants[-1]
                break
            time.sleep(0.02)
        assert running_message is not None

        response = client.post("/chat/cancel", json={"node_id": _NODE_ID})
        assert response.status_code == 202
        body = response.json()
        assert body["message_id"] == running_message.id
        assert body["node_id"] == _NODE_ID
        assert body["conversation_id"] == _CONVERSATION_ID
    finally:
        gate.set()
        thread.join(timeout=5)


def test_cancel_paused_202(client_with_fakes):
    client, chat_repo, tool_repo = client_with_fakes
    chat_repo.get_or_create_conversation(_NODE_ID, _PROJECT_ID)
    awaiting = chat_repo.add_message(
        _CONVERSATION_ID, "assistant", "partial", status="awaiting_approval"
    )
    tool_repo.set_pending_run(_CONVERSATION_ID, "[]")

    response = client.post("/chat/cancel", json={"node_id": _NODE_ID})

    assert response.status_code == 202
    body = response.json()
    assert body["message_id"] == awaiting.id
    assert tool_repo.pending_run is None


# -- attach ---------------------------------------------------------------


def test_attach_204_when_idle(client_with_fakes):
    client, chat_repo, tool_repo = client_with_fakes
    response = client.get(f"/chat/attach?node_id={_NODE_ID}")
    assert response.status_code == 204


def test_attach_unknown_node_404(client_with_fakes):
    client, chat_repo, tool_repo = client_with_fakes
    response = client.get(f"/chat/attach?node_id={_OTHER_NODE_ID}")
    assert response.status_code == 404


def test_attach_204_when_run_has_no_message_yet(client_with_fakes):
    """register() runs before the first DB insert: message is None for a
    moment. attach must treat that as nothing to join, not 500 on
    run.message.id.
    """
    client, chat_repo, tool_repo = client_with_fakes
    chat_repo.get_or_create_conversation(_NODE_ID, _PROJECT_ID)

    run = RunningTurn(
        conversation_id=_CONVERSATION_ID,
        node_id=_NODE_ID,
        project_id=_PROJECT_ID,
        model="test-model",
    )
    runs.register(run)

    response = client.get(f"/chat/attach?node_id={_NODE_ID}")
    assert response.status_code == 204


async def test_attach_snapshot_then_tail(client_with_fakes):
    """Attach mid-run: snapshot carries the partial text, then live events tail.

    Exercises chat_attach's route logic (node lookup, conversation lookup,
    runs.get) plus the shared ``_events``/``attach_events`` generator
    directly, rather than through a real HTTP call: starlette's TestClient
    buffers an entire streaming ASGI response before ``client.stream(...)``
    yields any line (its transport's ``handle_request`` blocks on
    ``portal.call(self.app, ...)`` until the response completes), so a
    genuinely mid-stream read is not observable through it. Driving the
    RunningTurn registry directly and calling the route coroutine covers the
    same logic without fighting that transport.
    """
    client, chat_repo, tool_repo = client_with_fakes
    chat_repo.get_or_create_conversation(_NODE_ID, _PROJECT_ID)
    user_message = chat_repo.add_message(_CONVERSATION_ID, "user", "hi")
    assistant_message = chat_repo.add_message(_CONVERSATION_ID, "assistant", "", status="running")

    run = RunningTurn(
        conversation_id=_CONVERSATION_ID,
        node_id=_NODE_ID,
        project_id=_PROJECT_ID,
        model="test-model",
    )
    run.user_message = user_message
    run.message = assistant_message
    run.text.append("partial")
    runs.register(run)
    response = None
    try:
        response = await chat_attach(node_id=UUID(_NODE_ID), repo=chat_repo)
        assert response.status_code == 200

        events = []
        async for chunk in response.body_iterator:
            events.append(chunk)
            if len(events) >= 1:
                break
        snapshot = "".join(events)
        assert "event: start" in snapshot
        assert "partial" in snapshot

        await runs.close(run, "done", {"assistant_message": {"id": assistant_message.id}})
        async for chunk in response.body_iterator:
            events.append(chunk)
            if "event: done" in chunk:
                break
        assert "event: done" in "".join(events)
    finally:
        if response is not None:
            await response.body_iterator.aclose()
        runs.unregister(_CONVERSATION_ID)


# -- busy -------------------------------------------------------------------


def test_chat_busy_409(client_with_fakes, monkeypatch):
    client, chat_repo, tool_repo = client_with_fakes
    gate = threading.Event()
    _use_gated_streaming_model(monkeypatch, gate)

    def run_stream():
        with client.stream("POST", "/chat/stream", json={"node_id": _NODE_ID, "prompt": "hi"}) as r:
            for _ in r.iter_lines():
                pass

    thread = threading.Thread(target=run_stream)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if any(m.role == "assistant" for m in chat_repo.messages):
                break
            time.sleep(0.02)

        response = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "again"})
        assert response.status_code == 409
        assert response.json()["detail"] == "Agent is already running a turn"
    finally:
        gate.set()
        thread.join(timeout=5)


def test_stream_start_carries_assistant_message(client_with_fakes, monkeypatch):
    client, chat_repo, tool_repo = client_with_fakes
    _use_model(monkeypatch, _script_answer)

    with client.stream("POST", "/chat/stream", json={"node_id": _NODE_ID, "prompt": "hi"}) as r:
        assert r.status_code == 200
        first_data = None
        for line in r.iter_lines():
            if line.startswith("data:"):
                first_data = line[len("data:") :].strip()
                break
        assert first_data is not None
        payload = json.loads(first_data)
        assert "assistant_message" in payload
        assert payload["assistant_message"]["role"] == "assistant"


# -- resume -------------------------------------------------------------------


def test_resume_without_awaiting_row_409_and_keeps_pending_run(client_with_fakes):
    """A resume can land between on_paused's pending_run write and the row
    flip, while a turn is legitimately pausing again. The old branch cleared
    pending_run here, destroying the parked history of that pause. It must
    just 409 and leave pending_run alone.
    """
    client, chat_repo, tool_repo = client_with_fakes
    chat_repo.get_or_create_conversation(_NODE_ID, _PROJECT_ID)
    tool_call_id = "call_1"
    tool_repo.calls[tool_call_id] = {"tool_call_id": tool_call_id, "status": "pending_approval"}
    tool_repo.set_pending_run(_CONVERSATION_ID, "[]")
    # No awaiting_approval row: latest_message_with_status returns None.

    response = client.post(
        "/chat/resume", json={"node_id": _NODE_ID, "approvals": {tool_call_id: True}}
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "No pending approval"
    assert tool_repo.pending_run is not None
