"""The driver writes the bubble progressively and finalises it."""

import asyncio
import threading
import time

import pytest
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.toolsets import FunctionToolset

import app.workflows as workflows
from app.repositories.project_repo import Message
from app.services import runs


class _Repo:
    def __init__(self):
        self.added = []
        self.updates = []
        self.node_status = []
        self._seq = 0

    def list_messages(self, conversation_id, limit=50):
        return []

    def _msg(self, role, content, status, **kw):
        self._seq += 1
        return Message(
            id=f"m{self._seq}",
            role=role,
            content=content,
            seq=self._seq,
            status=status,
            created_at="t",
            tool_calls=kw.get("tool_calls", []),
        )

    def add_message(self, conversation_id, role, content, **kw):
        m = self._msg(role, content, kw.get("status", "complete"))
        self.added.append(m)
        return m

    def update_message(self, message_id, **fields):
        self.updates.append((message_id, fields))
        base = next(m for m in self.added if m.id == message_id)
        return Message(
            id=base.id,
            role=base.role,
            content=fields.get("content", base.content),
            seq=base.seq,
            status=fields.get("status", base.status),
            created_at="t",
            tool_calls=fields.get("tool_calls", base.tool_calls),
        )

    def set_agent_status(self, node_id, status):
        self.node_status.append(status)

    def latest_message_with_status(self, conversation_id, status):
        return None


class _ToolRepo:
    def __init__(self):
        self.cancelled = []

    def cancel_calls(self, conversation_id, from_statuses):
        self.cancelled.append(from_statuses)


def _use_stream(monkeypatch, stream_fn, sync_fn=None):
    def fake(system_prompt, model):
        return Agent(
            FunctionModel(
                sync_fn or (lambda m, i: ModelResponse(parts=[])), stream_function=stream_fn
            ),
            name="t",
            output_type=[str, DeferredToolRequests],
        )

    monkeypatch.setattr(workflows, "get_agent_for", fake)


@pytest.fixture(autouse=True)
def clean():
    runs._RUNS.clear()
    yield
    runs._RUNS.clear()


async def _two(messages, info):
    yield "first"
    yield " second"


@pytest.mark.anyio
async def test_running_row_then_complete(monkeypatch):
    _use_stream(monkeypatch, _two)
    repo = _Repo()
    events = [
        e
        async for e, _ in workflows.stream_turn(
            repo, "c", "sys", "m", "hi", node_id="n", project_id="p"
        )
    ]
    assert events[0] == "start" and events[-1] == "done"
    assert [(m.role, m.status) for m in repo.added] == [
        ("user", "complete"),
        ("assistant", "running"),
    ]
    final = repo.updates[-1][1]
    assert final["status"] == "complete" and final["content"] == "first second"
    assert repo.node_status == ["running", "ready"]
    assert runs.get("c") is None


def _script(messages: list[ModelMessage], info: AgentInfo):
    calls = [p for m in messages for p in m.parts if isinstance(p, ToolCallPart)]
    done = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart | RetryPromptPart)]
    if not calls:
        return ModelResponse(parts=[ToolCallPart(tool_name="probe", args={})])
    if len(done) < len(calls):
        return ModelResponse(parts=[])
    return ModelResponse(parts=[TextPart(content="done")])


async def _stream_script(messages, info):
    calls = [p for m in messages for p in m.parts if isinstance(p, ToolCallPart)]
    done = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart | RetryPromptPart)]
    if not calls:
        yield {0: DeltaToolCall(name="probe", json_args="{}")}
        return
    if len(done) < len(calls):
        return
    yield "done"


@pytest.mark.anyio
async def test_tool_events_land_on_row_in_order(monkeypatch):
    def probe() -> str:
        return "ok"

    _use_stream(monkeypatch, _stream_script, _script)
    repo = _Repo()
    async for _ in workflows.stream_turn(
        repo,
        "c",
        "sys",
        "m",
        "hi",
        node_id="n",
        project_id="p",
        toolsets=[FunctionToolset([probe])],
    ):
        pass
    final = repo.updates[-1][1]
    assert [e["type"] for e in final["tool_calls"]] == ["call", "result"]
    assert final["tool_calls"][1]["result_head"] == "ok"
    assert final["tool_calls"][1]["status"] == "ok"
    # A tool event forces a flush: at least one update carries the call before the finalise.
    assert any(
        f.get("tool_calls") and f["tool_calls"][0]["type"] == "call" for _, f in repo.updates[:-1]
    )


async def _fifty(messages, info):
    for i in range(50):
        yield f"{i},"


@pytest.mark.anyio
async def test_no_write_per_chunk_within_the_interval(monkeypatch):
    """A long interval means the finalise is the only write, however many chunks."""
    monkeypatch.setattr(workflows, "_FLUSH_INTERVAL_S", 3600.0)
    _use_stream(monkeypatch, _fifty)
    repo = _Repo()
    async for _ in workflows.stream_turn(repo, "c", "sys", "m", "hi", node_id="n", project_id="p"):
        pass
    assert len(repo.updates) == 1
    assert repo.updates[0][1]["status"] == "complete"


@pytest.mark.anyio
async def test_zero_interval_writes_every_chunk(monkeypatch):
    """The throttle is the only thing holding writes back, not a chunk counter."""
    monkeypatch.setattr(workflows, "_FLUSH_INTERVAL_S", 0.0)
    _use_stream(monkeypatch, _fifty)
    repo = _Repo()
    async for _ in workflows.stream_turn(repo, "c", "sys", "m", "hi", node_id="n", project_id="p"):
        pass
    # 50 progress writes plus the finalise.
    assert len(repo.updates) == 51


