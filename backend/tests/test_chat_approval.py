"""The approval pause: detecting it, parking it, and resuming it.

Uses FunctionModel to script a model that calls an approval-required tool, so
no network and no database is touched. ``get_agent_for`` is monkeypatched at
the ``app.workflows`` import site to hand back an agent built on that model,
since the real one needs a Gemini key.
"""

import dataclasses
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.toolsets import ApprovalRequiredToolset, FunctionToolset

import app.workflows as workflows
from app.main import app
from app.repositories.project_repo import Inbound, Message, Node
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.deps import (
    TurnRepositories,
    get_environment_repository,
    get_project_repository,
    get_tool_repository,
    get_turn_repositories,
)
from app.services.turns import _record_pending_calls

_NODE_ID = "22222222-2222-2222-2222-222222222222"
_PROJECT_ID = "11111111-1111-1111-1111-111111111111"
_CONVERSATION_ID = "33333333-3333-3333-3333-333333333333"
_TOOL_NODE_ID = "44444444-4444-4444-4444-444444444444"


def _sse(text: str) -> dict[str, dict]:
    """Last payload per SSE event name."""
    out = {}
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out[lines["event"]] = json.loads(lines["data"])
    return out


def _working_tool() -> str:
    return "search results"


def _build_toolset() -> ApprovalRequiredToolset:
    functions = FunctionToolset()
    functions.add_function(_working_tool, name="working_tool")
    return ApprovalRequiredToolset(functions)


def _script_call_then_answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Call working_tool once, then answer once it sees a result or denial."""
    tool_calls = [p for m in messages for p in m.parts if isinstance(p, ToolCallPart)]
    resolved = [
        p for m in messages for p in m.parts if isinstance(p, ToolReturnPart | RetryPromptPart)
    ]
    if not tool_calls:
        return ModelResponse(parts=[ToolCallPart(tool_name="working_tool", args={})])
    if len(resolved) < len(tool_calls):
        return ModelResponse(parts=[])
    return ModelResponse(parts=[TextPart(content="done")])


def _script_call_twice_then_answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Call working_tool, then call it again, then answer. Used to test a
    second pause on resume.
    """
    tool_calls = [p for m in messages for p in m.parts if isinstance(p, ToolCallPart)]
    resolved = [
        p for m in messages for p in m.parts if isinstance(p, ToolReturnPart | RetryPromptPart)
    ]
    if len(resolved) < len(tool_calls):
        return ModelResponse(parts=[ToolCallPart(tool_name="working_tool", args={})])
    if len(tool_calls) < 2:
        return ModelResponse(parts=[ToolCallPart(tool_name="working_tool", args={})])
    return ModelResponse(parts=[TextPart(content="done")])


class _FakeChatRepo:
    """In-memory stand-in for ChatRepository."""

    def __init__(self) -> None:
        self.messages: list[Message] = []
        # Live tool_policy per node, as LivePolicyToolset reads it.
        self.policies: dict[str, str] = {_NODE_ID: "ask"}

    def get_tool_policy(self, node_id: str) -> str | None:
        return self.policies.get(node_id)

    def tool_policies(self, node_ids):
        kinds = {_NODE_ID: "agent", _TOOL_NODE_ID: "tool"}
        return {
            i: (kinds.get(i, "environment"), self.policies.get(i, "ask"))
            for i in node_ids
            if i in kinds or i in self.policies
        }

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
            tool_policy=self.policies[_NODE_ID],
            position_x=0,
            position_y=0,
        )

    def get_or_create_conversation(self, node_id: str, project_id: str) -> str:
        return _CONVERSATION_ID

    def get_conversation_for_node(self, node_id: str) -> str | None:
        return _CONVERSATION_ID if node_id == _NODE_ID else None

    def list_inbound_context(self, node_id: str) -> list:
        return []

    def list_inbound_environment_node_ids(self, node_id: str) -> list[str]:
        return []

    def list_inbound_tool_node_ids(self, node_id: str) -> list[str]:
        return [_TOOL_NODE_ID]

    def list_inbound(self, node_id: str) -> Inbound:
        return Inbound([], [_FakeToolNode()], [])

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


