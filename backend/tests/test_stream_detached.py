"""A streamed turn finishes and persists even when the reader leaves."""

import asyncio

import pytest
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.toolsets import ApprovalRequiredToolset, FunctionToolset

import app.workflows as workflows
from app.repositories.project_repo import Message
from app.services import runs


@pytest.fixture(autouse=True)
def clean():
    runs._RUNS.clear()
    yield
    runs._RUNS.clear()


class _Repo:
    def __init__(self):
        self.added = []
        self.updates = []
        self.node_status = []

    def list_messages(self, conversation_id, limit=50):
        return []

    def add_message(self, conversation_id, role, content, **kw):
        self.added.append((role, content, kw.get("status", "complete")))
        return Message(
            id=f"m{len(self.added)}",
            role=role,
            content=content,
            seq=len(self.added),
            status=kw.get("status", "complete"),
            created_at="t",
        )

    def update_message(self, message_id, **fields):
        self.updates.append((message_id, fields))
        return Message(
            id=message_id,
            role="assistant",
            content=fields.get("content", ""),
            seq=2,
            status=fields.get("status", "running"),
            created_at="t",
            tool_calls=fields.get("tool_calls", []),
        )

    def set_agent_status(self, node_id, status):
        self.node_status.append(status)

    def latest_message_with_status(self, conversation_id, status):
        return None


def _unused(messages, info):
    raise AssertionError("the sync path is never taken in these tests")


def _use_stream(monkeypatch, stream_fn, sync_fn=_unused):
    def fake(system_prompt, model):
        return Agent(
            FunctionModel(sync_fn, stream_function=stream_fn),
            name="t",
            output_type=[str, DeferredToolRequests],
        )

    monkeypatch.setattr(workflows, "get_agent_for", fake)


gate = asyncio.Event()


async def _slow(messages, info):
    yield "first"
    await gate.wait()
    yield " second"


@pytest.mark.anyio
async def test_reader_leaves_turn_still_persists(monkeypatch):
    _use_stream(monkeypatch, _slow)
    repo = _Repo()
    gate.clear()

    async for event, _ in workflows.stream_turn(
        repo, "c", "sys", "m", "hi", node_id="n", project_id="p"
    ):
        if event == "chunk":
            break  # client gone

    task = runs.get("c").task
    gate.set()
    await task

    assert [r for r, *_ in repo.added] == ["user", "assistant"]
    # The reply lands on the running row now, not as a second insert.
    assert repo.updates[-1][1]["content"] == "first second"


def _script_call_then_answer(messages: list[ModelMessage], info: AgentInfo):
    from pydantic_ai.messages import ModelResponse, TextPart

    tool_calls = [p for m in messages for p in m.parts if isinstance(p, ToolCallPart)]
    resolved = [
        p for m in messages for p in m.parts if isinstance(p, ToolReturnPart | RetryPromptPart)
    ]
    if not tool_calls:
        return ModelResponse(parts=[ToolCallPart(tool_name="needs_ok", args={})])
    if len(resolved) < len(tool_calls):
        return ModelResponse(parts=[])
    return ModelResponse(parts=[TextPart(content="done")])


async def _stream_call_then_answer(messages: list[ModelMessage], info: AgentInfo):
    tool_calls = [p for m in messages for p in m.parts if isinstance(p, ToolCallPart)]
    resolved = [
        p for m in messages for p in m.parts if isinstance(p, ToolReturnPart | RetryPromptPart)
    ]
    if not tool_calls:
        yield {0: DeltaToolCall(name="needs_ok", json_args="{}")}
        return
    if len(resolved) < len(tool_calls):
        return
    yield "done"


@pytest.mark.anyio
async def test_on_paused_runs_inside_task(monkeypatch):
    def needs_ok() -> str:
        return "ok"

    toolset = ApprovalRequiredToolset(FunctionToolset([needs_ok]))
    _use_stream(monkeypatch, _stream_call_then_answer, _script_call_then_answer)
    repo = _Repo()
    parked = []

    async def on_paused(pending, all_messages):
        parked.append(pending.approvals[0].tool_name)

    events = [
        e
        async for e, _ in workflows.stream_turn(
            repo,
            "c",
            "sys",
            "m",
            "hi",
            node_id="n",
            project_id="p",
            toolsets=[toolset],
            on_paused=on_paused,
        )
    ]

    assert events[-1] == "paused"
    assert parked == ["needs_ok"]
    # The bubble is inserted up front and parked as awaiting_approval.
    assert [r for r, *_ in repo.added] == ["user", "assistant"]
    assert repo.updates[-1][1]["status"] == "awaiting_approval"


@pytest.mark.anyio
async def test_tool_events_are_forwarded(monkeypatch):
    """A tool call and its result both reach the stream as ``tool`` events."""

    def needs_ok() -> str:
        return "ok"

    _use_stream(monkeypatch, _stream_call_then_answer, _script_call_then_answer)
    repo = _Repo()

    seen = [
        (e, p)
        async for e, p in workflows.stream_turn(
            repo,
            "c",
            "sys",
            "m",
            "hi",
            node_id="n",
            project_id="p",
            toolsets=[FunctionToolset([needs_ok])],
        )
    ]

    tools = [p for e, p in seen if e == "tool"]
    assert [t["name"] for t in tools] == ["needs_ok", "needs_ok"]
    assert tools[0]["args"] == {}
    assert tools[1]["result_head"] == "ok"
    assert seen[-1][0] == "done"


