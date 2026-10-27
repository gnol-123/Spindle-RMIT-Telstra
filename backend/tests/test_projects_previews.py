"""Projects list carries a signed preview URL; delete clears storage."""

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.project_repo import Project, ProjectRepository
from app.routers import projects as projects_router
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.deps import get_environment_repository, get_project_repository

_P1 = "11111111-1111-1111-1111-111111111111"
_P2 = "22222222-2222-2222-2222-222222222222"


def _override_auth():
    return AuthContext(
        user=UserResponse(id="user-1", email="u@example.com"),
        token="fake-token",  # noqa: S106 - test fixture
    )


class _Repo:
    def __init__(self, thumbs, snap=None):
        self.thumbs = thumbs
        self.snap = snap or {}
        self.stamped = []
        self.deleted = []

    def list_projects(self):
        return [
            Project(
                id=_P1,
                name="a",
                canvas_snapshot_at=self.snap.get(_P1),
                thumbnail_path=self.thumbs.get(_P1),
            ),
            Project(
                id=_P2,
                name="b",
                canvas_snapshot_at=self.snap.get(_P2),
                thumbnail_path=self.thumbs.get(_P2),
            ),
        ]

    def get_project(self, pid):
        return Project(id=pid, name="a") if pid == _P1 else None

    def set_canvas_snapshot_at(self, pid):
        self.stamped.append(pid)

    def delete_project(self, pid):
        self.deleted.append(pid)
        return True


class _Env:
    def list_environment_nodes(self, pid):
        return []


def _client(repo):
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_project_repository] = lambda: repo
    app.dependency_overrides[get_environment_repository] = lambda: _Env()
    return TestClient(app)


def test_list_projects_signs_latest_thumbnail_once(monkeypatch):
    signed = []

    def _sign(paths, expires_s=3600):
        signed.append(paths)
        return {p: f"https://signed/{p}" for p in paths}

    monkeypatch.setattr(projects_router.previews_storage, "sign", _sign)
    repo = _Repo({_P1: f"{_P1}/new.png"})
    try:
        body = _client(repo).get("/projects").json()
    finally:
        app.dependency_overrides.clear()
    assert signed == [[f"{_P1}/new.png"]]
    assert body[0]["preview_url"] == f"https://signed/{_P1}/new.png"
    assert body[1]["preview_url"] is None


def test_list_projects_no_thumbnails_skips_sign(monkeypatch):
    def _boom(*_a, **_k):
        raise AssertionError("sign must not be called")

    monkeypatch.setattr(projects_router.previews_storage, "sign", _boom)
    try:
        body = _client(_Repo({})).get("/projects").json()
    finally:
        app.dependency_overrides.clear()
    assert [p["preview_url"] for p in body] == [None, None]


def test_delete_project_removes_storage(monkeypatch):
    removed = []
    monkeypatch.setattr(projects_router.previews_storage, "remove_project", removed.append)
    repo = _Repo({})
    try:
        r = _client(repo).delete(f"/projects/{_P1}")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 204
    assert removed == [_P1]


def test_delete_project_storage_failure_does_not_fail(monkeypatch):
    def _boom(_pid):
        raise RuntimeError("storage down")

    monkeypatch.setattr(projects_router.previews_storage, "remove_project", _boom)
    try:
        r = _client(_Repo({})).delete(f"/projects/{_P1}")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 204


class _Q:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def select(self, *a):
        self.calls.append(("select", a))
        return self

    def in_(self, k, v):
        self.calls.append(("in_", k, v))
        return self

    @property
    def not_(self):
        return self

    def is_(self, k, v):
        self.calls.append(("is_", k, v))
        return self

    def eq(self, k, v):
        return self

    def limit(self, n, foreign_table=None):
        return self

    def order(self, k, desc=False, foreign_table=None):
        self.calls.append(("order", k, desc))
        return self

    def execute(self):
        return type("R", (), {"data": self.rows})()