class _FakeToolNode:
    id = _TOOL_NODE_ID
    status = "ready"
    tool_slug = "fake_slug"


class _FakeEnvRepo:
    """No environments in these cases: every lookup misses."""

    def get_environment_nodes(self, ids):
        return [n for n in map(self.get_environment_node, ids) if n is not None]

    def get_environment_node(self, node_id):
        return None


class _FakeToolRepo:
    """In-memory stand-in for ToolRepository. No database, no vault.

    record_call mirrors the real repository's select-then-update-or-insert
    behaviour (tool_repo.py), so a regression that reintroduces a bare
    INSERT would show up here the same way it does against Postgres: as a
    duplicate-key violation on (conversation_id, tool_call_id), keyed by
    tool_call_id alone since tests use a single fixed conversation id.
    """

    def __init__(self) -> None:
        self.calls: dict[str, dict] = {}
        self.pending_run: str | None = None
        self.pending_run_at: datetime | None = None

    # -- toolset assembly is bypassed entirely: prepare_turn calls assemble(),
    # which needs a real spec. Tests monkeypatch assemble directly instead of
    # routing fake tool nodes through the registry.

    def get_tool_nodes(self, ids):
        return [n for n in map(self.get_tool_node, ids) if n is not None]

    def get_tool_node(self, node_id: str):
        return _FakeToolNode() if node_id == _TOOL_NODE_ID else None

    def secret_keys(self, node_id: str) -> list[str]:
        return []

    def secret_keys_for_nodes(self, ids):
        return {}

    def record_call(
        self,
        *,
        project_id,
        conversation_id,
        agent_node_id,
        tool_node_id,
        tool_call_id,
        tool_name,
        arguments,
        status,
    ) -> str:
        existing = self.calls.get(tool_call_id)
        if existing is not None:
            existing["status"] = status
            existing["arguments"] = arguments
            return tool_call_id
        self.calls[tool_call_id] = {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "status": status,
            "tool_node_id": tool_node_id,
            "duration_ms": None,
        }
        return tool_call_id

    def finish_call(self, call_id, *, status, result=None, error=None, duration_ms=None):
        row = self.calls.setdefault(call_id, {"tool_call_id": call_id})
        row["status"] = status
        if result is not None:
            row["result"] = result
        if error is not None:
            row["error"] = error
        if duration_ms is not None:
            row["duration_ms"] = duration_ms

    def get_calls_by_tool_call_ids(self, conversation_id, ids):
        rows = {t: self.get_call_by_tool_call_id(conversation_id, t) for t in ids}
        return {t: r for t, r in rows.items() if r is not None}

    def get_call_by_tool_call_id(self, conversation_id, tool_call_id):
        return self.calls.get(tool_call_id)

    def set_calls_status(self, conversation_id, ids, status):
        for t in ids:
            self.finish_call_by_tool_call_id(conversation_id, t, status=status)

    def finish_call_by_tool_call_id(
        self, conversation_id, tool_call_id, *, status, result=None, error=None
    ):
        row = self.calls.setdefault(tool_call_id, {"tool_call_id": tool_call_id})
        row["status"] = status
        if result is not None:
            row["result"] = result
        if error is not None:
            row["error"] = error

    def set_pending_run(self, conversation_id: str, payload: str | None) -> None:
        self.pending_run = payload
        self.pending_run_at = datetime.now(UTC) if payload else None

    def get_pending_run(self, conversation_id: str):
        if not self.pending_run or not self.pending_run_at:
            return None
        return self.pending_run, self.pending_run_at


def _override_auth():
    return AuthContext(
        user=UserResponse(id="user-1", email="u@example.com"),
        token="fake-token",  # noqa: S106 - test fixture, not a real credential
    )


