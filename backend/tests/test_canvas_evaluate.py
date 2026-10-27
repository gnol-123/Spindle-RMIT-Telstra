"""evaluate: temporary evaluator, always torn down."""

import asyncio
from dataclasses import replace

import anyio
import pytest
from test_canvas_tools import (  # tests/ has no __init__; rootdir on sys.path
    ORCH,
    _node,
    _Repo,
    _tools,
    _user_env,
)

import app.tools.canvas as canvas
from app.repositories.project_repo import AgentType, Message


class _EvalRepo(_Repo):
    def __init__(self, nodes=(), replies=None):
        super().__init__(nodes)
        self.types.append(
            AgentType(
                id="at-eval",
                slug="evaluator",
                name="Evaluator",
                description="d",
                system_prompt="judge",
                model="m",
                default_presets=[],
            )
        )
        self.replies = replies or {}
        self.deleted = []

    def list_messages(self, conversation_id, limit=50):
        text = self.replies.get(conversation_id)
        if text is None:
            return []
        return [
            Message(
                id="m", role="assistant", content=text, seq=2, status="complete", created_at="t"
            )
        ]

    def delete_node(self, node_id):
        self.deleted.append(node_id)
        self.nodes.pop(node_id, None)
        self.edges = [e for e in self.edges if node_id not in (e[0], e[1])]
        return [node_id]


def _patch_provision(monkeypatch, repo):
    async def fake_provision(project_id, agent_type, name, **kw):
        node = _node("eval-1", agent_type_id=agent_type.id, slug=agent_type.slug)
        repo.nodes["eval-1"] = node
        return "eval-1"

    monkeypatch.setattr(canvas, "provision_agent", fake_provision)


@pytest.mark.anyio
async def test_evaluate_runs_and_deletes(monkeypatch):
    repo = _EvalRepo([ORCH, _node("code")], replies={"conv-code": "built it"})
    _patch_provision(monkeypatch, repo)
    seen = {}

    async def fake_run(self, target, prompt, *, refresh=True):
        seen.update(target=target.id, prompt=prompt, refresh=refresh)
        return "VERDICT: PASS\nFIXES: none"

    monkeypatch.setattr(canvas.CanvasTools, "_run", fake_run)
    out = await _tools(repo).evaluate("code", "has tests")
    assert out.startswith("VERDICT: PASS")
    assert seen["target"] == "eval-1" and seen["refresh"] is False
    assert "has tests" in seen["prompt"] and "built it" in seen["prompt"]
    assert repo.deleted == ["eval-1"]


@pytest.mark.anyio
async def test_evaluate_deletes_on_failure(monkeypatch):
    repo = _EvalRepo([ORCH, _node("code")], replies={"conv-code": "x"})
    _patch_provision(monkeypatch, repo)

    async def boom(self, target, prompt, *, refresh=True):
        raise RuntimeError("model down")

    monkeypatch.setattr(canvas.CanvasTools, "_run", boom)
    out = await _tools(repo).evaluate("code", "c")
    assert "failed" in out.lower()
    assert repo.deleted == ["eval-1"]


@pytest.mark.anyio
async def test_evaluate_deletes_on_cancel(monkeypatch):
    repo = _EvalRepo([ORCH, _node("code")], replies={"conv-code": "x"})
    _patch_provision(monkeypatch, repo)

    async def hang(self, target, prompt, *, refresh=True):
        await asyncio.sleep(10)

    monkeypatch.setattr(canvas.CanvasTools, "_run", hang)
    task = asyncio.create_task(_tools(repo).evaluate("code", "c"))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert repo.deleted == ["eval-1"]


@pytest.mark.anyio
async def test_evaluate_deletes_on_anyio_cancel_scope(monkeypatch):
    """Level-triggered cancellation (anyio scope, the pydantic-ai/task-group case):
    an unshielded await in the finally gets cancelled again, unlike a one-shot
    asyncio task.cancel(). This is what actually proves the shield matters."""
    repo = _EvalRepo([ORCH, _node("code")], replies={"conv-code": "x"})
    _patch_provision(monkeypatch, repo)

    async def hang(self, target, prompt, *, refresh=True):
        await anyio.sleep(10)

    monkeypatch.setattr(canvas.CanvasTools, "_run", hang)
    with anyio.move_on_after(0.05):
        await _tools(repo).evaluate("code", "c")
    assert repo.deleted == ["eval-1"]


@pytest.mark.anyio
async def test_evaluate_refuses_without_reply_and_creates_nothing(monkeypatch):
    repo = _EvalRepo([ORCH, _node("code")])
    _patch_provision(monkeypatch, repo)
    out = await _tools(repo).evaluate("code", "c")
    assert "nothing" in out.lower()
    assert "eval-1" not in repo.nodes and repo.deleted == []


@pytest.mark.anyio
async def test_evaluate_refuses_unknown_orchestrator_and_evaluator(monkeypatch):
    repo = _EvalRepo(
        [ORCH, _node("ev", agent_type_id="at-eval", slug="evaluator")], replies={"conv-ev": "x"}
    )
    t = _tools(repo)
    assert "not found" in (await t.evaluate("ghost", "c")).lower()
    assert "refused" in (await t.evaluate("orch", "c")).lower()
    assert "refused" in (await t.evaluate("ev", "c")).lower()


