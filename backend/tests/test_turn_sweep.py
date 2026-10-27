"""Startup sweep: repair tool calls and nodes a dead process left mid-turn.

Running messages are left for the recovery loop to resume.
"""

from datetime import UTC, datetime, timedelta

from app.services.runs import sweep_stale


def _iso(age_s):
    return (datetime.now(UTC) - timedelta(seconds=age_s)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class _Query:
    """Evaluates the filters sweep_stale uses against in-memory rows."""

    def __init__(self, db, table, log):
        self.db, self.table, self.log = db, table, log
        self.payload = None
        self.filters = []
        self._negate = False

    @property
    def not_(self):
        self._negate = True
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def select(self, _cols):
        return self

    def eq(self, col, val):
        self.filters.append(("eq", col, val, lambda r: r.get(col) == val))
        return self

    def lt(self, col, val):
        self.filters.append(("lt", col, val, lambda r: r.get(col) is not None and r[col] < val))
        return self

    def in_(self, col, vals):
        neg, self._negate = self._negate, False
        self.filters.append(("in", col, vals, lambda r: (r.get(col) in vals) != neg))
        return self

    def execute(self):
        rows = [r for r in self.db[self.table] if all(f[3](r) for f in self.filters)]
        if self.payload is not None:
            for r in rows:
                r.update(self.payload)
        self.log.append(
            {"table": self.table, "payload": self.payload, "filters": [f[:3] for f in self.filters]}
        )

        class _Result:
            data = rows

        return _Result()


class _FakeClient:
    def __init__(self, db):
        self.db = {"messages": [], "tool_calls": [], "nodes": [], **db}
        self.calls = []

    def table(self, name):
        return _Query(self.db, name, self.calls)


def test_running_messages_are_left_for_recovery():
    client = _FakeClient(
        {
            "messages": [
                # Old turn, but beating: another backend's live run.
                {
                    "id": "live",
                    "conversation_id": "c1",
                    "status": "running",
                    "created_at": _iso(3600),
                    "heartbeat_at": _iso(5),
                },
                {
                    "id": "stale",
                    "conversation_id": "c2",
                    "status": "running",
                    "created_at": _iso(3600),
                    "heartbeat_at": _iso(600),
                },
                {
                    "id": "null",
                    "conversation_id": "c3",
                    "status": "running",
                    "created_at": _iso(3600),
                    "heartbeat_at": None,
                },
                {
                    "id": "young",
                    "conversation_id": "c4",
                    "status": "running",
                    "created_at": _iso(5),
                    "heartbeat_at": None,
                },
            ],
        }
    )

    counts = sweep_stale(client, min_age_s=60)

    # Stale or not, the recovery loop resumes them; the sweep never writes messages.
    assert all(m["status"] == "running" for m in client.db["messages"])
    assert "messages" not in counts
    assert not any(c["table"] == "messages" and c["payload"] for c in client.calls)


def test_tool_call_under_a_running_message_is_not_swept():
    client = _FakeClient(
        {
            "messages": [
                {
                    "id": "live",
                    "conversation_id": "c1",
                    "status": "running",
                    "created_at": _iso(3600),
                    "heartbeat_at": _iso(5),
                },
                # Stale heartbeat: waiting to be resumed, so its calls are kept.
                {
                    "id": "stale",
                    "conversation_id": "c2",
                    "status": "running",
                    "created_at": _iso(3600),
                    "heartbeat_at": _iso(600),
                },
            ],
            "tool_calls": [
                {
                    "id": "t-live",
                    "conversation_id": "c1",
                    "status": "running",
                    "created_at": _iso(1800),
                },
                {
                    "id": "t-stale",
                    "conversation_id": "c2",
                    "status": "running",
                    "created_at": _iso(1800),
                },
                {
                    "id": "t-orphan",
                    "conversation_id": "c9",
                    "status": "running",
                    "created_at": _iso(1800),
                },
            ],
        }
    )

    counts = sweep_stale(client, min_age_s=60)

    status = {t["id"]: t["status"] for t in client.db["tool_calls"]}
    assert status == {"t-live": "running", "t-stale": "running", "t-orphan": "error"}
    assert counts["tool_calls"] == 1


def test_nodes_reset_only_when_not_touched_recently():
    client = _FakeClient(
        {
            "nodes": [
                {"id": "beating", "kind": "agent", "status": "running", "updated_at": _iso(10)},
                {"id": "abandoned", "kind": "agent", "status": "running", "updated_at": _iso(600)},
            ]
        }
    )

    sweep_stale(client, min_age_s=60)

    assert {n["id"]: n["status"] for n in client.db["nodes"]} == {
        "beating": "running",
        "abandoned": "ready",
    }


def test_stale_age_is_at_least_three_heartbeats():
    client = _FakeClient(
        {
            "nodes": [
                {"id": "n", "kind": "agent", "status": "running", "updated_at": _iso(45)},
            ]
        }
    )
    # min_age_s below the floor: a node touched 45s ago is still live.
    sweep_stale(client, min_age_s=1)
    assert client.db["nodes"][0]["status"] == "running"


def test_node_of_a_running_conversation_is_not_reset():
    client = _FakeClient(
        {
            "messages": [
                {
                    "id": "m",
                    "conversation_id": "c",
                    "status": "running",
                    "created_at": _iso(3600),
                    "heartbeat_at": _iso(600),
                    "conversations": {"node_id": "waiting"},
                },
            ],
            "nodes": [
                {"id": "waiting", "kind": "agent", "status": "running", "updated_at": _iso(600)},
                {"id": "abandoned", "kind": "agent", "status": "running", "updated_at": _iso(600)},
            ],
        }
    )

    sweep_stale(client, min_age_s=60)

    assert {n["id"]: n["status"] for n in client.db["nodes"]} == {
        "waiting": "running",
        "abandoned": "ready",
    }