@pytest.fixture
def fakes(monkeypatch):
    chat_repo = _FakeChatRepo()
    tool_repo = _FakeToolRepo()

    # Bypass the real tool registry: prepare_turn calls assemble(), which
    # needs a working ToolSpec. Tests only care that *a* toolset wrapped in
    # ApprovalRequiredToolset reaches record_calls.
    from app.tools.assembly import AssembledTools

    async def fake_assemble(repo, nodes, *, policy, start=None):
        return AssembledTools(
            toolsets=[_build_toolset()],
            owner_by_tool={"working_tool": _TOOL_NODE_ID},
            unavailable=[],
            owner_by_toolset=[_TOOL_NODE_ID],
        )

    monkeypatch.setattr("app.services.turns.assemble", fake_assemble)

    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_project_repository] = lambda: chat_repo
    app.dependency_overrides[get_tool_repository] = lambda: tool_repo
    app.dependency_overrides[get_environment_repository] = lambda: _FakeEnvRepo()
    app.dependency_overrides[get_turn_repositories] = lambda: TurnRepositories(
        project=chat_repo, tool=tool_repo, env=_FakeEnvRepo(), user_id="user-1"
    )
    try:
        yield chat_repo, tool_repo
    finally:
        app.dependency_overrides.clear()


def _replay(script):
    """Stream a sync script's response. The driver always streams now."""

    async def stream(messages: list[ModelMessage], info: AgentInfo):
        for i, part in enumerate(script(messages, info).parts):
            if isinstance(part, ToolCallPart):
                yield {i: DeltaToolCall(name=part.tool_name, json_args=part.args_as_json_str())}
            else:
                yield part.content

    return stream


def _use_model(monkeypatch, script) -> None:
    def fake_get_agent_for(system_prompt: str, model: str):
        return Agent(
            FunctionModel(script, stream_function=_replay(script)),
            output_type=[str, DeferredToolRequests],
        )

    monkeypatch.setattr(workflows, "get_agent_for", fake_get_agent_for)


async def _stream_call_then_answer(messages: list[ModelMessage], info: AgentInfo):
    """Streaming counterpart to _script_call_then_answer, for run_stream."""
    tool_calls = [p for m in messages for p in m.parts if isinstance(p, ToolCallPart)]
    resolved = [
        p for m in messages for p in m.parts if isinstance(p, ToolReturnPart | RetryPromptPart)
    ]
    if not tool_calls:
        yield {0: DeltaToolCall(name="working_tool", json_args="{}")}
        return
    if len(resolved) < len(tool_calls):
        return
    yield "done"


def _use_streaming_model(monkeypatch, script) -> None:
    def fake_get_agent_for(system_prompt: str, model: str):
        model_obj = FunctionModel(_script_call_then_answer, stream_function=script)
        return Agent(model_obj, output_type=[str, DeferredToolRequests])

    monkeypatch.setattr(workflows, "get_agent_for", fake_get_agent_for)


# -- auth and validation, from the brief -------------------------------------


def test_resume_requires_auth(client):
    response = client.post(
        "/chat/resume",
        json={
            "node_id": "11111111-1111-1111-1111-111111111111",
            "approvals": {"call_1": True},
        },
    )
    assert response.status_code == 401


def test_resume_rejects_empty_approvals(client):
    response = client.post(
        "/chat/resume",
        json={"node_id": "11111111-1111-1111-1111-111111111111", "approvals": {}},
    )
    assert response.status_code in (401, 422)


# -- pause detection -----------------------------------------------------------


def test_chat_pauses_and_records_pending_approval(client, fakes, monkeypatch):
    chat_repo, tool_repo = fakes
    _use_model(monkeypatch, _script_call_then_answer)

    response = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "search something"})

    assert response.status_code == 200
    body = response.json()
    assert body["paused"] is True
    assert len(body["pending_calls"]) == 1
    call = body["pending_calls"][0]
    assert call["tool_name"] == "working_tool"

    tool_call_id = call["tool_call_id"]
    assert tool_repo.calls[tool_call_id]["status"] == "pending_approval"
    assert tool_repo.pending_run is not None

    # No assistant message was persisted: the model never answered.
    # The bubble now exists, parked: the driver inserts it before the model runs.
    parked = [m for m in chat_repo.messages if m.role == "assistant"]
    assert [m.status for m in parked] == ["awaiting_approval"]


