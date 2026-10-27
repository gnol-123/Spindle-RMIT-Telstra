"""The five canvas tools, their guards, placement, staleness and ask-mode gating."""

import json

import pytest

import app.tools.canvas as canvas
from app.repositories.environment_repo import EnvNode
from app.repositories.project_repo import AgentType, DuplicateEdge, Edge, Message, Node
from app.repositories.tool_repo import ToolNode
from app.routers.deps import TurnRepositories
from app.workflows import ChatTurn


def _node(id, x=0, y=0, agent_type_id="at-stage", policy="auto", slug="coding", kind="agent"):
    return Node(
        id=id,
        project_id="p",
        name=id,
        agent_type_id=agent_type_id,
        system_prompt="s",
        model="m",
        tool_policy=policy,
        position_x=x,
        position_y=y,
        kind=kind,
        agent_slug=slug,
    )


ORCH = _node("orch", x=100, y=50, agent_type_id="at-orch", slug="orchestrator")


class _Repo:
    def __init__(self, nodes=()):
        self.nodes = {n.id: n for n in nodes}
        self.edges = []
        self.pending = {}
        self.types = [
            AgentType(
                id="at-orch",
                slug="orchestrator",
                name="Orchestrator",
                description="d",
                system_prompt="s",
                model="m",
                default_presets=["canvas"],
            ),
            AgentType(
                id="at-stage",
                slug="coding",
                name="Coding",
                description="d",
                system_prompt="s",
                model="m",
                default_presets=[],
            ),
        ]

    # project repo
    def list_agent_types(self):
        return self.types

    def get_agent_type(self, slug):
        return next((t for t in self.types if t.slug == slug), None)

    def list_nodes(self, project_id):
        return list(self.nodes.values())

    def get_agent_node(self, node_id):
        n = self.nodes.get(node_id)
        return n if n and n.kind == "agent" else None

    def list_edges(self, project_id):
        return getattr(self, "context_edges", [])

    def list_outbound_context_edges(self, node_id):
        return [e for e in getattr(self, "context_edges", []) if e.source_node_id == node_id]

    def get_conversation_head(self, node_id):
        return getattr(self, "heads", {}).get(node_id, 0)

    def get_or_create_conversation(self, node_id, project_id):
        return f"conv-{node_id}"

    def get_conversation_for_node(self, node_id):
        return f"conv-{node_id}"

    def list_messages(self, conversation_id, limit=50):
        return []

    def create_edge(self, source, target, kind="context", summary_max_words=None):
        key = (source, target, kind)
        if key in self.edges:
            raise DuplicateEdge("dup")
        self.edges.append(key)
        self.last_words = summary_max_words
        return object()

    def list_inbound_environment_node_ids(self, node_id):
        return [e[0] for e in self.edges if e[2] == "environment" and e[1] == node_id]

    def list_inbound_tool_node_ids(self, node_id):
        return [e[0] for e in self.edges if e[2] == "tool" and e[1] == node_id]

    def get_tool_nodes(self, ids):
        return [n for n in map(self.get_tool_node, ids) if n is not None]

    def get_tool_node(self, node_id):
        return getattr(self, "tool_nodes", {}).get(node_id)

    # env repo
    def get_environment_nodes(self, ids):
        return [n for n in map(self.get_environment_node, ids) if n is not None]

    def get_environment_node(self, node_id):
        return getattr(self, "envs", {}).get(node_id)

    def create_environment_node(
        self, project_id, name, config, *, tool_policy="ask", position_x=0.0, position_y=0.0
    ):
        env_id = f"env-{len(getattr(self, 'envs', {})) + 1}"
        node = EnvNode(
            id=env_id,
            project_id=project_id,
            name=name,
            config=config,
            status="pending",
            status_detail=None,
            tool_policy=tool_policy,
            position_x=position_x,
            position_y=position_y,
        )
        self.envs = {**getattr(self, "envs", {}), env_id: node}
        self.created_env = node
        return env_id

    # tool repo
    def get_pending_run(self, conversation_id):
        return self.pending.get(conversation_id)


