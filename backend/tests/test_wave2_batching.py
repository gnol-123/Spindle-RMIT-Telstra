"""Bulk default wiring, cached preview URLs, scratch pre-read skip."""

import pytest
from fastapi.testclient import TestClient
from test_environment_repo import _PROJECT, _FakeDB, _repo

import app.routers.projects as projects
from app.main import app
from app.repositories.project_repo import AgentType, Edge, Project
from app.repositories.tool_repo import ToolPreset, ToolType
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.deps import get_environment_repository, get_project_repository
from app.services import previews_storage

_TYPE = ToolType(
    id="t1", slug="skill", name="Skill", description=None,
    config_schema={"fields": [], "default_url": "https://x"}, secret_fields=[],
)  # fmt: skip
_PRESETS = [
    ToolPreset(
        id=f"p{i}",
        slug=f"s{i}",
        name=f"S{i}",
        description=None,
        tool_type_id="t1",
        tool_slug="skill",
        config={},
    )  # fmt: skip
    for i in range(3)
]
_AGENT = AgentType(
    id="a1", slug="x", name="X", description=None, system_prompt="", model="m",
    default_presets=[p.slug for p in _PRESETS],
)  # fmt: skip


class _ToolRepo:
    def __init__(self, bulk_fails=False):
        self.bulk_fails = bulk_fails
        self.bulk_calls = []
        self.single_calls = []

    def list_presets(self):
        return _PRESETS

    def list_tool_types(self):
        return [_TYPE]

    def create_tool_nodes(self, project_id, rows):
        self.bulk_calls.append(rows)
        if self.bulk_fails:
            raise RuntimeError("boom")
        return [f"tool-{i}" for i in range(len(rows))]

    def create_tool_node(self, project_id, type_id, name, config, *, position_x, position_y):
        self.single_calls.append((name, config, position_y))
        return f"single-{len(self.single_calls)}"


def _edge(s, t, k):
    return Edge(
        id="e", source_node_id=s, target_node_id=t, kind=k, summary=None,
        summarised_through_seq=None, summary_updated_at=None, summary_max_words=200,
    )  # fmt: skip


class _Repo:
    def __init__(self):
        self.bulk_edges = []
        self.single_edges = []

    def create_node(self, *a, **k):
        return "node-1"

    def create_conversation(self, node_id, project_id):
        return "conv-1"

    def create_edges(self, edges):
        self.bulk_edges.append(list(edges))
        return [_edge(*e) for e in edges]

    def create_edge(self, s, t, k):
        self.single_edges.append((s, t, k))
        return _edge(s, t, k)


class _Env:
    def ensure_scratch_node(self, project_id, new_project=False):
        return type("N", (), {"id": "scratch"})()


async def _provision(tool_repo, repo):
    return await projects.provision_agent(
        "p1", _AGENT, "X", position_x=0, position_y=0, tool_policy="ask",
        repo=repo, tool_repo=tool_repo, env_repo=_Env(),
    )  # fmt: skip


@pytest.mark.anyio
async def test_defaults_use_one_bulk_tool_insert_and_one_bulk_edge_insert(monkeypatch):
    monkeypatch.setattr(projects, "_verify_in_background", lambda ids, r: None)
    tools, repo = _ToolRepo(), _Repo()
    await _provision(tools, repo)
    assert len(tools.bulk_calls) == 1 and tools.single_calls == []
    assert [r["position_y"] for r in tools.bulk_calls[0]] == [0, 90, 180]
    assert tools.bulk_calls[0][0]["config"] == {"url": "https://x"}
    assert len(repo.bulk_edges) == 1 and repo.single_edges == []
    assert repo.bulk_edges[0][0] == ("scratch", "node-1", "environment")
    assert len(repo.bulk_edges[0]) == 4


@pytest.mark.anyio
async def test_bulk_tool_insert_failure_falls_back_per_preset(monkeypatch):
    monkeypatch.setattr(projects, "_verify_in_background", lambda ids, r: None)
    tools, repo = _ToolRepo(bulk_fails=True), _Repo()
    await _provision(tools, repo)
    assert len(tools.single_calls) == 3
    assert len(repo.bulk_edges[0]) == 4


@pytest.mark.anyio
async def test_bulk_edge_failure_falls_back_per_edge(monkeypatch):
    monkeypatch.setattr(projects, "_verify_in_background", lambda ids, r: None)
    tools, repo = _ToolRepo(), _Repo()

    def boom(edges):
        raise RuntimeError("boom")

    repo.create_edges = boom
    await _provision(tools, repo)
    assert len(repo.single_edges) == 4


# -- projects list ---------------------------------------------------------------

_P1 = "11111111-1111-1111-1111-111111111111"
_P2 = "22222222-2222-2222-2222-222222222222"


class _ListRepo:
    def __init__(self):
        self.snap = "t1"
        self.list_calls = 0

    def list_projects(self):
        self.list_calls += 1
        return [
            Project(id=_P1, name="a", thumbnail_path=f"{_P1}/new.png"),
            Project(id=_P2, name="b", canvas_snapshot_at=self.snap),
        ]


def _get(repo):
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user=UserResponse(id="u", email="u@example.com"),
        token="t",  # noqa: S106
    )
    app.dependency_overrides[get_project_repository] = lambda: repo
    app.dependency_overrides[get_environment_repository] = lambda: object()
    try:
        return TestClient(app).get("/projects").json()
    finally:
        app.dependency_overrides.clear()


def test_list_uses_one_query_and_signs_only_misses(monkeypatch):
    signed = []

    def sign(paths, expires_s=3600):
        signed.append(list(paths))
        return {p: f"https://s/{p}?n={len(signed)}" for p in paths}

    monkeypatch.setattr(previews_storage, "sign", sign)
    repo = _ListRepo()
    first = _get(repo)
    assert repo.list_calls == 1
    assert signed == [[f"{_P1}/new.png", f"{_P2}/canvas.webp"]]

    assert _get(repo) == first  # all cached, nothing signed
    assert len(signed) == 1

    # New canvas snapshot: only the canvas path is re-signed, URL changes.
    repo.snap = "t2"
    third = _get(repo)
    assert signed[1] == [f"{_P2}/canvas.webp"]
    assert third[0] == first[0] and third[1]["preview_url"] != first[1]["preview_url"]


def test_canvas_snapshot_put_changes_cache_key(monkeypatch):
    n = []
    monkeypatch.setattr(
        previews_storage,
        "sign",
        lambda paths, e=3600: {p: f"u{len(n.append(1) or n)}" for p in paths},
    )
    path = f"{_P1}/canvas.webp"
    a = previews_storage.sign_cached({path: "t1"})
    assert previews_storage.sign_cached({path: "t1"}) == a
    assert previews_storage.sign_cached({path: "t2"}) != a


def test_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(previews_storage, "_MAX_CACHED", 2)
    monkeypatch.setattr(previews_storage, "sign", lambda paths, e=3600: {p: p for p in paths})
    previews_storage.sign_cached({"a": None, "b": None})
    previews_storage.sign_cached({"c": None})
    assert len(previews_storage._cache) == 1


# -- create_project --------------------------------------------------------------


def test_new_project_scratch_skips_the_pre_read():
    db = _FakeDB([])
    node = _repo(db).ensure_scratch_node(_PROJECT, new_project=True)
    assert node.role == "scratch"
    assert [op for _t, op, _f in db.ops] == ["insert"]