# -- resume: approve ----------------------------------------------------------


def test_resume_with_approval_completes_the_run(client, fakes, monkeypatch):
    chat_repo, tool_repo = fakes
    _use_model(monkeypatch, _script_call_then_answer)

    pause = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "search something"})
    tool_call_id = pause.json()["pending_calls"][0]["tool_call_id"]

    response = client.post(
        "/chat/resume",
        json={"node_id": _NODE_ID, "approvals": {tool_call_id: True}},
    )

    assert response.status_code == 200
    events = _sse(response.text)
    assert "approval_required" not in events
    assert events["done"]["assistant_message"]["content"] == "done"
    assert tool_repo.pending_run is None
    assert tool_repo.calls[tool_call_id]["status"] == "ok"
    assert any(m.role == "assistant" and m.content == "done" for m in chat_repo.messages)


def test_resume_with_approval_leaves_exactly_one_row_for_the_call(client, fakes, monkeypatch):
    """Regression: RecordingToolset re-enters record_call on resume for a
    call that already has a pending_approval row from the pause. That must
    move the existing row on to running then ok, never insert a second row
    for the same (conversation_id, tool_call_id), which the real database
    would reject with a unique constraint violation.
    """
    chat_repo, tool_repo = fakes
    _use_model(monkeypatch, _script_call_then_answer)

    pause = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "search something"})
    tool_call_id = pause.json()["pending_calls"][0]["tool_call_id"]
    assert len(tool_repo.calls) == 1

    response = client.post(
        "/chat/resume",
        json={"node_id": _NODE_ID, "approvals": {tool_call_id: True}},
    )

    assert response.status_code == 200
    assert _sse(response.text)["done"]["assistant_message"]["content"] == "done"
    # Exactly one row for this tool_call_id, not a duplicate insert, and it
    # ended in ok: pending_approval -> running -> ok.
    assert len(tool_repo.calls) == 1
    assert list(tool_repo.calls.keys()) == [tool_call_id]
    assert tool_repo.calls[tool_call_id]["status"] == "ok"


# -- resume: deny --------------------------------------------------------------


def test_resume_with_denial_records_denied_and_completes(client, fakes, monkeypatch):
    chat_repo, tool_repo = fakes
    _use_model(monkeypatch, _script_call_then_answer)

    pause = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "search something"})
    tool_call_id = pause.json()["pending_calls"][0]["tool_call_id"]

    response = client.post(
        "/chat/resume",
        json={"node_id": _NODE_ID, "approvals": {tool_call_id: False}},
    )

    assert response.status_code == 200
    assert _sse(response.text)["done"]["assistant_message"]["content"] == "done"
    assert len(tool_repo.calls) == 1
    assert tool_repo.calls[tool_call_id]["status"] == "denied"
    assert tool_repo.pending_run is None

    # The denial also closes the call event on the bubble, and survives the
    # resumed turn's own finalise write.
    row = [m for m in chat_repo.messages if m.role == "assistant"][-1]
    assert row.status == "complete"
    result = next(
        e for e in row.tool_calls if e["type"] == "result" and e["tool_call_id"] == tool_call_id
    )
    assert result["status"] == "denied"
    assert not [
        e
        for e in row.tool_calls
        if e["type"] == "call"
        and not any(
            r["type"] == "result" and r["tool_call_id"] == e["tool_call_id"] for r in row.tool_calls
        )
    ]


def test_resume_busy_leaves_no_denial_on_the_parked_row(client, fakes, monkeypatch):
    """A TurnBusy must not leave a call rendered denied while it is still pending."""
    from app.services import runs
    from app.services.runs import RunningTurn

    chat_repo, tool_repo = fakes
    _use_model(monkeypatch, _script_call_then_answer)

    pause = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "search something"})
    tool_call_id = pause.json()["pending_calls"][0]["tool_call_id"]

    # Occupy the conversation so start_turn raises TurnBusy.
    runs.register(
        RunningTurn(conversation_id=_CONVERSATION_ID, node_id=_NODE_ID, project_id="p", model="m")
    )
    try:
        response = client.post(
            "/chat/resume",
            json={"node_id": _NODE_ID, "approvals": {tool_call_id: False}},
        )
    finally:
        runs.unregister(_CONVERSATION_ID)

    assert response.status_code == 409
    row = [m for m in chat_repo.messages if m.role == "assistant"][-1]
    assert row.status == "awaiting_approval"
    assert not [e for e in row.tool_calls if e["type"] == "result"]
    assert tool_repo.calls[tool_call_id]["status"] == "pending_approval"


