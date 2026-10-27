"""Web Push sender: payloads, batch send, kick, and the _finalise hook."""

import asyncio
import threading
import time

import pytest
from pywebpush import WebPushException

import app.workflows as workflows
from app.repositories.project_repo import Message
from app.services import push, runs


def row(**kw):
    base = {
        "notification_id": "n1",
        "message_id": "m1",
        "subscription_id": "s1",
        "endpoint": "https://push.example/abc",
        "p256dh": "pk",
        "auth": "au",
        "status": "complete",
        "node_name": "Agent",
        "project_name": "Proj",
        "project_id": "p1",
        "nested": False,
        "excerpt": None,
    }
    return {**base, **kw}


class _Resp:
    def __init__(self, status_code):
        self.status_code = status_code
        self.text = ""


class _Query:
    def __init__(self, client, table):
        self.client = client
        self.table = table

    def delete(self):
        return self

    def eq(self, col, val):
        self.client.deleted.append((self.table, col, val))
        return self

    def execute(self):
        return self


class _Rpc:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _Client:
    def __init__(self, rows):
        self.rows = rows
        self.rpcs = []
        self.deleted = []

    def rpc(self, name, params):
        self.rpcs.append((name, params))
        return _Rpc(self.rows)

    def table(self, name):
        return _Query(self, name)


@pytest.fixture
def vapid(monkeypatch):
    monkeypatch.setattr(push.settings, "vapid_private_key", "priv")
    monkeypatch.setattr(push.settings, "vapid_subject", "mailto:a@b.c")


def test_payload_complete():
    p = push.payload_for(row(status="complete"))
    assert p["body"] == "Proj · finished"
    assert p["title"] == "Agent"


def test_payload_failed_with_excerpt():
    p = push.payload_for(row(status="failed", excerpt="boom"))
    assert p["body"] == "Proj · failed\nboom"


def test_payload_approval_and_nested():
    p = push.payload_for(row(status="awaiting_approval", nested=True))
    assert p["body"].startswith("Proj · needs your approval")
    assert p["title"] == "Agent · via orchestrator"


def test_payload_url_and_tag():
    p = push.payload_for(row(project_id="abc", message_id="mid"))
    assert p["url"] == "/?project=abc"
    # Per turn, so "finished" replaces "needs your approval".
    assert p["tag"] == "mid"


@pytest.mark.parametrize("code", [404, 410])
async def test_send_batch_dead_deletes_subscription_and_continues(monkeypatch, vapid, code):
    calls = []

    def fake_webpush(**kw):
        calls.append(kw)
        if kw["subscription_info"]["endpoint"] == "e2":
            raise WebPushException("gone", response=_Resp(code))

    monkeypatch.setattr(push, "webpush", fake_webpush)
    client = _Client(
        [
            row(subscription_id="s1", endpoint="e1"),
            row(subscription_id="s2", endpoint="e2"),
            row(subscription_id="s3", endpoint="e3"),
        ]
    )
    assert await push.send_batch(client) == 2
    assert client.rpcs == [("claim_push_batch", {"p_limit": 50})]
    assert client.deleted == [("push_subscriptions", "id", "s2")]
    assert len(calls) == 3
    first = calls[0]
    assert first["subscription_info"] == {"endpoint": "e1", "keys": {"p256dh": "pk", "auth": "au"}}
    assert first["vapid_private_key"] == "priv"
    assert first["ttl"] == 3600
    assert first["timeout"] == 10
    # Fresh dict per call: pywebpush writes aud/exp into it.
    assert calls[0]["vapid_claims"] is not calls[1]["vapid_claims"]
    assert calls[1]["vapid_claims"]["sub"] == "mailto:a@b.c"


async def test_send_batch_other_error_keeps_going(monkeypatch, vapid):
    def fake_webpush(**kw):
        endpoint = kw["subscription_info"]["endpoint"]
        if endpoint == "e1":
            raise WebPushException("server", response=_Resp(500))
        if endpoint == "e2":
            raise RuntimeError("network")

    monkeypatch.setattr(push, "webpush", fake_webpush)
    client = _Client(
        [row(endpoint="e1"), row(endpoint="e2"), row(endpoint="e3", subscription_id="s3")]
    )
    assert await push.send_batch(client) == 1
    assert client.deleted == []


async def test_send_batch_caps_concurrency(monkeypatch, vapid):
    lock = threading.Lock()
    now = peak = 0

    def slow_webpush(**kw):
        nonlocal now, peak
        with lock:
            now += 1
            peak = max(peak, now)
        time.sleep(0.02)
        with lock:
            now -= 1

    monkeypatch.setattr(push, "webpush", slow_webpush)
    rows = [row(subscription_id=f"s{i}", endpoint=f"e{i}") for i in range(30)]
    assert await push.send_batch(_Client(rows)) == 30
    assert 1 < peak <= 8


async def test_send_batch_empty(monkeypatch, vapid):
    monkeypatch.setattr(push, "webpush", lambda **kw: pytest.fail("no rows, no send"))
    assert await push.send_batch(_Client([])) == 0


def test_kick_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(push, "push_enabled", lambda: False)
    monkeypatch.setattr(push, "get_service_client", lambda: pytest.fail("no client when off"))
    push.kick()


async def test_kick_schedules_tracked_send(monkeypatch):
    sent = []

    async def fake_send(client):
        sent.append(client)
        return 0

    tracked = []
    monkeypatch.setattr(push, "push_enabled", lambda: True)
    monkeypatch.setattr(push, "get_service_client", lambda: "svc")
    monkeypatch.setattr(push, "send_batch", fake_send)
    monkeypatch.setattr(runs, "track_finaliser", tracked.append)
    push.kick()
    assert len(tracked) == 1
    await tracked[0]
    assert sent == ["svc"]


def test_kick_never_raises(monkeypatch):
    monkeypatch.setattr(push, "push_enabled", lambda: True)

    def boom():
        raise RuntimeError("no key")

    monkeypatch.setattr(push, "get_service_client", boom)
    push.kick()


class _Repo:
    def __init__(self):
        self.base = Message(
            id="m1", role="assistant", content="", seq=1, status="running", created_at="t"
        )

    def update_message(self, message_id, **fields):
        return Message(
            id=message_id,
            role="assistant",
            content=fields.get("content", ""),
            seq=1,
            status=fields["status"],
            created_at="t",
        )

    def clear_checkpoint(self, message_id):
        pass

    def set_agent_status(self, node_id, status):
        pass


async def test_finalise_kicks_once(monkeypatch):
    kicks = []
    monkeypatch.setattr(push, "kick", lambda: kicks.append(1))
    repo = _Repo()
    run = runs.RunningTurn(conversation_id="c1", node_id="n1", project_id="p1", model="m")
    run.message = repo.base
    message = await workflows._finalise(repo, None, run, status="complete")
    assert message.status == "complete"
    assert kicks == [1]


async def test_push_loop_survives_errors(monkeypatch):
    polls = []

    async def flaky(client):
        polls.append(1)
        if len(polls) == 1:
            raise RuntimeError("db down")
        if len(polls) == 3:
            raise asyncio.CancelledError
        return 0

    monkeypatch.setattr(push, "get_service_client", lambda: "svc")
    monkeypatch.setattr(push, "send_batch", flaky)
    monkeypatch.setattr(push, "POLL_S", 0)
    with pytest.raises(asyncio.CancelledError):
        await push.push_loop()
    assert len(polls) == 3