@pytest.mark.anyio
async def test_busy_conversation_raises_before_writes(monkeypatch):
    gate = asyncio.Event()

    async def slow(messages, info):
        yield "a"
        await gate.wait()

    _use_stream(monkeypatch, slow)
    repo = _Repo()
    run = await workflows.start_turn(repo, "c", "sys", "m", "hi", node_id="n", project_id="p")
    before = len(repo.added)
    with pytest.raises(runs.TurnBusy):
        await workflows.start_turn(repo, "c", "sys", "m", "again", node_id="n", project_id="p")
    assert len(repo.added) == before
    gate.set()
    await run.task


@pytest.mark.anyio
async def test_run_turn_returns_chat_turn(monkeypatch):
    _use_stream(monkeypatch, _two)
    repo = _Repo()
    turn = await workflows.run_turn(repo, "c", "sys", "m", "hi", node_id="n", project_id="p")
    assert turn.output == "first second"
    assert turn.assistant_message.status == "complete"


@pytest.mark.anyio
async def test_model_failure_is_failed_row(monkeypatch):
    async def boom(messages, info):
        yield "partial"
        raise RuntimeError("upstream")

    _use_stream(monkeypatch, boom)
    repo = _Repo()
    events = [
        e
        async for e, _ in workflows.stream_turn(
            repo, "c", "sys", "m", "hi", node_id="n", project_id="p"
        )
    ]
    assert "error" in events
    final = repo.updates[-1][1]
    assert final["status"] == "failed" and final["content"] == "partial"
    assert repo.node_status[-1] == "ready"


@pytest.mark.anyio
async def test_cancel_finalises_cancelled_row(monkeypatch):
    gate = asyncio.Event()

    async def slow(messages, info):
        yield "partial"
        await gate.wait()

    _use_stream(monkeypatch, slow)
    repo = _Repo()
    tool_repo = _ToolRepo()
    run = await workflows.start_turn(
        repo, "c", "sys", "m", "hi", node_id="n", project_id="p", tool_repo=tool_repo
    )
    await asyncio.sleep(0.05)
    run.cancel_requested = True
    run.task.cancel()
    await run.task

    final = repo.updates[-1][1]
    assert final["status"] == "cancelled" and final["content"] == "partial"
    assert tool_repo.cancelled == [["running", "pending_approval"]]
    assert repo.node_status[-1] == "ready"
    assert runs.get("c") is None


@pytest.mark.anyio
async def test_resume_reuses_the_parked_row(monkeypatch):
    """A resume writes no new rows: it flips the parked bubble back to running."""
    from pydantic_ai import DeferredToolResults

    _use_stream(monkeypatch, _two)
    repo = _Repo()
    parked = repo.add_message("c", "assistant", "before ", status="awaiting_approval")
    resume = workflows.ResumeInput(history=[], deferred=DeferredToolResults(), message=parked)
    turn = await workflows.run_turn(
        repo, "c", "sys", "m", None, node_id="n", project_id="p", resume=resume
    )

    assert turn.user_message is None
    assert len(repo.added) == 1
    assert repo.updates[0][0] == parked.id
    assert repo.updates[0][1]["status"] == "running" and "heartbeat_at" in repo.updates[0][1]
    # The empty history makes the run itself fail; the row is still finalised.
    assert repo.updates[-1][1]["status"] == "failed"
    assert repo.updates[-1][1]["content"].startswith("before ")
    assert repo.node_status == ["running", "ready"]
    assert runs.get("c") is None


@pytest.mark.anyio
async def test_second_cancel_still_closes_subscribers(monkeypatch):
    """A cancel landing mid-finalise must not strand attached readers."""
    gate = asyncio.Event()
    # threading.Event: set from the worker thread the write runs on.
    writing = threading.Event()

    async def slow(messages, info):
        yield "partial"
        await gate.wait()

    class _BlockingRepo(_Repo):
        def update_message(self, message_id, **fields):
            # Only the finalise blocks; the running-row insert is untouched.
            if fields.get("status") == "cancelled":
                writing.set()
                time.sleep(0.2)
            return super().update_message(message_id, **fields)

    _use_stream(monkeypatch, slow)
    repo = _BlockingRepo()
    run = await workflows.start_turn(repo, "c", "sys", "m", "hi", node_id="n", project_id="p")
    _text, _events, receive = await runs.subscribe(run)

    await asyncio.sleep(0.05)
    run.cancel_requested = True
    run.task.cancel()
    # Land a second cancel while the finalise write is in flight.
    await asyncio.to_thread(writing.wait, 2.0)
    run.task.cancel()
    await run.task

    seen = []
    # Bounded: an unshielded tail leaves this stream open forever.
    async with asyncio.timeout(2.0), receive:
        async for item in receive:
            seen.append(item)
    assert seen and seen[-1][0] == "done"
    assert seen[-1][1]["assistant_message"]["status"] == "cancelled"
    assert repo.updates[-1][1]["status"] == "cancelled"


@pytest.mark.anyio
async def test_stream_with_no_terminal_event_is_failed(monkeypatch):
    """A provider that closes without a result must not leave the row running."""

    async def silent(messages, info):
        return
        yield  # pragma: no cover

    def _no_terminal(*a, **kw):
        async def gen():
            yield "chunk", {"text": "bit"}

        return gen()

    _use_stream(monkeypatch, silent)
    monkeypatch.setattr(workflows, "_stream_agent", _no_terminal)
    repo = _Repo()
    await workflows.run_turn(repo, "c", "sys", "m", "hi", node_id="n", project_id="p")

    final = repo.updates[-1][1]
    assert final["status"] == "failed"
    assert final["error"] == "run ended without a result"
    assert repo.node_status == ["running", "ready"]
    assert runs.get("c") is None