# -- resume: second pause -------------------------------------------------------


def test_resume_can_pause_again(client, fakes, monkeypatch):
    chat_repo, tool_repo = fakes
    _use_model(monkeypatch, _script_call_twice_then_answer)

    pause = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "search something"})
    first_call_id = pause.json()["pending_calls"][0]["tool_call_id"]

    response = client.post(
        "/chat/resume",
        json={"node_id": _NODE_ID, "approvals": {first_call_id: True}},
    )

    assert response.status_code == 200
    events = _sse(response.text)
    assert "done" not in events
    body = events["approval_required"]
    assert len(body["pending_calls"]) == 1
    second_call_id = body["pending_calls"][0]["tool_call_id"]
    assert second_call_id != first_call_id
    assert tool_repo.pending_run is not None
    assert tool_repo.calls[second_call_id]["status"] == "pending_approval"


# -- stale pending run ----------------------------------------------------------


def test_resume_with_stale_pending_run_gives_409(client, fakes, monkeypatch):
    chat_repo, tool_repo = fakes
    _use_model(monkeypatch, _script_call_then_answer)

    pause = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "search something"})
    tool_call_id = pause.json()["pending_calls"][0]["tool_call_id"]

    # Backdate the parked run past the one-hour window.
    tool_repo.pending_run_at = datetime.now(UTC) - timedelta(hours=2)

    response = client.post(
        "/chat/resume",
        json={"node_id": _NODE_ID, "approvals": {tool_call_id: True}},
    )

    assert response.status_code == 409
    assert tool_repo.pending_run is None


def test_resume_with_no_pending_run_gives_409(client, fakes):
    response = client.post(
        "/chat/resume",
        json={"node_id": _NODE_ID, "approvals": {"whatever": True}},
    )
    assert response.status_code == 409


# -- unknown tool_call_id ---------------------------------------------------


def test_resume_with_unknown_tool_call_id_gives_422(client, fakes, monkeypatch):
    chat_repo, tool_repo = fakes
    _use_model(monkeypatch, _script_call_then_answer)

    client.post("/chat", json={"node_id": _NODE_ID, "prompt": "search something"})

    response = client.post(
        "/chat/resume",
        json={"node_id": _NODE_ID, "approvals": {"not-a-real-call-id": True}},
    )

    assert response.status_code == 422


# -- the parked payload actually round-trips through ModelMessagesTypeAdapter --


def test_pending_run_payload_is_valid_model_messages_json(client, fakes, monkeypatch):
    chat_repo, tool_repo = fakes
    _use_model(monkeypatch, _script_call_then_answer)

    client.post("/chat", json={"node_id": _NODE_ID, "prompt": "search something"})

    history = ModelMessagesTypeAdapter.validate_json(tool_repo.pending_run)
    assert len(history) >= 2


# -- streaming: approval_required, no done event -------------------------------


def test_chat_stream_emits_approval_required_and_no_done(client, fakes, monkeypatch):
    chat_repo, tool_repo = fakes
    _use_streaming_model(monkeypatch, _stream_call_then_answer)

    response = client.post("/chat/stream", json={"node_id": _NODE_ID, "prompt": "search something"})

    assert response.status_code == 200
    body = response.text
    assert "event: approval_required" in body
    assert "event: done" not in body
    assert tool_repo.pending_run is not None
    # The bubble now exists, parked: the driver inserts it before the model runs.
    parked = [m for m in chat_repo.messages if m.role == "assistant"]
    assert [m.status for m in parked] == ["awaiting_approval"]


# -- resume's response tells the truth about who said what --------------------


