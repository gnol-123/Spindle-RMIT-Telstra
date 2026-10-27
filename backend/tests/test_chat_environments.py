"""An environment reaching a real agent turn.

Scripted model, fake repositories, fake sandbox. Proves the wiring: the
toolset is assembled, a call is recorded against the environment node, and an
ask environment pauses the turn.
"""

from uuid import uuid4

from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.toolsets import FunctionToolset

from app import workflows
from app.environments import assembly as env_assembly
from app.environments.assembly import ENV_TOOL_NAMES, env_prefix
from app.environments.base import EnvSpec
from app.main import app
from app.repositories.environment_repo import EnvNode
from app.repositories.project_repo import Inbound, Message, Node
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.deps import (
    TurnRepositories,
    get_environment_repository,
    get_project_repository,
    get_tool_repository,
    get_turn_repositories,
)
from app.tools.base import VerifyResult

_PROJECT_ID = "11111111-1111-1111-1111-111111111111"
_NODE_ID = "22222222-2222-2222-2222-222222222222"
_ENV_ID = "33333333-3333-3333-3333-333333333333"
_CONVERSATION_ID = "44444444-4444-4444-4444-444444444444"
_USER_ID = "55555555-5555-5555-5555-555555555555"


def _override_auth():
    return AuthContext(user=UserResponse(id=_USER_ID, email="t@example.com"), token="tok")


def _env_node(**over) -> EnvNode:
    base = {
        "id": _ENV_ID,
        "project_id": _PROJECT_ID,
        "name": "Scratch Space",
        "config": {"runtime": "e2b", "role": "scratch", "sandbox_id": "sbx_1"},
        "status": "ready",
        "status_detail": None,
        "tool_policy": "auto",
        "position_x": 0.0,
        "position_y": 0.0,
    }
    base.update(over)
    return EnvNode(**base)


class _FakeChatRepo:
    def __init__(self, env_node=None):
        self.env_node = env_node
        self.messages: list[Message] = []

    def get_agent_node(self, node_id):
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

    def get_or_create_conversation(self, node_id, project_id):
        return _CONVERSATION_ID

    def get_tool_policy(self, node_id):
        n = self.env_node
        return n.tool_policy if n is not None and n.id == node_id else None

    def get_conversation_for_node(self, node_id):
        return _CONVERSATION_ID

    def list_inbound_context(self, node_id):
        return []

    def list_inbound_tool_node_ids(self, node_id):
        return []

    def list_inbound_environment_node_ids(self, node_id):
        return [_ENV_ID]

    def list_inbound(self, node_id):
        return Inbound([], [], [self.env_node] if self.env_node else [])

    def list_messages(self, conversation_id, limit=50):
        return list(self.messages)

    def add_message(self, conversation_id, role, content, **kwargs):
        message = Message(
            id=str(uuid4()),
            role=role,
            content=content,
            seq=len(self.messages),
            status=kwargs.get("status", "complete"),
            created_at="2026-09-13T00:00:00Z",
        )
        self.messages.append(message)
        return message

    def update_message(self, message_id, **fields):
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

    def set_agent_status(self, node_id, status):
        pass

    def latest_message_with_status(self, conversation_id, status):
        return next((m for m in reversed(self.messages) if m.status == status), None)


class _FakeToolRepo:
    """Records tool_calls rows. No database."""

    def __init__(self):
        self.calls: list[dict] = []
        self.pending_run: str | None = None

    def get_tool_nodes(self, ids):
        return [n for n in map(self.get_tool_node, ids) if n is not None]

    def get_tool_node(self, node_id):
        return None

    def record_call(self, **kwargs):
        self.calls.append(dict(kwargs))
        return f"call-{len(self.calls)}"

    def finish_call(self, call_id, **kwargs):
        return None

    def get_calls_by_tool_call_ids(self, conversation_id, ids):
        rows = {t: self.get_call_by_tool_call_id(conversation_id, t) for t in ids}
        return {t: r for t, r in rows.items() if r is not None}

    def get_call_by_tool_call_id(self, conversation_id, tool_call_id):
        for call in self.calls:
            if call.get("tool_call_id") == tool_call_id:
                return call
        return None

    def set_calls_status(self, conversation_id, ids, status):
        for t in ids:
            self.finish_call_by_tool_call_id(conversation_id, t, status=status)

    def finish_call_by_tool_call_id(self, conversation_id, tool_call_id, **kwargs):
        return None

    def set_pending_run(self, conversation_id, payload):
        self.pending_run = payload


class _FakeEnvRepo:
    def __init__(self, node: EnvNode):
        self.node = node

    def get_environment_nodes(self, ids):
        return [n for n in map(self.get_environment_node, ids) if n is not None]

    def get_environment_node(self, node_id):
        return self.node if node_id == self.node.id else None

    def set_status(self, node_id, status, detail):
        return None


