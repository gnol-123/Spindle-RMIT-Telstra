"""The streaming bridge in ``_stream_agent``.

Deltas reach the caller through an ``event_stream_handler`` and a memory
stream. The task that drives the run must not be wrapped in a task group:
a cancel scope cannot span the generator's ``yield``, and when it did, a mid-stream
failure surfaced as a
RuntimeError about cancel scopes instead of the provider's own error.
"""

import pytest
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.models.function import FunctionModel

import app.workflows as workflows


def _unused(messages, info):
    raise AssertionError("the sync path is never taken in these tests")


def _use_stream(monkeypatch, stream_fn) -> None:
    def fake_get_agent_for(system_prompt: str, model: str):
        return Agent(
            FunctionModel(_unused, stream_function=stream_fn),
            name="test_stream_agent",
            output_type=[str, DeferredToolRequests],
        )

    monkeypatch.setattr(workflows, "get_agent_for", fake_get_agent_for)


async def _ok(messages, info):
    yield "Hel"
    yield "lo"
    yield " world"


async def _boom(messages, info):
    yield "partial"
    raise RuntimeError("provider exploded")


async def test_deltas_arrive_then_done(monkeypatch):
    _use_stream(monkeypatch, _ok)

    events = [
        (event, payload.get("text"))
        async for event, payload in workflows._stream_agent("sys", "m", "hi", [])
    ]

    assert "".join(t for e, t in events if e == "chunk") == "Hello world"
    assert events[-1][0] == "done"


async def test_mid_stream_failure_surfaces_the_providers_error(monkeypatch):
    """Regression: the real error must not be buried in an ExceptionGroup."""
    _use_stream(monkeypatch, _boom)

    with pytest.raises(RuntimeError, match="provider exploded"):
        async for _event, _payload in workflows._stream_agent("sys", "m", "hi", []):
            pass


async def test_reader_leaving_early_does_not_raise(monkeypatch):
    """The SSE client can disconnect mid-turn; the generator must close cleanly."""
    _use_stream(monkeypatch, _ok)

    async for event, _payload in workflows._stream_agent("sys", "m", "hi", []):
        assert event == "chunk"
        break
