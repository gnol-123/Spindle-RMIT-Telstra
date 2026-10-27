"""Stopping a turn: the model call aborts, the partial lands, the node frees."""

import asyncio
import threading
import time

import pytest
from pydantic_ai.toolsets import FunctionToolset

import app.workflows as workflows
from app.services import runs
from tests.test_turn_persistence import _Repo, _script, _stream_script, _ToolRepo, _use_stream


@pytest.fixture(autouse=True)
def clean():
    runs._RUNS.clear()
    yield
    runs._RUNS.clear()


@pytest.mark.anyio
async def test_cancel_mid_stream(monkeypatch):
    gate = asyncio.Event()
    reached = asyncio.Event()

    async def slow(messages, info):
        yield "partial"
        reached.set()
        await gate.wait()
        yield " never"

    _use_stream(monkeypatch, slow)
    repo, tool_repo = _Repo(), _ToolRepo()
    run = await workflows.start_turn(
        repo, "c", "sys", "m", "hi", node_id="n", project_id="p", tool_repo=tool_repo
    )
    await reached.wait()
    await workflows.cancel_turn(run)
    await run.task
    final = repo.updates[-1][1]
    assert final["status"] == "cancelled" and final["content"] == "partial"
    assert final.get("error") is None
    assert tool_repo.cancelled == [["running", "pending_approval"]]
    assert repo.node_status[-1] == "ready"
    assert runs.get("c") is None
    assert run.message.status == "cancelled"


@pytest.mark.anyio
async def test_cancel_during_tool_call(monkeypatch):
    gate = asyncio.Event()
    inside = asyncio.Event()
    seen: list[str] = []

    async def probe() -> str:
        inside.set()
        try:
            await gate.wait()
        except asyncio.CancelledError:
            seen.append("cancelled")
            raise
        seen.append("finished")
        return "ok"

    _use_stream(monkeypatch, _stream_script, _script)
    repo, tool_repo = _Repo(), _ToolRepo()
    run = await workflows.start_turn(
        repo,
        "c",
        "sys",
        "m",
        "hi",
        node_id="n",
        project_id="p",
        tool_repo=tool_repo,
        toolsets=[FunctionToolset([probe])],
    )
    await inside.wait()
    await workflows.cancel_turn(run)
    await run.task
    final = repo.updates[-1][1]
    assert final["status"] == "cancelled"
    # The tool coroutine was interrupted mid-await, not merely left unrecorded.
    assert seen == ["cancelled"]
    # The dangling call gets a synthetic result, so the bubble never spins forever.
    assert [e["type"] for e in final["tool_calls"]] == ["call", "result"]
    synthetic = final["tool_calls"][1]
    assert synthetic["status"] == "cancelled"
    assert synthetic["tool_call_id"] == final["tool_calls"][0]["tool_call_id"]
    assert synthetic["name"] == "probe"
    assert synthetic["result_head"] == "cancelled" and synthetic["at"]


@pytest.mark.anyio
async def test_shutdown_mid_tool_call_closes_the_call_as_error(monkeypatch):
    """A failed terminal path must not leave a call spinning either."""
    gate, inside = asyncio.Event(), asyncio.Event()

    async def probe() -> str:
        inside.set()
        await gate.wait()
        return "ok"

    _use_stream(monkeypatch, _stream_script, _script)
    repo, tool_repo = _Repo(), _ToolRepo()
    run = await workflows.start_turn(
        repo,
        "c",
        "sys",
        "m",
        "hi",
        node_id="n",
        project_id="p",
        tool_repo=tool_repo,
        toolsets=[FunctionToolset([probe])],
    )
    await inside.wait()
    run.task.cancel()  # no cancel_requested: uvicorn tearing down
    await run.task
    final = repo.updates[-1][1]
    assert final["status"] == "failed"
    assert [e["type"] for e in final["tool_calls"]] == ["call", "result"]
    assert final["tool_calls"][1]["status"] == "error"


@pytest.mark.anyio
async def test_shutdown_cancel_is_failed_not_cancelled(monkeypatch):
    gate = asyncio.Event()
    reached = asyncio.Event()

    async def slow(messages, info):
        yield "x"
        reached.set()
        await gate.wait()

    _use_stream(monkeypatch, slow)
    repo = _Repo()
    run = await workflows.start_turn(repo, "c", "sys", "m", "hi", node_id="n", project_id="p")
    await reached.wait()
    run.task.cancel()  # no cancel_requested: uvicorn tearing down
    await run.task
    final = repo.updates[-1][1]
    assert final["status"] == "failed" and final["error"] == "backend shutting down"