@pytest.mark.anyio
async def test_evaluate_shares_env_and_keeps_it(monkeypatch):
    repo = _EvalRepo([ORCH, _node("code")], replies={"conv-code": "x"})
    _user_env(repo, "env-code", "code")
    _patch_provision(monkeypatch, repo)
    seen = {}

    async def fake_run(self, target, prompt, *, refresh=True):
        seen["edges"] = list(repo.edges)
        return "VERDICT: FAIL\nFIXES:\n1. add tests"

    monkeypatch.setattr(canvas.CanvasTools, "_run", fake_run)
    await _tools(repo).evaluate("code", "c")
    assert ("env-code", "eval-1", "environment") in seen["edges"]
    assert ("env-code", "code", "environment") in repo.edges
    assert "env-code" in repo.envs


@pytest.mark.anyio
async def test_evaluate_provision_failure_returns_string(monkeypatch):
    repo = _EvalRepo([ORCH, _node("code")], replies={"conv-code": "x"})

    async def bad(*a, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(canvas, "provision_agent", bad)
    out = await _tools(repo).evaluate("code", "c")
    assert "could not" in out.lower()
    assert repo.deleted == []


@pytest.mark.anyio
async def test_evaluate_deletes_despite_cancel_lookup_failure(monkeypatch):
    """Fix round 2, finding 1: a raising teardown step must not skip delete_node
    or let the exception replace the return string."""
    repo = _EvalRepo([ORCH, _node("code")], replies={"conv-code": "x"})
    _patch_provision(monkeypatch, repo)

    async def fake_run(self, target, prompt, *, refresh=True):
        return "VERDICT: PASS\nFIXES: none"

    async def boom_cancel(conversation_id):
        raise RuntimeError("db blip")

    monkeypatch.setattr(canvas.CanvasTools, "_run", fake_run)
    monkeypatch.setattr(canvas, "cancel_for_node", boom_cancel)
    out = await _tools(repo).evaluate("code", "c")
    assert isinstance(out, str) and out.startswith("VERDICT: PASS")
    assert repo.deleted == ["eval-1"]


@pytest.mark.anyio
async def test_evaluate_waits_for_evaluator_tools_before_running(monkeypatch):
    """Fix round 2, finding 2: the evaluator's default tools verify in the
    background; evaluate must wait for them to leave pending before _run."""
    from app.repositories.tool_repo import ToolNode

    repo = _EvalRepo([ORCH, _node("code")], replies={"conv-code": "x"})
    _patch_provision(monkeypatch, repo)
    monkeypatch.setattr(canvas, "_TOOL_WAIT_POLL_S", 0.01)

    repo.edges.append(("tool-1", "eval-1", "tool"))
    repo.tool_nodes = {
        "tool-1": ToolNode(
            id="tool-1",
            project_id="p",
            name="Web Fetch",
            tool_type_id="tt",
            tool_slug="web_fetch",
            config={},
            status="pending",
            status_detail=None,
        )
    }
    polls = {"n": 0}
    real_get = repo.get_tool_node

    def flipping_get(node_id):
        polls["n"] += 1
        if polls["n"] > 1:
            repo.tool_nodes["tool-1"] = ToolNode(
                id="tool-1",
                project_id="p",
                name="Web Fetch",
                tool_type_id="tt",
                tool_slug="web_fetch",
                config={},
                status="ready",
                status_detail=None,
            )
        return real_get(node_id)

    monkeypatch.setattr(repo, "get_tool_node", flipping_get)

    seen = {}

    async def fake_run(self, target, prompt, *, refresh=True):
        seen["status"] = repo.tool_nodes["tool-1"].status
        return "VERDICT: PASS\nFIXES: none"

    monkeypatch.setattr(canvas.CanvasTools, "_run", fake_run)
    await _tools(repo).evaluate("code", "c")
    assert seen["status"] == "ready"
    assert polls["n"] >= 2


@pytest.mark.anyio
async def test_evaluate_provision_failure_sweeps_stranded_node(monkeypatch):
    """Fix round 2, finding 3: provision_agent can raise after inserting the
    node (e.g. while wiring presets). evaluate must find and delete it."""
    repo = _EvalRepo([ORCH, _node("code")], replies={"conv-code": "x"})

    async def half_provision(project_id, agent_type, name, **kw):
        node = _node("eval-1", agent_type_id=agent_type.id, slug=agent_type.slug)
        node = replace(node, name=name)  # "Eval: code": what evaluate sweeps for
        repo.nodes["eval-1"] = node
        raise RuntimeError("preset wiring failed")

    monkeypatch.setattr(canvas, "provision_agent", half_provision)
    out = await _tools(repo).evaluate("code", "c")
    assert "could not" in out.lower()
    assert "eval-1" not in repo.nodes
    assert repo.deleted == ["eval-1"]


@pytest.mark.anyio
async def test_evaluate_cancel_during_provision_sweeps_node(monkeypatch):
    """Cancel lands after the insert, before provision_agent returns."""
    repo = _EvalRepo([ORCH, _node("code")], replies={"conv-code": "x"})

    async def stuck_provision(project_id, agent_type, name, **kw):
        node = _node("eval-1", agent_type_id=agent_type.id, slug=agent_type.slug)
        repo.nodes["eval-1"] = replace(node, name=name)
        await anyio.sleep_forever()

    monkeypatch.setattr(canvas, "provision_agent", stuck_provision)
    with anyio.move_on_after(0.05):
        await _tools(repo).evaluate("code", "c")
    assert "eval-1" not in repo.nodes
    assert repo.deleted == ["eval-1"]


def test_list_canvas_hides_evaluator_type():
    import json

    repo = _EvalRepo([ORCH])
    slugs = [t["slug"] for t in json.loads(asyncio.run(_tools(repo).list_canvas()))["agent_types"]]
    assert "evaluator" not in slugs


@pytest.mark.anyio
async def test_create_agent_refuses_evaluator():
    assert "refused" in (await _tools(_EvalRepo([ORCH])).create_agent("evaluator", "E")).lower()
