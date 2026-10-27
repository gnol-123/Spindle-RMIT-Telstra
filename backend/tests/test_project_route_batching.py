"""Batched reads in the project routes: node kinds, edge heads, scratch create."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.environment_repo import EnvironmentRepository
from app.repositories.project_repo import Edge, ProjectRepository
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.deps import get_project_repository

_P = "11111111-1111-1111-1111-111111111111"
_OTHER = "99999999-9999-9999-9999-999999999999"
_A, _B, _T = (f"2222222{i}-2222-2222-2222-222222222222" for i in range(3))
_E = "77777777-7777-7777-7777-777777777777"
_X = "88888888-8888-8888-8888-888888888888"
_USER = "55555555-5555-5555-5555-555555555555"


class _Q:
    def __init__(self, db, table):
        self.db, self.table, self.op, self.payload, self.f = db, table, "select", None, {}

    def select(self, *_):
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def eq(self, k, v):
        self.f[k] = v
        return self

    def in_(self, k, vs):
        self.f[k] = list(vs)
        return self

    def order(self, *_, **__):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        self.db.log.append((self.table, self.op, dict(self.f)))
        if self.op == "insert":
            return type("R", (), {"data": [{"id": "new", **self.payload}]})()
        rows = []
        for r in self.db.rows.get(self.table, []):
            ok = all(
                r.get(k) in v if isinstance(v, list) else r.get(k) == v for k, v in self.f.items()
            )
            if ok:
                rows.append(r)
        return type("R", (), {"data": rows})()


class _Db:
    def __init__(self, rows):
        self.rows, self.log = rows, []

    def table(self, name):
        return _Q(self, name)


def _post(db, source, target, kind):
    repo = ProjectRepository(db, _USER)
    repo.get_project = lambda pid: object()
    repo.create_edge = lambda s, t, k: Edge(_P, s, t, k, None, None, None, 200)
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user=UserResponse(id=_USER, email="t@e.com"),
        token="test-token",  # noqa: S106
    )
    app.dependency_overrides[get_project_repository] = lambda: repo
    try:
        return TestClient(app).post(
            f"/projects/{_P}/edges",
            json={"source_node_id": source, "target_node_id": target, "kind": kind},
        )
    finally:
        app.dependency_overrides.clear()


def _nodes():
    return {
        "nodes": [
            {"id": _A, "project_id": _P, "kind": "agent", "owner_id": _USER},
            {"id": _B, "project_id": _P, "kind": "agent", "owner_id": _USER},
            {"id": _T, "project_id": _OTHER, "kind": "tool", "owner_id": _USER},
        ]
    }


def test_create_edge_kind_check_is_one_nodes_query():
    db = _Db(_nodes())
    assert _post(db, _A, _B, "context").status_code == 201
    assert [t for t, _, _ in db.log] == ["nodes"]


def test_create_edge_wrong_kinds_422():
    r = _post(_Db(_nodes()), _A, _B, "tool")
    assert r.status_code == 422
    assert "tool to agent" in r.json()["detail"]


def test_create_edge_missing_or_foreign_node_404():
    missing = "33333333-3333-3333-3333-333333333333"
    assert _post(_Db(_nodes()), _A, missing, "context").status_code == 404
    assert _post(_Db(_nodes()), _T, _A, "tool").status_code == 404


@pytest.mark.anyio
async def test_list_edges_heads_for_many_sources_and_none():
    from app.routers.projects import list_edges

    db = _Db(
        {
            "conversations": [
                {"id": "c1", "node_id": _A, "owner_id": _USER},
                {"id": "c2", "node_id": _B, "owner_id": _USER},
            ],
            "messages": [
                {"conversation_id": "c1", "seq": 5, "status": "complete", "owner_id": _USER},
                {"conversation_id": "c2", "seq": 9, "status": "running", "owner_id": _USER},
            ],
        }
    )
    repo = ProjectRepository(db, _USER)
    repo.get_project = lambda pid: object()
    # _T has no conversation; _B has no complete row.
    edges = [
        Edge(_E, _A, _X, "context", "s", 2, None, 200),
        Edge(_E, _B, _X, "context", "s", 0, None, 200),
        Edge(_E, _T, _X, "context", "s", 1, None, 200),
        Edge(_E, _A, _X, "context", "s", 5, None, 200),
    ]
    repo.list_edges = lambda pid: edges
    out = await list_edges(_P, repo)
    assert [e.messages_behind for e in out] == [3, 0, 0, 0]
    assert sum(t == "conversations" for t, _, _ in db.log) == 1


def test_ensure_scratch_create_path_does_not_reread():
    db = _Db({})
    node = EnvironmentRepository(db, _USER).ensure_scratch_node(_P)
    assert node.id == "new" and node.role == "scratch"
    assert [op for _, op, _ in db.log] == ["select", "insert"]