def test_resume_response_has_assistant_message_and_no_user_message(client, fakes, monkeypatch):
    """Regression: resume must not attribute the assistant's reply to the user.

    ResumeResponse carries only assistant_message; there is no user prompt
    on a resume, so the field must not exist at all on the wire.
    """
    chat_repo, tool_repo = fakes
    _use_model(monkeypatch, _script_call_then_answer)

    pause = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "search something"})
    tool_call_id = pause.json()["pending_calls"][0]["tool_call_id"]

    response = client.post(
        "/chat/resume",
        json={"node_id": _NODE_ID, "approvals": {tool_call_id: True}},
    )

    assert response.status_code == 200
    events = _sse(response.text)
    assert "user_message" not in events["start"]
    assert events["done"]["assistant_message"]["role"] == "assistant"
    assert events["done"]["assistant_message"]["content"] == "done"


# -- an unmapped tool name gets no row, never a wrong one ----------------------


def test_record_pending_calls_skips_unmapped_tool_name():
    """A tool name absent from owner_by_tool must not produce a row at all,

    since a fabricated tool_node_id would be a wrong foreign key, silently
    believable and worse than a missing audit row.
    """
    tool_repo = _FakeToolRepo()
    part = ToolCallPart(tool_name="mystery_tool", args={}, tool_call_id="call_1")
    pending = DeferredToolRequests(approvals=[part])

    _record_pending_calls(
        tool_repo,
        pending,
        project_id=_PROJECT_ID,
        conversation_id=_CONVERSATION_ID,
        agent_node_id=_NODE_ID,
        owner_by_tool={},
    )

    assert tool_repo.calls == {}


def test_chat_pause_falls_back_to_owner_by_tool_only_when_no_row_exists(client, monkeypatch):
    """End to end: when RecordingToolset has already written the pending row
    (the normal case), _record_pending_calls must not touch it, and the row
    keeps the real tool_node_id RecordingToolset gave it, not a guess.
    """
    from app.tools.assembly import AssembledTools

    chat_repo = _FakeChatRepo()
    tool_repo = _FakeToolRepo()

    async def fake_assemble(repo, nodes, *, policy, start=None):
        return AssembledTools(
            toolsets=[_build_toolset()],
            # Not mapped: if _record_pending_calls's fallback ever ran
            # for this call, it would have nothing to guess with and
            # must skip rather than write a wrong tool_node_id.
            owner_by_tool={},
            unavailable=[],
            owner_by_toolset=[_TOOL_NODE_ID],
        )

    monkeypatch.setattr("app.services.turns.assemble", fake_assemble)
    _use_model(monkeypatch, _script_call_then_answer)

    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_project_repository] = lambda: chat_repo
    app.dependency_overrides[get_tool_repository] = lambda: tool_repo
    app.dependency_overrides[get_environment_repository] = lambda: _FakeEnvRepo()
    app.dependency_overrides[get_turn_repositories] = lambda: TurnRepositories(
        project=chat_repo, tool=tool_repo, env=_FakeEnvRepo(), user_id="user-1"
    )
    try:
        response = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "search something"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["paused"] is True
    # RecordingToolset (record_calls) wrote the row with the real tool node
    # id, which _record_pending_calls's fallback never had to guess at.
    tool_call_id = response.json()["pending_calls"][0]["tool_call_id"]
    assert tool_repo.calls[tool_call_id]["status"] == "pending_approval"
    assert tool_repo.calls[tool_call_id]["tool_node_id"] == _TOOL_NODE_ID
    assert tool_repo.calls[tool_call_id]["tool_node_id"] != _NODE_ID


# -- live tool policy -----------------------------------------------------------

_ENV_NODE_ID = "55555555-5555-5555-5555-555555555555"