@pytest.mark.anyio
async def test_on_paused_failure_writes_no_assistant_row(monkeypatch):
    """Parking bookkeeping blew up. The pause still ends the turn cleanly."""

    def needs_ok() -> str:
        return "ok"

    toolset = ApprovalRequiredToolset(FunctionToolset([needs_ok]))
    _use_stream(monkeypatch, _stream_call_then_answer, _script_call_then_answer)
    repo = _Repo()

    async def on_paused(pending, all_messages):
        raise RuntimeError("park failed")

    events = [
        e
        async for e, _ in workflows.stream_turn(
            repo,
            "c",
            "sys",
            "m",
            "hi",
            node_id="n",
            project_id="p",
            toolsets=[toolset],
            on_paused=on_paused,
        )
    ]

    assert events[-1] == "paused"
    # The bubble is inserted up front and parked as awaiting_approval.
    assert [r for r, *_ in repo.added] == ["user", "assistant"]
    assert repo.updates[-1][1]["status"] == "awaiting_approval"


async def _many(messages, info):
    for i in range(200):
        yield f"<{i}>"


@pytest.mark.anyio
async def test_slow_reader_loses_no_chunks(monkeypatch):
    """Backpressure, not dropping: a reader slower than the model still sees all."""
    _use_stream(monkeypatch, _many)
    repo = _Repo()

    seen = []
    async for event, payload in workflows.stream_turn(
        repo, "c", "sys", "m", "hi", node_id="n", project_id="p"
    ):
        if event == "chunk":
            seen.append(payload["text"])
            await asyncio.sleep(0.001)

    assert seen == [f"<{i}>" for i in range(200)]
    assert repo.updates[-1][1]["content"] == "".join(seen)


@pytest.mark.anyio
async def test_cancel_during_setup_finalises_cancelled(monkeypatch):
    """Rows exist before setup runs, and a cancel mid-setup never reaches the model."""
    _use_stream(monkeypatch, _unused)
    repo = _Repo()
    in_setup = asyncio.Event()

    async def setup():
        in_setup.set()
        await asyncio.sleep(10)
        raise AssertionError("setup should have been cancelled")

    run = await workflows.start_turn(
        repo, "c-setup", "sys", "m", "hi", node_id="n", project_id="p", setup=setup
    )
    assert [r for r, _, _ in repo.added] == ["user", "assistant"]
    await in_setup.wait()
    await workflows.cancel_turn(run)
    await run.task
    assert run.message.status == "cancelled"
    assert runs.get("c-setup") is None


def _flaky(failures, status=503):
    calls = {"n": 0}

    async def stream(messages, info):
        calls["n"] += 1
        if calls["n"] <= failures:
            raise ModelHTTPError(status_code=status, model_name="m", body="down")
        yield "ok"

    return stream, calls


def _use_retrying(monkeypatch, stream_fn):
    from app.services import agent

    monkeypatch.setattr(agent, "MODEL_RETRY_DELAY_S", 0)

    def fake(system_prompt, model):
        return Agent(
            agent.RetryingModel(FunctionModel(_unused, stream_function=stream_fn)),
            name="t",
            output_type=[str, DeferredToolRequests],
        )

    monkeypatch.setattr(workflows, "get_agent_for", fake)


async def test_model_error_retried_with_countdown_events(monkeypatch):
    stream, calls = _flaky(2)
    _use_retrying(monkeypatch, stream)

    events = [
        (e, p)
        async for e, p in workflows.stream_turn(
            _Repo(), "c", "sys", "m", "hi", node_id="n", project_id="p"
        )
    ]

    retries = [p for e, p in events if e == "retry"]
    assert [r.get("attempt") for r in retries] == [1, 2, None]
    assert retries[0]["max"] == 5 and "503" in retries[0]["error"]
    assert retries[-1] == {"recovered": True}
    assert calls["n"] == 3
    assert events[-1][1]["assistant_message"]["status"] == "complete"


async def test_model_retries_give_up_after_five(monkeypatch):
    stream, calls = _flaky(99)
    _use_retrying(monkeypatch, stream)

    events = [
        e
        async for e, _ in workflows.stream_turn(
            _Repo(), "c", "sys", "m", "hi", node_id="n", project_id="p"
        )
    ]

    assert events.count("retry") == 5
    assert calls["n"] == 6
    assert "error" in events


async def test_client_error_not_retried(monkeypatch):
    stream, calls = _flaky(1, status=400)
    _use_retrying(monkeypatch, stream)

    events = [
        e
        async for e, _ in workflows.stream_turn(
            _Repo(), "c", "sys", "m", "hi", node_id="n", project_id="p"
        )
    ]

    assert "retry" not in events
    assert calls["n"] == 1
