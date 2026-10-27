"""Deleting a node or project must stop its running turn first."""

import asyncio
import contextlib

import pytest

import app.workflows as workflows
from app.services import runs
from app.services.runs import RunningTurn


@pytest.fixture(autouse=True)
def clean():
    runs._RUNS.clear()
    yield
    runs._RUNS.clear()


def _run(conversation_id, node_id, project_id):
    async def _never():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            return

    run = RunningTurn(
        conversation_id=conversation_id, node_id=node_id, project_id=project_id, model="m"
    )
    run.task = asyncio.ensure_future(_never())
    runs.register(run)
    return run


@pytest.mark.anyio
async def test_cancel_for_node_cancels_running_turn():
    run = _run("c1", "n1", "p1")
    await workflows.cancel_for_node("c1")
    assert run.task.done()
    assert run.cancel_requested is True


@pytest.mark.anyio
async def test_cancel_for_node_is_noop_without_conversation():
    # No conversation id (e.g. a non-agent node kind) is a no-op, not an error.
    await workflows.cancel_for_node(None)


@pytest.mark.anyio
async def test_cancel_for_node_is_noop_when_nothing_running():
    await workflows.cancel_for_node("no-such-conversation")


@pytest.mark.anyio
async def test_cancel_for_project_cancels_every_run_in_project():
    r1 = _run("c1", "n1", "p1")
    r2 = _run("c2", "n2", "p1")
    r3 = _run("c3", "n3", "other-project")

    await workflows.cancel_for_project("p1")

    assert r1.task.done()
    assert r2.task.done()
    assert not r3.task.done()
    r3.task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await r3.task