def _live_fakes(monkeypatch, chat_repo, flip_to: str | None = None):
    """assemble honours the live policy prepare_turn hands it. The tool flips
    the agent's policy each time it runs when ``flip_to`` is set."""
    from app.tools.assembly import AssembledTools, LivePolicyToolset

    def working_tool() -> str:
        if flip_to is not None:
            chat_repo.policies[_NODE_ID] = flip_to
        return "search results"

    async def fake_assemble(repo, nodes, *, policy, start=None):
        functions = FunctionToolset()
        functions.add_function(working_tool, name="working_tool")
        return AssembledTools(
            toolsets=[LivePolicyToolset(functions, policy=policy)],
            owner_by_tool={"working_tool": _TOOL_NODE_ID},
            owner_by_toolset=[_TOOL_NODE_ID],
        )

    monkeypatch.setattr("app.services.turns.assemble", fake_assemble)


def _turn_repos(chat_repo, tool_repo) -> TurnRepositories:
    return TurnRepositories(project=chat_repo, tool=tool_repo, env=_FakeEnvRepo(), user_id="u")


def test_flip_to_ask_mid_run_pauses_the_next_call(client, fakes, monkeypatch):
    chat_repo, tool_repo = fakes
    chat_repo.policies[_NODE_ID] = "auto"
    _live_fakes(monkeypatch, chat_repo, flip_to="ask")
    _use_model(monkeypatch, _script_call_twice_then_answer)

    body = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "go"}).json()

    # First call ran under auto and flipped to ask; the second one asks.
    assert body["paused"] is True
    assert sorted(c["status"] for c in tool_repo.calls.values()) == ["ok", "pending_approval"]


def test_flip_to_auto_mid_run_runs_the_next_call(client, fakes, monkeypatch):
    chat_repo, tool_repo = fakes
    _live_fakes(monkeypatch, chat_repo, flip_to="auto")
    _use_model(monkeypatch, _script_call_twice_then_answer)

    pause = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "go"}).json()
    first = pause["pending_calls"][0]["tool_call_id"]
    # The approved call flips the agent to auto, so the second needs no approval.
    response = client.post("/chat/resume", json={"node_id": _NODE_ID, "approvals": {first: True}})

    events = _sse(response.text)
    assert "approval_required" not in events
    assert events["done"]["assistant_message"]["content"] == "done"
    assert [c["status"] for c in tool_repo.calls.values()] == ["ok", "ok"]


@pytest.mark.anyio
async def test_resume_if_auto_approves_everything_waiting(client, fakes, monkeypatch):
    from app.services import runs, turns

    chat_repo, tool_repo = fakes
    _live_fakes(monkeypatch, chat_repo)
    _use_model(monkeypatch, _script_call_then_answer)
    pause = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "go"}).json()
    call_id = pause["pending_calls"][0]["tool_call_id"]
    repos = _turn_repos(chat_repo, tool_repo)

    # Still ask: nothing moves.
    await turns.resume_if_auto(repos, chat_repo.get_agent_node(_NODE_ID))
    assert runs.get(_CONVERSATION_ID) is None

    chat_repo.policies[_NODE_ID] = "auto"
    await turns.resume_if_auto(repos, chat_repo.get_agent_node(_NODE_ID))
    run = runs.get(_CONVERSATION_ID)
    assert run is not None
    await run.task

    assert run.final[0] == "done"
    assert run.final[1]["assistant_message"]["content"] == "done"
    assert tool_repo.calls[call_id]["status"] == "ok"
    assert tool_repo.pending_run is None


def _park_two_calls(tool_repo) -> None:
    """A pause on one tool node call and one environment call."""
    history = [
        ModelResponse(
            parts=[
                ToolCallPart(tool_name="working_tool", args={}, tool_call_id="c-tool"),
                ToolCallPart(tool_name="env_run_command", args={}, tool_call_id="c-env"),
            ]
        )
    ]
    payload = ModelMessagesTypeAdapter.dump_json(history).decode()
    tool_repo.set_pending_run(_CONVERSATION_ID, payload)
    for call_id, owner in (("c-tool", _TOOL_NODE_ID), ("c-env", _ENV_NODE_ID)):
        tool_repo.record_call(
            project_id=_PROJECT_ID,
            conversation_id=_CONVERSATION_ID,
            agent_node_id=_NODE_ID,
            tool_node_id=owner,
            tool_call_id=call_id,
            tool_name="x",
            arguments={},
            status="pending_approval",
        )


