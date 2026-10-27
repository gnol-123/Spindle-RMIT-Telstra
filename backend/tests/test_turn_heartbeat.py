"""Turn heartbeat, finalise error clearing, per agent request limits."""

import asyncio

import pytest

import app.workflows as workflows
from app.repositories.project_repo import _to_node
from app.services import runs
from tests.test_turn_persistence import _Repo, _use_stream


class _LogRepo(_Repo):
    """One ordered log of every write, message and node alike."""

    def __init__(self):
        super().__init__()
        self.log = []

    def add_message(self, conversation_id, role, content, **kw):
        self.log.append(("add", role, kw))
        return super().add_message(conversation_id, role, content, **kw)

    def update_message(self, message_id, **fields):
        self.log.append(("msg", fields))
        return super().update_message(message_id, **fields)

    def set_agent_status(self, node_id, status):
        self.log.append(("node", status))
        super().set_agent_status(node_id, status)


@pytest.fixture(autouse=True)
def clean():
    runs._RUNS.clear()
    yield
    runs._RUNS.clear()


@pytest.mark.anyio
async def test_heartbeat_beats_through_silence_and_stops_before_finalise(monkeypatch):
    monkeypatch.setattr(workflows, "_HEARTBEAT_S", 0.01)

    async def silent_then_done(messages, info):
        # A long silent tool call, in miniature.
        await asyncio.sleep(0.2)
        yield "done"

    _use_stream(monkeypatch, silent_then_done)
    repo = _LogRepo()
    run = await workflows.start_turn(repo, "c", "sys", "m", "hi", node_id="n", project_id="p")
    await run.task

    running_add = next(e for e in repo.log if e[:2] == ("add", "assistant"))
    assert "heartbeat_at" in running_add[2]  # the running row starts stamped
    beats = [i for i, e in enumerate(repo.log) if e[0] == "msg" and set(e[1]) == {"heartbeat_at"}]
    assert len(beats) >= 2
    final = next(i for i, e in enumerate(repo.log) if e[0] == "msg" and "status" in e[1])
    assert max(beats) < final
    ready = repo.log.index(("node", "ready"))
    assert ("node", "running") not in repo.log[ready:]

    # Nothing beats after the turn is over.
    n = len(repo.log)
    await asyncio.sleep(0.05)
    assert len(repo.log) == n


@pytest.mark.anyio
async def test_heartbeat_failure_is_logged_not_raised(monkeypatch):
    monkeypatch.setattr(workflows, "_HEARTBEAT_S", 0.01)

    async def slow(messages, info):
        await asyncio.sleep(0.05)
        yield "ok"

    class _Flaky(_LogRepo):
        def set_agent_status(self, node_id, status):
            if status == "running" and len(self.node_status) > 0:
                raise RuntimeError("db down")
            super().set_agent_status(node_id, status)

    _use_stream(monkeypatch, slow)
    repo = _Flaky()
    run = await workflows.start_turn(repo, "c", "sys", "m", "hi", node_id="n", project_id="p")
    await run.task
    assert run.message.status == "complete"


@pytest.mark.anyio
async def test_complete_after_prior_error_sends_null_error(monkeypatch):
    async def two(messages, info):
        yield "hi"

    _use_stream(monkeypatch, two)
    repo = _Repo()
    run = await workflows.start_turn(repo, "c", "sys", "m", "hi", node_id="n", project_id="p")
    await run.task
    final = repo.updates[-1][1]
    assert final["status"] == "complete"
    assert "error" in final and final["error"] is None


@pytest.mark.anyio
async def test_failed_keeps_its_error(monkeypatch):
    async def boom(messages, info):
        raise RuntimeError("nope")
        yield  # pragma: no cover

    _use_stream(monkeypatch, boom)
    repo = _Repo()
    run = await workflows.start_turn(repo, "c", "sys", "m", "hi", node_id="n", project_id="p")
    await run.task
    final = repo.updates[-1][1]
    assert final["status"] == "failed" and final["error"]


def test_limits_per_agent_type(monkeypatch):
    monkeypatch.setattr(workflows.settings, "turn_request_limit", 100)
    row = {"id": "n", "project_id": "p", "name": "x", "agent_types": {"request_limit": 300}}
    node = _to_node(row)
    assert node.request_limit == 300
    assert workflows._limits(node.request_limit).request_limit == 300

    bare = _to_node({**row, "agent_types": {"request_limit": None}})
    assert bare.request_limit is None
    assert workflows._limits(bare.request_limit).request_limit == 100


@pytest.mark.anyio
async def test_start_turn_passes_request_limit_to_the_run(monkeypatch):
    seen = []
    real = workflows._limits

    def spy(request_limit=None):
        seen.append(request_limit)
        return real(request_limit)

    monkeypatch.setattr(workflows, "_limits", spy)

    async def two(messages, info):
        yield "hi"

    _use_stream(monkeypatch, two)
    run = await workflows.start_turn(
        _Repo(), "c", "sys", "m", "hi", node_id="n", project_id="p", request_limit=300
    )
    await run.task
    assert seen == [300]