def _tools(repo, conversation_id="conv-orch"):
    repos = TurnRepositories(project=repo, tool=repo, env=repo, user_id="u")
    return canvas.CanvasTools(repos, ORCH, conversation_id)


# create_agent ---------------------------------------------------------------


@pytest.mark.anyio
async def test_create_agent_places_first_in_row_below(monkeypatch):
    seen = {}

    async def fake_provision(project_id, agent_type, name, **kw):
        seen.update(kw, project_id=project_id)
        return "new"

    monkeypatch.setattr(canvas, "provision_agent", fake_provision)
    out = await _tools(_Repo([ORCH])).create_agent("coding", "Coding")

    assert "new" in out
    assert seen["project_id"] == "p"
    assert seen["tool_policy"] == "auto"
    assert (seen["position_x"], seen["position_y"]) == (100, 50 + canvas._STAGE_DY)


@pytest.mark.anyio
async def test_create_agent_continues_row(monkeypatch):
    async def fake_provision(project_id, agent_type, name, **kw):
        assert kw["position_x"] == 100 + canvas._STAGE_DX
        return "new"

    monkeypatch.setattr(canvas, "provision_agent", fake_provision)
    existing = _node("scoping", x=100, y=50 + canvas._STAGE_DY)
    await _tools(_Repo([ORCH, existing])).create_agent("coding", "Coding")


@pytest.mark.anyio
async def test_create_agent_refuses_orchestrator_and_unknown():
    t = _tools(_Repo([ORCH]))
    assert "refused" in (await t.create_agent("orchestrator", "X")).lower()
    assert "coding" in await t.create_agent("nope", "X")


@pytest.mark.anyio
async def test_create_agent_duplicate_name_returns_existing(monkeypatch):
    async def never(*a, **k):
        raise AssertionError("must not provision")

    monkeypatch.setattr(canvas, "provision_agent", never)
    out = await _tools(_Repo([ORCH, _node("Coding")])).create_agent("coding", "Coding")
    assert "Coding" in out and "already" in out.lower()


# connect --------------------------------------------------------------------


@pytest.mark.anyio
async def test_connect_creates_with_words_and_reports_duplicate():
    repo = _Repo([ORCH, _node("a"), _node("b")])
    t = _tools(repo)
    assert "connected" in (await t.connect("a", "b")).lower()
    assert repo.last_words == 1000
    assert "already" in (await t.connect("a", "b")).lower()


@pytest.mark.anyio
async def test_connect_summarises_a_source_that_already_replied(monkeypatch):
    seen = []

    async def fake_refresh(repo, edge):
        seen.append(edge)
        return edge

    monkeypatch.setattr(canvas, "refresh_edge", fake_refresh)
    repo = _Repo([ORCH, _node("a"), _node("b")])
    repo.heads = {"a": 4}
    out = await _tools(repo).connect("a", "b")
    assert len(seen) == 1
    assert "summary generated" in out.lower()


@pytest.mark.anyio
async def test_connect_skips_summary_for_a_silent_source(monkeypatch):
    async def never(repo, edge):
        raise AssertionError("must not refresh")

    monkeypatch.setattr(canvas, "refresh_edge", never)
    out = await _tools(_Repo([ORCH, _node("a"), _node("b")])).connect("a", "b")
    assert "connected" in out.lower()


@pytest.mark.anyio
async def test_connect_keeps_edge_when_summary_fails(monkeypatch):
    async def boom(repo, edge):
        raise RuntimeError("summariser down")

    monkeypatch.setattr(canvas, "refresh_edge", boom)
    repo = _Repo([ORCH, _node("a"), _node("b")])
    repo.heads = {"a": 2}
    out = await _tools(repo).connect("a", "b")
    assert ("a", "b", "context") in repo.edges
    assert "connected" in out.lower() and "could not" in out.lower()


@pytest.mark.anyio
async def test_connect_refuses_unknown_or_foreign_node():
    t = _tools(_Repo([ORCH, _node("a")]))
    assert "not found" in (await t.connect("a", "ghost")).lower()