@pytest.mark.anyio
async def test_mixed_pause_stays_paused_until_every_call_is_auto(fakes, monkeypatch):
    from app.services import turns

    chat_repo, tool_repo = fakes
    _park_two_calls(tool_repo)
    resumed = []

    async def fake_resume(repos, node, approvals):
        resumed.append(approvals)

    monkeypatch.setattr(turns, "resume_paused", fake_resume)
    repos = _turn_repos(chat_repo, tool_repo)
    node = chat_repo.get_agent_node(_NODE_ID)

    # The agent went auto, but the environment call still asks.
    chat_repo.policies.update({_NODE_ID: "auto", _ENV_NODE_ID: "ask"})
    await turns.resume_if_auto(repos, node)
    assert resumed == []

    # The environment call follows the environment, not the agent.
    chat_repo.policies.update({_NODE_ID: "ask", _ENV_NODE_ID: "auto"})
    await turns.resume_if_auto(repos, node)
    assert resumed == []

    chat_repo.policies[_NODE_ID] = "auto"
    await turns.resume_if_auto(repos, node)
    assert resumed == [{"c-tool": True, "c-env": True}]


@pytest.mark.anyio
async def test_env_flip_checks_every_agent_paused_on_it(fakes, monkeypatch):
    import asyncio

    from app.services import runs, turns

    chat_repo, tool_repo = fakes
    seen = []

    async def fake_if_auto(repos, node):
        seen.append(node.id)

    tool_repo.paused_agents_for_tool_node = lambda tool_node_id: [_NODE_ID, "gone"]
    monkeypatch.setattr(turns, "resume_if_auto", fake_if_auto)

    turns.resume_waiting(_turn_repos(chat_repo, tool_repo), env_id=_ENV_NODE_ID)
    await asyncio.gather(*runs._FINALISERS)

    # A deleted agent is skipped.
    assert seen == [_NODE_ID]


def test_patch_agent_to_auto_resumes_detached(client, fakes, monkeypatch):
    import app.routers.projects as projects

    chat_repo, _ = fakes

    def update_node(node_id, changes):
        chat_repo.policies[node_id] = changes.get("tool_policy", chat_repo.policies[node_id])
        return chat_repo.get_agent_node(node_id)

    chat_repo.update_node = update_node
    calls = []
    monkeypatch.setattr(projects, "resume_waiting", lambda repos, **kw: calls.append(kw))
    url = f"/projects/{_PROJECT_ID}/nodes/{_NODE_ID}"

    assert client.patch(url, json={"tool_policy": "ask"}).status_code == 200
    assert calls == []
    response = client.patch(url, json={"tool_policy": "auto"})
    assert response.status_code == 200
    assert response.json()["tool_policy"] == "auto"
    assert [kw["agent"].id for kw in calls] == [_NODE_ID]


def test_patch_environment_to_auto_resumes_detached(client, fakes, monkeypatch):
    import app.routers.environments as env_router
    from app.repositories.environment_repo import EnvNode

    env = EnvNode(
        id=_ENV_NODE_ID,
        project_id=_PROJECT_ID,
        name="Env",
        config={},
        status="ready",
        status_detail=None,
        tool_policy="ask",
        position_x=0.0,
        position_y=0.0,
    )

    class _Envs(_FakeEnvRepo):
        def get_environment_node(self, node_id):
            return env if node_id == _ENV_NODE_ID else None

        def update_environment_node(self, node_id, changes):
            return dataclasses.replace(env, **changes)

    app.dependency_overrides[get_environment_repository] = lambda: _Envs()
    calls = []
    monkeypatch.setattr(env_router, "resume_waiting", lambda repos, **kw: calls.append(kw))
    url = f"/projects/{_PROJECT_ID}/environments/{_ENV_NODE_ID}"

    assert client.patch(url, json={"name": "x"}).status_code == 200
    assert client.patch(url, json={"tool_policy": "auto"}).status_code == 200
    assert calls == [{"env_id": _ENV_NODE_ID}]