def test_list_projects_sign_failure_still_returns_projects(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("storage down")

    monkeypatch.setattr(projects_router.previews_storage, "sign", _boom)
    try:
        r = _client(_Repo({_P1: f"{_P1}/new.png"})).get("/projects")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert [p["preview_url"] for p in r.json()] == [None, None]


def _repo_with(rows):
    q = _Q(rows)
    db = type("Db", (), {"table": lambda self, n: q})()
    return ProjectRepository(db, "u"), q


def test_list_projects_embeds_previews_in_one_query():
    rows = [
        {
            "id": "p1",
            "name": "a",
            "canvas_snapshot_at": None,
            "previews": [{"thumbnail_path": "p1/new.png"}],
        },
        {"id": "p2", "name": "b", "canvas_snapshot_at": "t", "previews": []},
    ]
    repo, q = _repo_with(rows)
    out = repo.list_projects()
    assert [p.thumbnail_path for p in out] == ["p1/new.png", None]
    assert [c[0] for c in q.calls].count("select") == 1


def test_list_projects_ignores_foreign_prefix():
    rows = [
        {"id": "p1", "name": "a", "previews": [{"thumbnail_path": "p2/steal.png"}]},
    ]
    repo, _ = _repo_with(rows)
    assert repo.list_projects()[0].thumbnail_path is None


def _fake_sign(signed):
    def _sign(paths, expires_s=3600):
        signed.append(paths)
        return {p: f"https://signed/{p}" for p in paths}

    return _sign


def test_list_projects_canvas_snapshot_fallback(monkeypatch):
    signed = []
    monkeypatch.setattr(projects_router.previews_storage, "sign", _fake_sign(signed))
    repo = _Repo({_P1: f"{_P1}/new.png"}, snap={_P1: "t", _P2: "t"})
    try:
        body = _client(repo).get("/projects").json()
    finally:
        app.dependency_overrides.clear()
    assert signed == [[f"{_P1}/new.png", f"{_P2}/canvas.webp"]]
    assert body[0]["preview_url"] == f"https://signed/{_P1}/new.png"
    assert body[1]["preview_url"] == f"https://signed/{_P2}/canvas.webp"


def test_list_projects_neither_gives_null(monkeypatch):
    monkeypatch.setattr(projects_router.previews_storage, "sign", _fake_sign([]))
    try:
        body = _client(_Repo({}, snap={_P2: "t"})).get("/projects").json()
    finally:
        app.dependency_overrides.clear()
    assert body[0]["preview_url"] is None
    assert body[1]["preview_url"] == f"https://signed/{_P2}/canvas.webp"


def _put(repo, monkeypatch, *, body=b"img", ctype="image/webp", pid=_P1, headers=None, up=None):
    uploads = []
    monkeypatch.setattr(
        projects_router.previews_storage,
        "upload_canvas_snapshot",
        up or (lambda *a: uploads.append(a) or f"{a[0]}/canvas.webp"),
    )
    try:
        r = _client(repo).put(
            f"/projects/{pid}/canvas-snapshot",
            content=body,
            headers={"content-type": ctype, **(headers or {})},
        )
    finally:
        app.dependency_overrides.clear()
    return r, uploads


def test_put_snapshot_owner_204(monkeypatch):
    repo = _Repo({})
    r, uploads = _put(repo, monkeypatch, ctype="image/png")
    assert r.status_code == 204
    assert uploads == [(_P1, b"img", "image/png")]
    assert repo.stamped == [_P1]


def test_put_snapshot_missing_project_404(monkeypatch):
    repo = _Repo({})
    r, uploads = _put(repo, monkeypatch, pid=_P2)
    assert r.status_code == 404
    assert uploads == [] and repo.stamped == []


def test_put_snapshot_bad_type_415(monkeypatch):
    r, _ = _put(_Repo({}), monkeypatch, ctype="text/plain")
    assert r.status_code == 415


def test_put_snapshot_too_big_413(monkeypatch):
    r, _ = _put(_Repo({}), monkeypatch, body=b"x" * 2_000_001)
    assert r.status_code == 413


def test_put_snapshot_empty_400(monkeypatch):
    r, _ = _put(_Repo({}), monkeypatch, body=b"")
    assert r.status_code == 400


def test_put_snapshot_storage_failure_502(monkeypatch):
    def _boom(*_a):
        raise RuntimeError("secret-key-here")

    repo = _Repo({})
    r, _ = _put(repo, monkeypatch, up=_boom)
    assert r.status_code == 502
    assert "secret" not in r.text
    assert repo.stamped == []