@pytest.mark.anyio
async def test_connect_refuses_self_loop():
    t = _tools(_Repo([ORCH, _node("a")]))
    assert "itself" in (await t.connect("a", "a")).lower()


# run_agent ------------------------------------------------------------------


def _prepared():
    from app.services.turns import PreparedTurn
    from app.tools.assembly import AssembledTools

    return PreparedTurn(instructions="ctx", toolsets=[], tools=AssembledTools())


@pytest.mark.anyio
async def test_run_agent_runs_turn_refreshes_and_returns_head(monkeypatch):
    seen = {}

    async def fake_prepare(repos, node, conversation_id, *, nested=False):
        seen["nested"] = nested
        return _prepared()

    async def fake_run_turn(repo, conversation_id, system_prompt, model, prompt, **kw):
        seen["instructions"] = kw["instructions"]
        return ChatTurn(
            conversation_id=conversation_id,
            user_message=None,
            assistant_message=None,
            output="x" * 7000,
        )

    async def fake_refresh(repo, node_id):
        seen["refreshed"] = node_id
        return []

    monkeypatch.setattr(canvas, "prepare_turn", fake_prepare)
    monkeypatch.setattr(canvas, "run_turn", fake_run_turn)
    monkeypatch.setattr(canvas, "refresh_outbound", fake_refresh)

    out = await _tools(_Repo([ORCH, _node("a")])).run_agent("a", "go")

    assert seen["nested"] is True
    assert canvas.UNATTENDED_INSTRUCTION in seen["instructions"]
    assert "ctx" in seen["instructions"]
    assert seen["refreshed"] == "a"
    assert len(out) < 7000 and "truncated" in out.lower()


@pytest.mark.anyio
async def test_run_agent_guards():
    repo = _Repo([ORCH, _node("a"), _node("orch2", agent_type_id="at-orch")])
    t = _tools(repo)
    assert "refused" in (await t.run_agent("orch", "x")).lower()
    assert "refused" in (await t.run_agent("orch2", "x")).lower()
    assert "not found" in (await t.run_agent("ghost", "x")).lower()
    repo.pending["conv-a"] = ("payload", None)
    assert "approval" in (await t.run_agent("a", "x")).lower()


@pytest.mark.anyio
async def test_run_agent_reports_failed_and_paused(monkeypatch):
    async def fake_prepare(repos, node, conversation_id, *, nested=False):
        return _prepared()

    monkeypatch.setattr(canvas, "prepare_turn", fake_prepare)

    async def failed(repo, conversation_id, system_prompt, model, prompt, **kw):
        m = Message(id="m", role="assistant", content="", seq=2, status="failed", created_at="t")
        return ChatTurn(
            conversation_id=conversation_id,
            user_message=None,
            assistant_message=m,
            output="",
            error="boom",
        )

    monkeypatch.setattr(canvas, "run_turn", failed)
    out = await _tools(_Repo([ORCH, _node("a")])).run_agent("a", "x")
    assert "failed" in out.lower()
    assert "boom" in out

    async def paused(repo, conversation_id, system_prompt, model, prompt, **kw):
        return ChatTurn(
            conversation_id=conversation_id,
            user_message=None,
            assistant_message=None,
            output="",
            pending=object(),
        )

    monkeypatch.setattr(canvas, "run_turn", paused)
    assert "approval" in (await _tools(_Repo([ORCH, _node("a")])).run_agent("a", "x")).lower()


# assemble -------------------------------------------------------------------


def _canvas_node():
    return ToolNode(
        id="cv",
        project_id="p",
        name="Canvas",
        tool_type_id="tt",
        tool_slug="canvas",
        config={},
        status="ready",
        status_detail=None,
    )


@pytest.mark.anyio
async def test_assemble_auto_is_plain_and_sequential():
    repos = TurnRepositories(project=_Repo(), tool=_Repo(), env=_Repo(), user_id="u")
    out = await canvas.assemble_canvas(
        repos, ORCH, [_canvas_node()], "conv-orch", policy=lambda: "auto"
    )
    assert set(out.owner_by_tool) == set(canvas.TOOL_NAMES)
    assert out.owner_by_toolset == ["cv"]
    assert await out.toolsets[0]._asks() is False
    assert out.toolsets[0].wrapped.sequential is True


