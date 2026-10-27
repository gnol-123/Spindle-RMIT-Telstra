"""Setup overlaps the row writes; inbound edges and secret keys are one query each."""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest
from pydantic_ai.toolsets import FunctionToolset

import app.tools.assembly as assembly
import app.workflows as workflows
from app.repositories.project_repo import ProjectRepository
from app.repositories.tool_repo import ToolNode
from app.services import runs
from app.tools.base import ToolSpec, VerifyResult
from tests.test_stream_detached import _Repo, _use_stream


@pytest.fixture(autouse=True)
def clean():
    runs._RUNS.clear()
    yield
    runs._RUNS.clear()


async def _ok(messages, info):
    yield "ok"


async def test_setup_starts_before_user_row_insert_returns(monkeypatch):
    _use_stream(monkeypatch, _ok)
    started = threading.Event()

    class Repo(_Repo):
        def add_message(self, conversation_id, role, content, **kw):
            # Blocks the insert until setup runs: sequential would time out.
            if role == "user":
                assert started.wait(2)
            return super().add_message(conversation_id, role, content, **kw)

    async def setup():
        started.set()
        return workflows.TurnSetup(None, None, None)

    run = await workflows.start_turn(
        Repo(), "c-ov", "sys", "m", "hi", node_id="n", project_id="p", setup=setup
    )
    await run.task
    assert run.message.status == "complete"


async def test_row_write_failure_cancels_setup():
    cancelled = asyncio.Event()

    class Repo(_Repo):
        def add_message(self, *a, **k):
            raise RuntimeError("db down")

    async def setup():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with pytest.raises(RuntimeError):
        await workflows.start_turn(
            Repo(), "c-fail", "sys", "m", "hi", node_id="n", project_id="p", setup=setup
        )
    await asyncio.wait_for(cancelled.wait(), 1)
    assert runs.get("c-fail") is None


def _node_row(i, kind, owner="u", slug=None):
    return {
        "id": i,
        "project_id": "p",
        "name": i,
        "kind": kind,
        "owner_id": owner,
        "tool_type_id": "tt" if slug else None,
        "config": {},
        "status": "ready",
        "status_detail": None,
        "tool_policy": "ask",
        "position_x": 0,
        "position_y": 0,
        "tool_types": {"slug": slug} if slug else None,
    }


def _edge(kind, node, summary=None):
    return {"kind": kind, "summary": summary, "source_node_id": node["id"], "nodes": node}


def test_list_inbound_is_one_query_split_by_kind():
    client = MagicMock()
    chain = client.table.return_value
    for m in ("select", "eq", "in_"):
        getattr(chain, m).return_value = chain
    chain.execute.return_value = MagicMock(
        data=[
            _edge("context", _node_row("a", "agent"), summary=" s "),
            _edge("context", _node_row("b", "agent"), summary=""),
            _edge("tool", _node_row("t", "tool", slug="web_fetch")),
            _edge("tool", _node_row("x", "tool", owner="other", slug="s")),
            _edge("environment", _node_row("e", "environment")),
            _edge("environment", _node_row("w", "tool", slug="s")),
        ]
    )

    got = ProjectRepository(client, "u").list_inbound("n")

    assert chain.execute.call_count == 1
    assert [(c.source_node_id, c.summary) for c in got.context] == [("a", "s")]
    assert [(n.id, n.tool_slug) for n in got.tool_nodes] == [("t", "web_fetch")]
    assert [n.id for n in got.env_nodes] == ["e"]


def _tool(i):
    return ToolNode(
        id=i,
        project_id="p",
        name=i,
        tool_type_id="tt",
        tool_slug="s",
        config={},
        status="ready",
        status_detail=None,
    )


async def test_assemble_reads_secret_keys_once_and_loads_only_keyed_nodes(monkeypatch):
    repo = MagicMock()
    repo.secret_keys_for_nodes.return_value = {"b": ["api_key"]}
    loaded = []

    def load(node_id, keys):
        loaded.append((node_id, keys))
        return {"api_key": "k"}

    async def verify(ctx):
        return VerifyResult(ok=True)

    spec = ToolSpec("api", lambda c: FunctionToolset(), verify)
    monkeypatch.setattr(assembly, "get_spec", lambda s: spec)
    monkeypatch.setattr(assembly, "load_node_secrets", load)
    monkeypatch.setattr(assembly, "platform_secrets", lambda s: {})

    got = await assembly.assemble(repo, [_tool("a"), _tool("b"), _tool("c")], policy=lambda: "auto")

    repo.secret_keys_for_nodes.assert_called_once_with(["a", "b", "c"])
    repo.secret_keys.assert_not_called()
    assert loaded == [("b", ["api_key"])]
    assert len(got.toolsets) == 3
