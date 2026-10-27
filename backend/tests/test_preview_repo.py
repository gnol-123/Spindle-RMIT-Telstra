"""PreviewRepository against a fake PostgREST client. No database."""

from typing import Any

from app.repositories.preview_repo import PreviewRepository, PreviewRow

_PROJECT = "11111111-1111-1111-1111-111111111111"
_ENV = "22222222-2222-2222-2222-222222222222"
_AGENT = "33333333-3333-3333-3333-333333333333"


class _Result:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _Query:
    def __init__(self, db: "_FakeDB", op: str, payload: Any = None, on_conflict: str = "") -> None:
        self._db, self._op, self._payload, self._conflict = db, op, payload, on_conflict
        self.filters: dict[str, Any] = {}
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, *_a: Any, **_k: Any) -> "_Query":
        return self

    def eq(self, key: str, value: Any) -> "_Query":
        self.filters[key] = value
        return self

    def order(self, col: str, desc: bool = False) -> "_Query":
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    def execute(self) -> _Result:
        return self._db.run(self)


class _FakeDB:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._n = 0

    def table(self, name: str) -> "_Table":
        assert name == "previews"
        return _Table(self)

    def run(self, q: _Query) -> _Result:
        match = [r for r in self.rows if all(r.get(k) == v for k, v in q.filters.items())]
        if q._op == "upsert":
            key = q._conflict.split(",")
            hit = next((r for r in self.rows if all(r[k] == q._payload[k] for k in key)), None)
            if hit:
                hit.update(q._payload)
                return _Result([hit])
            self._n += 1
            row = {"id": f"id-{self._n}", "thumbnail_path": None, **q._payload}
            self.rows.append(row)
            return _Result([row])
        if q._op == "update":
            for r in match:
                r.update(q._payload)
            return _Result(match)
        if q._op == "delete":
            self.rows = [r for r in self.rows if r not in match]
            return _Result(match)
        if q._order:
            match.sort(key=lambda r: r[q._order[0]], reverse=q._order[1])
        return _Result(match[: q._limit] if q._limit else match)


class _Table:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db

    def select(self, *_a: Any, **_k: Any) -> _Query:
        return _Query(self._db, "select")

    def upsert(self, payload: dict, on_conflict: str = "") -> _Query:
        return _Query(self._db, "upsert", payload, on_conflict)

    def update(self, payload: dict) -> _Query:
        return _Query(self._db, "update", payload)

    def delete(self) -> _Query:
        return _Query(self._db, "delete")


def _up(repo: PreviewRepository, port: int = 3000, title: str = "Todo app") -> str:
    return repo.upsert(_PROJECT, _ENV, port, "/", title, _AGENT)


def test_upsert_same_port_replaces_row():
    db = _FakeDB()
    repo = PreviewRepository(db)
    first = _up(repo, 3000, "Todo app")
    second = _up(repo, 3000, "Todo app v2")
    assert first == second
    assert len(db.rows) == 1
    assert db.rows[0]["title"] == "Todo app v2"


def test_upsert_resets_created_at():
    db = _FakeDB()
    repo = PreviewRepository(db)
    _up(repo)
    db.rows[0]["created_at"] = "2000-01-01T00:00:00+00:00"
    _up(repo)
    assert db.rows[0]["created_at"] > "2001"


def test_list_for_env_newest_first_and_scoped():
    db = _FakeDB()
    repo = PreviewRepository(db)
    _up(repo, 3000)
    _up(repo, 3001)
    db.rows[0]["created_at"] = "2020-01-01T00:00:00+00:00"
    db.rows[1]["created_at"] = "2021-01-01T00:00:00+00:00"
    db.rows.append({**db.rows[0], "id": "x", "env_node_id": "other"})
    rows = repo.list_for_env(_ENV)
    assert [r.port for r in rows] == [3001, 3000]
    assert isinstance(rows[0], PreviewRow)


def test_newest_for_env_and_none_when_empty():
    db = _FakeDB()
    repo = PreviewRepository(db)
    assert repo.newest_for_env(_ENV) is None
    _up(repo, 3000)
    _up(repo, 3001)
    db.rows[0]["created_at"] = "2020-01-01T00:00:00+00:00"
    db.rows[1]["created_at"] = "2021-01-01T00:00:00+00:00"
    assert repo.newest_for_env(_ENV).port == 3001


def test_delete_removes_only_that_port():
    db = _FakeDB()
    repo = PreviewRepository(db)
    _up(repo, 3000)
    _up(repo, 3001)
    repo.delete(_ENV, 3000)
    assert [r["port"] for r in db.rows] == [3001]


def test_set_thumbnail():
    db = _FakeDB()
    repo = PreviewRepository(db)
    pid = _up(repo)
    repo.set_thumbnail(pid, "p/e/1.png")
    assert repo.list_for_env(_ENV)[0].thumbnail_path == "p/e/1.png"