@pytest.mark.anyio
async def test_assemble_ask_gates_only_run_agent():
    repos = TurnRepositories(project=_Repo(), tool=_Repo(), env=_Repo(), user_id="u")
    out = await canvas.assemble_canvas(
        repos, ORCH, [_canvas_node()], "conv-orch", policy=lambda: "ask"
    )
    gate = out.toolsets[0]
    assert await gate._asks() is True
    assert gate.only == {"run_agent", "evaluate"}


@pytest.mark.anyio
async def test_assemble_second_canvas_box_unavailable():
    repos = TurnRepositories(project=_Repo(), tool=_Repo(), env=_Repo(), user_id="u")
    second = ToolNode(
        id="cv2",
        project_id="p",
        name="Canvas 2",
        tool_type_id="tt",
        tool_slug="canvas",
        config={},
        status="ready",
        status_detail=None,
    )
    out = await canvas.assemble_canvas(
        repos, ORCH, [_canvas_node(), second], "conv-orch", policy=lambda: "auto"
    )
    assert out.unavailable == ["Canvas 2"]


def test_list_canvas_is_json():
    import asyncio

    out = asyncio.run(_tools(_Repo([ORCH, _node("a")])).list_canvas())
    data = json.loads(out)
    assert {"agent_types", "agents", "edges"} <= set(data)
    assert data["agents"][0]["id"] in {"orch", "a"}


# refresh_context + staleness ------------------------------------------------


def _ctx_edge(src, tgt, through=None, words=1000):
    return Edge(
        id=f"e-{src}-{tgt}",
        source_node_id=src,
        target_node_id=tgt,
        kind="context",
        summary="s" if through is not None else None,
        summarised_through_seq=through,
        summary_updated_at=None,
        summary_max_words=words,
    )


@pytest.mark.anyio
async def test_list_canvas_reports_staleness():
    """Stale when never summarised, or when the source has moved past the summary."""
    repo = _Repo([ORCH, _node("a"), _node("b"), _node("c")])
    repo.context_edges = [
        _ctx_edge("a", "b", through=None),  # never summarised
        _ctx_edge("a", "c", through=4),  # source head is 4: covered
        _ctx_edge("b", "c", through=1),  # source head is 3: moved on
    ]
    repo.heads = {"a": 4, "b": 3}
    data = json.loads(await _tools(repo).list_canvas())
    stale = {(e["source_node_id"], e["target_node_id"]): e["is_stale"] for e in data["edges"]}
    assert stale[("a", "b")] is True
    assert stale[("a", "c")] is False
    assert stale[("b", "c")] is True


@pytest.mark.anyio
async def test_refresh_context_refreshes_outbound(monkeypatch):
    seen = {}

    async def fake_refresh(repo, node_id):
        seen["node_id"] = node_id
        return []

    monkeypatch.setattr(canvas, "refresh_outbound", fake_refresh)
    repo = _Repo([ORCH, _node("a"), _node("b")])
    repo.context_edges = [_ctx_edge("a", "b", through=1)]

    out = await _tools(repo).refresh_context("a")

    assert seen["node_id"] == "a"
    assert "Refreshed 1" in out


@pytest.mark.anyio
async def test_refresh_context_reports_failures(monkeypatch):
    async def fake_refresh(repo, node_id):
        return ["e-a-b"]

    monkeypatch.setattr(canvas, "refresh_outbound", fake_refresh)
    repo = _Repo([ORCH, _node("a"), _node("b")])
    repo.context_edges = [_ctx_edge("a", "b", through=1), _ctx_edge("a", "orch", through=1)]

    out = await _tools(repo).refresh_context("a")

    assert "Failed: e-a-b" in out
    assert "1 of 2" in out


