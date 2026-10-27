"""Notification + push routes over the real repo and a fake PostgREST client. No database."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import push_enabled, settings
from app.main import app
from app.repositories.notification_repo import NotificationRepository
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.deps import get_notification_repository

_UID = "u1"
_P1 = "11111111-1111-1111-1111-111111111111"
_P2 = "22222222-2222-2222-2222-222222222222"
_EP = "https://web.push.apple.com/abc"


class _Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, db: "_FakeDB", table: str, op: str, payload: Any = None) -> None:
        self._db, self._table, self._op, self._payload = db, table, op, payload
        self._eq: dict[str, Any] = {}
        self._null: list[str] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, *_a: Any) -> "_Query":
        return self

    def eq(self, k: str, v: Any) -> "_Query":
        self._eq[k] = v
        return self

    def is_(self, k: str, _v: str) -> "_Query":
        self._null.append(k)
        return self

    def order(self, col: str, desc: bool = False) -> "_Query":
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    def execute(self) -> _Result:
        rows = self._db.rows[self._table]
        hit = [
            r
            for r in rows
            if all(r.get(k) == v for k, v in self._eq.items())
            and all(r.get(k) is None for k in self._null)
        ]
        if self._op == "update":
            for r in hit:
                r.update(self._payload)
        elif self._op == "delete":
            self._db.rows[self._table] = [r for r in rows if r not in hit]
        elif self._order:
            hit.sort(key=lambda r: r[self._order[0]], reverse=self._order[1])
            hit = hit[: self._limit]
        return _Result(hit)


class _Rpc:
    def __init__(self, db: "_FakeDB", name: str, params: dict) -> None:
        db.rpcs.append((name, params))

    def execute(self) -> _Result:
        return _Result("sub-id")


class _FakeDB:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict]] = {"notifications": [], "push_subscriptions": []}
        self.rpcs: list[tuple[str, dict]] = []

    def table(self, name: str) -> Any:
        db = self

        class _T:
            def select(self, *a: Any) -> _Query:
                return _Query(db, name, "select")

            def update(self, payload: dict) -> _Query:
                return _Query(db, name, "update", payload)

            def delete(self) -> _Query:
                return _Query(db, name, "delete")

        return _T()

    def rpc(self, name: str, params: dict) -> _Rpc:
        return _Rpc(self, name, params)


def _note(i: int, project: str = _P1, read_at: str | None = None, owner: str = _UID) -> dict:
    return {
        "id": f"n{i}",
        "owner_id": owner,
        "project_id": project,
        "node_id": "node",
        "message_id": f"m{i}",
        "status": "complete",
        "node_name": "Agent",
        "project_name": "Proj",
        "nested": False,
        "excerpt": "hi",
        "read_at": read_at,
        "created_at": f"2026-01-01T00:00:0{i}+00:00",
    }


@pytest.fixture
def db() -> _FakeDB:
    return _FakeDB()


@pytest.fixture
def client(db: _FakeDB):
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user=UserResponse(id=_UID, email="u@example.com"),
        token="t",  # noqa: S106 - test fixture
    )
    app.dependency_overrides[get_notification_repository] = lambda: NotificationRepository(db, _UID)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_newest_first_and_limit_bounds(client, db):
    db.rows["notifications"] = [_note(1), _note(3), _note(2), _note(4, owner="other")]
    r = client.get("/notifications")
    assert r.status_code == 200
    assert [n["id"] for n in r.json()] == ["n3", "n2", "n1"]
    assert [n["id"] for n in client.get("/notifications?limit=2").json()] == ["n3", "n2"]
    assert client.get("/notifications?limit=0").status_code == 422
    assert client.get("/notifications?limit=201").status_code == 422


def test_mark_read_scoped_to_project(client, db):
    db.rows["notifications"] = [
        _note(1, _P1),
        _note(2, _P2),
        _note(3, _P1, read_at="2026-01-02T00:00:00+00:00"),
    ]
    r = client.post("/notifications/read", json={"project_id": _P1})
    assert r.json() == {"updated": 1}
    by_id = {n["id"]: n for n in db.rows["notifications"]}
    assert by_id["n1"]["read_at"] and by_id["n2"]["read_at"] is None
    assert by_id["n3"]["read_at"] == "2026-01-02T00:00:00+00:00"


def test_mark_read_all(client, db):
    db.rows["notifications"] = [_note(1, _P1), _note(2, _P2), _note(3, owner="other")]
    assert client.post("/notifications/read", json={}).json() == {"updated": 2}
    assert db.rows["notifications"][2]["read_at"] is None


def test_push_key_none_when_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "vapid_public_key", "")
    assert client.get("/push/key").json() == {"public_key": None}


def test_push_key_returned_when_enabled(client, monkeypatch):
    for k, v in {
        "supabase_service_key": "s",
        "vapid_private_key": "priv",
        "vapid_public_key": "pub",
        "vapid_subject": "mailto:a@b.c",
    }.items():
        monkeypatch.setattr(settings, k, v)
    assert push_enabled()
    assert client.get("/push/key").json() == {"public_key": "pub"}
    monkeypatch.setattr(settings, "supabase_service_key", "")
    assert not push_enabled()


def test_subscribe_calls_rpc_with_keys(client, db):
    r = client.post(
        "/push/subscriptions",
        json={"endpoint": _EP, "keys": {"p256dh": "P", "auth": "A"}},
        headers={"User-Agent": "u" * 400},
    )
    assert r.status_code == 204
    assert db.rpcs == [
        (
            "upsert_push_subscription",
            {"p_endpoint": _EP, "p_p256dh": "P", "p_auth": "A", "p_user_agent": "u" * 300},
        )
    ]


def test_subscribe_rejects_bad_endpoint(client):
    r = client.post(
        "/push/subscriptions",
        json={"endpoint": "nope", "keys": {"p256dh": "P", "auth": "A"}},
    )
    assert r.status_code == 422


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://169.254.169.254/latest",
        "https://169.254.169.254/latest",
        "https://localhost:8000/x",
        "http://web.push.apple.com/x",
        "https://push.example.com/x",
        "https://web.push.apple.com.evil.com/x",
        "https://evilweb.push.apple.com/x",
        "https://web.push.apple.com:8443/x",
        "https://u:p@web.push.apple.com/x",
        "https://evil.com/fcm.googleapis.com/x",
    ],
)
def test_subscribe_rejects_non_push_hosts(client, db, endpoint):
    body = {"endpoint": endpoint, "keys": {"p256dh": "P", "auth": "A"}}
    r = client.post("/push/subscriptions", json=body)
    assert r.status_code == 422
    assert db.rpcs == []


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://web.push.apple.com/x",
        "https://web.push.apple.com:443/x",
        "https://fcm.googleapis.com/fcm/send/x",
        "https://updates.push.services.mozilla.com/wpush/v2/x",
        "https://other.push.services.mozilla.com/x",
        "https://wns2-par02p.notify.windows.com/w/?token=x",
    ],
)
def test_subscribe_accepts_push_hosts(client, db, endpoint):
    body = {"endpoint": endpoint, "keys": {"p256dh": "P", "auth": "A"}}
    r = client.post("/push/subscriptions", json=body)
    assert r.status_code == 204
    assert len(db.rpcs) == 1


def test_presence_sets_visible_until_60s(client, db):
    db.rows["push_subscriptions"] = [
        {"endpoint": _EP, "owner_id": _UID, "visible_until": None},
        {"endpoint": _EP, "owner_id": "other", "visible_until": None},
    ]
    assert (
        client.patch("/push/subscriptions", json={"endpoint": _EP, "visible": True}).status_code
        == 204
    )
    mine, theirs = db.rows["push_subscriptions"]
    want = datetime.now(UTC) + timedelta(seconds=60)
    assert abs((datetime.fromisoformat(mine["visible_until"]) - want).total_seconds()) < 2
    assert mine["updated_at"]
    assert theirs["visible_until"] is None


def test_presence_false_clears(client, db):
    db.rows["push_subscriptions"] = [
        {"endpoint": _EP, "owner_id": _UID, "visible_until": "2099-01-01T00:00:00+00:00"}
    ]
    assert (
        client.patch("/push/subscriptions", json={"endpoint": _EP, "visible": False}).status_code
        == 204
    )
    assert db.rows["push_subscriptions"][0]["visible_until"] is None


def test_unsubscribe_deletes_own_only(client, db):
    db.rows["push_subscriptions"] = [
        {"endpoint": _EP, "owner_id": _UID},
        {"endpoint": _EP, "owner_id": "other"},
    ]
    assert (
        client.request("DELETE", "/push/subscriptions", json={"endpoint": _EP}).status_code == 204
    )
    assert [r["owner_id"] for r in db.rows["push_subscriptions"]] == ["other"]


def test_routes_require_auth():
    c = TestClient(app)
    ep = {"endpoint": _EP}
    assert c.get("/notifications").status_code == 401
    assert c.post("/notifications/read", json={}).status_code == 401
    assert (
        c.post("/push/subscriptions", json={**ep, "keys": {"p256dh": "P", "auth": "A"}}).status_code
        == 401
    )
    assert c.patch("/push/subscriptions", json={**ep, "visible": True}).status_code == 401
    assert c.request("DELETE", "/push/subscriptions", json=ep).status_code == 401
    assert c.get("/push/key").status_code == 200
