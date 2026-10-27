"""join_detached: shutdown waits on in-flight turns, then gives up at the timeout."""

import asyncio

import pytest

from app.services import runs
from app.services.runs import RunningTurn


@pytest.fixture(autouse=True)
def clean():
    runs._RUNS.clear()
    yield
    runs._RUNS.clear()


def _register(conversation_id: str, task: asyncio.Task) -> None:
    run = RunningTurn(conversation_id=conversation_id, node_id="n", project_id="p", model="m")
    run.task = task
    runs.register(run)


@pytest.mark.anyio
async def test_join_detached_returns_zero_when_task_finishes():
    async def quick():
        await asyncio.sleep(0)

    _register("c", asyncio.ensure_future(quick()))

    assert await runs.join_detached(1.0) == 0


@pytest.mark.anyio
async def test_join_detached_returns_one_when_still_running():
    stuck = asyncio.Event()

    async def blocked():
        await stuck.wait()

    task = asyncio.ensure_future(blocked())
    _register("c", task)

    assert await runs.join_detached(0.05) == 1

    stuck.set()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