@pytest.mark.anyio
async def test_refresh_context_guards(monkeypatch):
    async def never(repo, node_id):
        raise AssertionError("must not refresh")

    monkeypatch.setattr(canvas, "refresh_outbound", never)
    repo = _Repo([ORCH, _node("a")])

    assert "not found" in (await _tools(repo).refresh_context("ghost")).lower()
    # No outbound edges: nothing to do, and no summariser call.
    assert "nothing to refresh" in (await _tools(repo).refresh_context("a")).lower()


@pytest.mark.anyio
async def test_ask_mode_does_not_gate_refresh_context():
    repos = TurnRepositories(project=_Repo(), tool=_Repo(), env=_Repo(), user_id="u")
    out = await canvas.assemble_canvas(
        repos, ORCH, [_canvas_node()], "conv-orch", policy=lambda: "ask"
    )
    assert "refresh_context" not in out.toolsets[0].only


# give_environment -----------------------------------------------------------


@pytest.mark.anyio
async def test_give_environment_creates_and_wires_auto_policy():
    repo = _Repo([ORCH, _node("a", x=900, y=370)])
    out = await _tools(repo).give_environment("a")

    env = repo.created_env
    assert env.config["role"] == "user"
    assert env.tool_policy == "auto"  # nobody is there to approve shell commands
    assert env.position_x == 900 + canvas._ENV_DX
    assert (env.id, "a", "environment") in repo.edges
    assert env.id in out


@pytest.mark.anyio
async def test_give_environment_uses_custom_name():
    repo = _Repo([ORCH, _node("a")])
    await _tools(repo).give_environment("a", "Build Box")
    assert repo.created_env.name == "Build Box"


@pytest.mark.anyio
async def test_give_environment_is_idempotent():
    repo = _Repo([ORCH, _node("a")])
    await _tools(repo).give_environment("a")
    first = repo.created_env.id

    out = await _tools(repo).give_environment("a")

    assert "already has" in out.lower()
    assert repo.created_env.id == first  # no second sandbox


@pytest.mark.anyio
async def test_give_environment_ignores_scratch_when_checking():
    """Scratch is wired to every agent; it must not count as the agent's own."""
    repo = _Repo([ORCH, _node("a")])
    repo.envs = {
        "scratch-1": EnvNode(
            id="scratch-1",
            project_id="p",
            name="Scratch Space",
            config={"role": "scratch"},
            status="ready",
            status_detail=None,
            tool_policy="auto",
            position_x=0,
            position_y=0,
        )
    }
    repo.edges.append(("scratch-1", "a", "environment"))

    out = await _tools(repo).give_environment("a")

    assert "gave" in out.lower()
    assert repo.created_env.config["role"] == "user"


@pytest.mark.anyio
async def test_give_environment_refuses_unknown_node():
    repo = _Repo([ORCH])
    assert "not found" in (await _tools(repo).give_environment("ghost")).lower()


def _user_env(repo, env_id, owner):
    env = EnvNode(
        id=env_id,
        project_id="p",
        name=env_id,
        config={"role": "user"},
        status="ready",
        status_detail=None,
        tool_policy="auto",
        position_x=0,
        position_y=0,
    )
    repo.envs = {**getattr(repo, "envs", {}), env_id: env}
    repo.edges.append((env_id, owner, "environment"))


@pytest.mark.anyio
async def test_give_environment_share_from_reuses_env():
    repo = _Repo([ORCH, _node("code"), _node("pitch", slug="scrutinizer")])
    _user_env(repo, "env-code", "code")
    out = await _tools(repo).give_environment("pitch", share_from="code")
    assert ("env-code", "pitch", "environment") in repo.edges
    assert not hasattr(repo, "created_env")
    assert "env-code" in out


@pytest.mark.anyio
async def test_give_environment_share_from_without_env_refuses():
    repo = _Repo([ORCH, _node("code"), _node("pitch")])
    out = await _tools(repo).give_environment("pitch", share_from="code")
    assert "no environment" in out.lower()
    assert not hasattr(repo, "created_env")


@pytest.mark.anyio
async def test_give_environment_share_from_unknown_refuses():
    repo = _Repo([ORCH, _node("pitch")])
    assert "not found" in (await _tools(repo).give_environment("pitch", share_from="ghost")).lower()