@pytest.mark.anyio
async def test_second_cancel_during_finalise_does_not_cut_write(monkeypatch):
    gate = asyncio.Event()
    reached = asyncio.Event()
    # threading.Event: set from the worker thread the write runs on.
    writing = threading.Event()

    async def slow(messages, info):
        yield "x"
        reached.set()
        await gate.wait()

    class _BlockingRepo(_Repo):
        def update_message(self, message_id, **fields):
            if fields.get("status") == "cancelled":
                writing.set()
                time.sleep(0.2)
            return super().update_message(message_id, **fields)

    _use_stream(monkeypatch, slow)
    repo = _BlockingRepo()
    run = await workflows.start_turn(repo, "c", "sys", "m", "hi", node_id="n", project_id="p")
    await reached.wait()
    await workflows.cancel_turn(run)
    await asyncio.to_thread(writing.wait, 2.0)
    run.task.cancel()  # second cancel while finalise is in flight
    await run.task
    await asyncio.gather(*runs._FINALISERS, return_exceptions=True)
    assert repo.updates[-1][1]["status"] == "cancelled"


@pytest.mark.anyio
async def test_cancel_paused_abandons_pending():
    from app.repositories.project_repo import Message

    class Repo(_Repo):
        def latest_message_with_status(self, conversation_id, status):
            m = Message(
                id="m9", role="assistant", content="so far", seq=9, status=status, created_at="t"
            )
            self.added.append(m)
            return m

    class ToolRepo(_ToolRepo):
        def __init__(self):
            super().__init__()
            self.pending_cleared = []

        def set_pending_run(self, conversation_id, payload):
            self.pending_cleared.append(payload)

    repo, tool_repo = Repo(), ToolRepo()
    out = await workflows.cancel_paused(repo, tool_repo, "c", "n")
    assert out.status == "cancelled"
    assert tool_repo.pending_cleared == [None]
    assert tool_repo.cancelled == [["running", "pending_approval"]]
    assert repo.node_status[-1] == "ready"


@pytest.mark.anyio
async def test_cancel_paused_closes_dangling_calls():
    from app.repositories.project_repo import Message

    parked_events = [
        {"type": "call", "tool_call_id": "c1", "name": "probe", "args": {}, "at": "t"},
        {"type": "call", "tool_call_id": "c2", "name": "other", "args": {}, "at": "t"},
        {
            "type": "result",
            "tool_call_id": "c2",
            "name": "other",
            "status": "ok",
            "result_head": "fine",
            "at": "t",
        },
    ]

    class Repo(_Repo):
        def latest_message_with_status(self, conversation_id, status):
            m = Message(
                id="m9",
                role="assistant",
                content="so far",
                seq=9,
                status=status,
                created_at="t",
                tool_calls=parked_events,
            )
            self.added.append(m)
            return m

    class ToolRepo(_ToolRepo):
        def set_pending_run(self, conversation_id, payload):
            pass

    repo, tool_repo = Repo(), ToolRepo()
    out = await workflows.cancel_paused(repo, tool_repo, "c", "n")
    assert out.status == "cancelled"
    written = repo.updates[-1][1]["tool_calls"]
    assert [(e["type"], e["tool_call_id"]) for e in written] == [
        ("call", "c1"),
        ("call", "c2"),
        ("result", "c2"),
        ("result", "c1"),
    ]
    assert written[-1]["status"] == "cancelled" and written[-1]["name"] == "probe"
    assert written[2]["status"] == "ok"


@pytest.mark.anyio
async def test_settle_blowing_up_still_writes_a_terminal_status(monkeypatch):
    """A throw after _finalise must not leave the row running for the sweep."""

    async def boom(run, event, payload):
        raise RuntimeError("close failed")

    monkeypatch.setattr(runs, "close", boom)
    _use_stream(monkeypatch, _stream_script)

    repo, tool_repo = _Repo(), _ToolRepo()
    run = await workflows.start_turn(
        repo, "c", "sys", "m", "hi", node_id="n", project_id="p", tool_repo=tool_repo
    )
    await asyncio.wait_for(run.task, 5)

    assert repo.updates[-1][1]["status"] == "failed"
    assert runs.get("c") is None
    assert repo.node_status[-1] == "ready"


@pytest.mark.anyio
async def test_run_stays_registered_until_the_pause_row_is_written(monkeypatch):
    """A cancel arriving while the turn parks must find the run, not 409."""
    inside_on_paused = asyncio.Event()
    release = asyncio.Event()

    async def fake_stream(*args, **kwargs):
        yield "paused", {"pending": object(), "all_messages": []}

    monkeypatch.setattr(workflows, "_stream_agent", fake_stream)

    async def on_paused(pending, all_messages):
        inside_on_paused.set()
        await release.wait()

    repo, tool_repo = _Repo(), _ToolRepo()
    run = await workflows.start_turn(
        repo,
        "c",
        "sys",
        "m",
        "hi",
        node_id="n",
        project_id="p",
        tool_repo=tool_repo,
        on_paused=on_paused,
    )
    await asyncio.wait_for(inside_on_paused.wait(), 5)

    # The window: the row is not awaiting_approval yet.
    assert runs.get("c") is run

    release.set()
    await asyncio.wait_for(run.task, 5)
    assert runs.get("c") is None
    assert repo.updates[-1][1]["status"] == "awaiting_approval"


@pytest.mark.anyio
async def test_cancel_paused_returns_none_when_nothing_parked():
    repo, tool_repo = _Repo(), _ToolRepo()
    assert await workflows.cancel_paused(repo, tool_repo, "c", "n") is None
    assert tool_repo.cancelled == []
