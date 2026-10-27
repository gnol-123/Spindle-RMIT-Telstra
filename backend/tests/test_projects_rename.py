"""PATCH /projects/{id} renames an owned project."""

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.main import app
from app.repositories.project_repo import DuplicateProjectName, Project, ProjectRepository
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.deps import get_project_repository

_P1 = "11111111-1111-1111-1111-111111111111"
_P2 = "22222222-2222-2222-2222-222222222222"


class _Repo:
    def __init__(self):
        self.calls = []

    def rename_project(self, pid, name):
        self.calls.append((pid, name))
        if name == "taken":
            raise DuplicateProjectName(name)
        return Project(id=pid, name=name) if pid == _P1 else None


def _patch(pid, body, repo=None, authed=True):
    if authed:
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(
            user=UserResponse(id="u", email="u@example.com"),
            token="t",  # noqa: S106 - test fixture
        )
    if authed:
        app.dependency_overrides[get_project_repository] = lambda: repo or _Repo()
    try:
        return TestClient(app).patch(f"/projects/{pid}", json=body)
    finally:
        app.dependency_overrides.clear()


def test_rename_ok_strips():
    repo = _Repo()
    r = _patch(_P1, {"name": "  new  "}, repo)
    assert r.status_code == 200
    assert r.json()["name"] == "new"
    assert repo.calls == [(_P1, "new")]


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_rename_invalid_422(name):
    assert _patch(_P1, {"name": name}).status_code == 422


def test_rename_duplicate_409():
    r = _patch(_P1, {"name": "taken"})
    assert r.status_code == 409
    assert "taken" in r.json()["detail"]


def test_rename_missing_or_foreign_404():
    assert _patch(_P2, {"name": "x"}).status_code == 404


def test_rename_unauthenticated_401():
    assert _patch(_P1, {"name": "x"}, authed=False).status_code == 401


class _Q:
    def __init__(self, rows=None, err=None):
        self.rows, self.err, self.calls = rows or [], err, []

    def update(self, p):
        self.calls.append(("update", p))
        return self

    def eq(self, k, v):
        self.calls.append(("eq", k, v))
        return self

    def execute(self):
        if self.err:
            raise self.err
        return type("R", (), {"data": self.rows})()


def _repo(q):
    return ProjectRepository(type("Db", (), {"table": lambda self, n: q})(), "u1")


def test_repo_rename_owner_scoped():
    q = _Q([{"id": "p", "name": "n"}])
    assert _repo(q).rename_project("p", "n") == Project(id="p", name="n")
    assert ("eq", "owner_id", "u1") in q.calls


def test_repo_rename_none_when_no_row():
    assert _repo(_Q()).rename_project("p", "n") is None


def test_repo_rename_unique_violation():
    err = APIError({"message": "dup", "code": "23505", "details": "", "hint": ""})
    with pytest.raises(DuplicateProjectName):
        _repo(_Q(err=err)).rename_project("p", "n")
