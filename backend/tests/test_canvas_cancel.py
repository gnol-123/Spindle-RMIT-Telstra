"""run_agent as a child run: busy refusal, stage-only cancel, orchestrator cascade."""

import asyncio

import pytest
from pydantic_ai.toolsets import FunctionToolset

import app.tools.canvas as canvas
import app.workflows as workflows
from app.routers.deps import TurnRepositories
from app.services import runs
from tests.test_canvas_tools import ORCH, _node, _prepared
from tests.test_canvas_tools import _Repo as _CanvasRepo
from tests.test_turn_persistence import _Repo as _TurnRepo
from tests.test_turn_persistence import _ToolRepo, _use_stream


@pytest.fixture(autouse=True)
def clean():
    runs._RUNS.clear()
    yield
    runs._RUNS.clear()


class _Repo(_CanvasRepo, _TurnRepo):
    """Canvas reads plus the message/status writes run_turn needs to actually run."""

    def __init__(self, nodes=()):
        _CanvasRepo.__init__(self, nodes)
        _TurnRepo.__init__(self)
        self.cancelled = []

    # tool repo: run_agent checks this before starting the child turn
    def set_pending_run(self, conversation_id, payload):
        self.pending[conversation_id] = payload

    def cancel_calls(self, conversation_id, from_statuses):
        self.cancelled.append(from_statuses)


def _tools(repo, conversation_id="conv-orch"):
    repos = TurnRepositories(project=repo, tool=repo, env=repo, user_id="u")
    return canvas.CanvasTools(repos, ORCH, conversation_id)


async def _prepared_async():
    return _prepared()


@pytest.mark.anyio
async def test_run_agent_refuses_busy_stage(monkeypatch):
    repo = _Repo([ORCH, _node("a")])
    monkeypatch.setattr(canvas, "prepare_turn", lambda *a, **k: _prepared_async())

    run = runs.RunningTurn(conversation_id="conv-a", node_id="a", project_id="p", model="m")
    runs.register(run)

    out = await _tools(repo).run_agent("a", "go")

    assert out == "Refused: a is already running a turn."


@pytest.mark.anyio
async def test_stage_cancel_returns_tool_result(monkeypatch):
    gate = asyncio.Event()
    reached = asyncio.Event()

    async def slow(messages, info):
        yield "partial"
        reached.set()
        await gate.wait()
        yield " never"

    _use_stream(monkeypatch, slow)
    monkeypatch.setattr(canvas, "prepare_turn", lambda *a, **k: _prepared_async())

    repo = _Repo([ORCH, _node("a")])

    task = asyncio.ensure_future(_tools(repo).run_agent("a", "go"))
    async with asyncio.timeout(5):
        await reached.wait()
    stage_run = runs.get("conv-a")
    assert stage_run is not None
    await workflows.cancel_turn(stage_run)

    async with asyncio.timeout(5):
        out = await task
    assert out.startswith("Cancelled by user: a.")
    assert "conversation" in out
    # Orchestrator's own conversation was never registered, so cascade never ran.
    assert runs.get("conv-orch") is None


@pytest.mark.anyio
async def test_orchestrator_cancel_cascades(monkeypatch):
    gate = asyncio.Event()
    reached = asyncio.Event()

    async def slow(messages, info):
        yield "partial"
        reached.set()
        await gate.wait()
        yield " never"

    async def orch_model(messages, info):
        calls = [p for m in messages for p in m.parts if p.__class__.__name__ == "ToolCallPart"]
        done = [
            p
            for m in messages
            for p in m.parts
            if p.__class__.__name__ in ("ToolReturnPart", "RetryPromptPart")
        ]
        if not calls:
            from pydantic_ai.models.function import DeltaToolCall

            yield {0: DeltaToolCall(name="run_agent", json_args='{"node_id": "a", "prompt": "go"}')}
            return
        if len(done) < len(calls):
            return
        yield "orchestrator done"

    # Two distinct models so get_agent_for can tell the orchestrator's call
    # from the stage's: both run through the same fake agent factory.
    def fake_get_agent_for(system_prompt, model):
        from pydantic_ai import Agent, DeferredToolRequests
        from pydantic_ai.models.function import FunctionModel

        stream_fn = orch_model if model == "orch-model" else slow
        return Agent(
            FunctionModel(lambda m, i: None, stream_function=stream_fn),
            name="t",
            output_type=[str, DeferredToolRequests],
        )

    monkeypatch.setattr(workflows, "get_agent_for", fake_get_agent_for)
    monkeypatch.setattr(canvas, "prepare_turn", lambda *a, **k: _prepared_async())

    stage_node = _node("a")
    project_repo = _Repo([ORCH, stage_node])
    orch_repo, orch_tool_repo = _TurnRepo(), _ToolRepo()

    async def fake_run_agent_tool(node_id: str, prompt: str) -> str:
        return await _tools(project_repo, "conv-orch").run_agent(node_id, prompt)

    orch_toolset = FunctionToolset([])
    orch_toolset.add_function(fake_run_agent_tool, name="run_agent")

    orch_run = await workflows.start_turn(
        orch_repo,
        "conv-orch",
        "sys",
        "orch-model",
        "hi",
        node_id="orch",
        project_id="p",
        tool_repo=orch_tool_repo,
        toolsets=[orch_toolset],
    )

    async with asyncio.timeout(5):
        await reached.wait()
    await workflows.cancel_turn(orch_run)
    async with asyncio.timeout(5):
        await orch_run.task

    orch_final = orch_repo.updates[-1][1]
    assert orch_final["status"] == "cancelled"
    assert runs.get("conv-orch") is None
    assert runs.get("conv-a") is None

    # The cascade must land the stage row cancelled too, not just clear the
    # registry (unregister happens on the shutdown-failed path as well).
    stage_final = project_repo.updates[-1][1]
    assert stage_final["status"] == "cancelled"
    assert stage_final["content"] == "partial"
