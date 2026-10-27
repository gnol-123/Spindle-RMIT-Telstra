"""In-process registry of running turns."""

import asyncio

import pytest

from app.services import runs


def _run(cid="c"):
    return runs.RunningTurn(conversation_id=cid, node_id="n", project_id="p", model="m")


@pytest.fixture(autouse=True)
def clean():
    runs._RUNS.clear()
    yield
    runs._RUNS.clear()


def test_register_twice_is_busy():
    runs.register(_run())
    with pytest.raises(runs.TurnBusy):
        runs.register(_run())
    runs.unregister("c")
    assert runs.get("c") is None


def test_running_in_project():
    runs.register(_run("a"))
    other = _run("b")
    other.project_id = "q"
    runs.register(other)
    assert [r.conversation_id for r in runs.running_in_project("p")] == ["a"]


@pytest.mark.anyio
async def test_subscribe_snapshot_then_tail():
    run = _run()
    await runs.emit(run, "chunk", {"text": "he"})
    await runs.emit(run, "tool", {"name": "t", "args": {}})
    text, events, receive = await runs.subscribe(run)
    assert text == "he"
    # offset: where in the text the tool event landed.
    assert events == [{"name": "t", "args": {}, "offset": 2}]
    await runs.emit(run, "chunk", {"text": "llo"})
    await runs.close(run, "done", {"ok": True})
    got = [item async for item in receive]
    assert got == [("chunk", {"text": "llo"}), ("done", {"ok": True})]
    assert "".join(run.text) == "hello"


@pytest.mark.anyio
async def test_full_subscriber_is_dropped_not_blocking():
    run = _run()
    _, _, receive = await runs.subscribe(run)
    for i in range(runs.SUBSCRIBER_BUFFER + 5):
        await runs.emit(run, "chunk", {"text": str(i)})
    assert run.subscribers == set()
    seen = [item async for item in receive]
    assert len(seen) == runs.SUBSCRIBER_BUFFER


@pytest.mark.anyio
async def test_late_subscriber_gets_final_only():
    run = _run()
    await runs.close(run, "done", {"ok": True})
    text, events, receive = await runs.subscribe(run)
    assert [item async for item in receive] == [("done", {"ok": True})]


@pytest.mark.anyio
async def test_join_detached_counts_still_running():
    run = _run()
    gate = asyncio.Event()

    async def wait():
        await gate.wait()

    run.task = asyncio.ensure_future(wait())
    runs.register(run)
    assert await runs.join_detached(0.01) == 1
    gate.set()
    await run.task
    assert await runs.join_detached(0.01) == 0