def _install_env_spec(monkeypatch, *, run_output: str = "hello from the sandbox"):
    """A spec whose run_command returns a fixed string."""

    def _build(ctx):
        ts = FunctionToolset()

        async def run_command(command: str, timeout_seconds: int | None = None) -> str:
            return run_output

        async def read_file(path: str) -> str:
            return ""

        async def write_file(path: str, content: str) -> str:
            return "written"

        async def list_files(path: str = ".") -> str:
            return ""

        async def next_free_port() -> str:
            return "3000"

        async def publish_preview(port: int, title: str, path: str = "/") -> str:
            return "published"

        for fn, name in zip(
            (run_command, read_file, write_file, list_files, next_free_port, publish_preview),
            ENV_TOOL_NAMES,
            strict=True,
        ):
            ts.add_function(fn, name=name, description=name)
        return ts

    async def _noop(*_a, **_k):
        return None

    async def _verify(ctx):
        return VerifyResult(ok=True, detail="Sandbox running")

    spec = EnvSpec(runtime="e2b", provision=_noop, build=_build, verify=_verify, teardown=_noop)
    monkeypatch.setattr(env_assembly, "get_spec", lambda runtime: spec)


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


def _script_call_then_answer(prefix: str):
    """Call the environment's run_command, then answer with its output."""

    def script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart(f"{prefix}_run_command", {"command": "echo hi"})]
            )
        return ModelResponse(parts=[TextPart("The sandbox said hello.")])

    return script


def _capture_instructions(seen: dict):
    """A script that records the per turn instructions, then answers.

    Instructions passed to Agent.run(instructions=...) arrive on AgentInfo,
    not as a system-prompt part: the agent's own system_prompt is the part.
    """

    def script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen["instructions"] = info.instructions or ""
        return ModelResponse(parts=[TextPart("ok")])

    return script


def _use(chat_repo, tool_repo, env_repo):
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_project_repository] = lambda: chat_repo
    app.dependency_overrides[get_tool_repository] = lambda: tool_repo
    app.dependency_overrides[get_environment_repository] = lambda: env_repo
    app.dependency_overrides[get_turn_repositories] = lambda: TurnRepositories(
        project=chat_repo, tool=tool_repo, env=env_repo, user_id=_USER_ID
    )


def test_an_environment_tool_call_is_recorded_against_the_environment_node(client, monkeypatch):
    node = _env_node(tool_policy="auto")
    _install_env_spec(monkeypatch)
    _use_model(monkeypatch, _script_call_then_answer(env_prefix(node.name, node.id)))

    chat_repo, tool_repo, env_repo = _FakeChatRepo(node), _FakeToolRepo(), _FakeEnvRepo(node)
    _use(chat_repo, tool_repo, env_repo)
    try:
        response = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "run something"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert tool_repo.calls, "the environment call was not recorded"
    assert tool_repo.calls[0]["tool_node_id"] == _ENV_ID
    assert tool_repo.calls[0]["tool_name"].endswith("run_command")


def test_an_ask_environment_pauses_the_turn(client, monkeypatch):
    """The environment's own policy drives approval, not the agent's."""
    node = _env_node(tool_policy="ask")
    _install_env_spec(monkeypatch)
    _use_model(monkeypatch, _script_call_then_answer(env_prefix(node.name, node.id)))

    chat_repo, tool_repo, env_repo = _FakeChatRepo(node), _FakeToolRepo(), _FakeEnvRepo(node)
    _use(chat_repo, tool_repo, env_repo)
    try:
        response = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "run something"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["paused"] is True
    pending = body["pending_calls"][0]
    assert pending["tool_name"].endswith("run_command")
    # The prefixed name resolved to an owner, so the row is attributable.
    assert tool_repo.calls[0]["tool_node_id"] == _ENV_ID


def test_the_environment_note_reaches_the_model(client, monkeypatch):
    node = _env_node(tool_policy="auto")
    _install_env_spec(monkeypatch)

    seen: dict = {}
    _use_model(monkeypatch, _capture_instructions(seen))

    chat_repo, tool_repo, env_repo = _FakeChatRepo(node), _FakeToolRepo(), _FakeEnvRepo(node)
    _use(chat_repo, tool_repo, env_repo)
    try:
        client.post("/chat", json={"node_id": _NODE_ID, "prompt": "hello"})
    finally:
        app.dependency_overrides.clear()

    assert "Scratch Space" in seen.get("instructions", "")


def test_a_stopped_environment_is_reported_unavailable(client, monkeypatch):
    node = _env_node(status="stopped", config={"runtime": "e2b", "role": "scratch"})
    _install_env_spec(monkeypatch)

    seen: dict = {}
    _use_model(monkeypatch, _capture_instructions(seen))

    chat_repo, tool_repo, env_repo = _FakeChatRepo(node), _FakeToolRepo(), _FakeEnvRepo(node)
    _use(chat_repo, tool_repo, env_repo)
    try:
        response = client.post("/chat", json={"node_id": _NODE_ID, "prompt": "hello"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "unavailable" in seen.get("instructions", "").lower()
