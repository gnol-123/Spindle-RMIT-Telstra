"""Repository additions for progressive turns, against a fake client."""

from app.repositories.project_repo import ProjectRepository, _to_message
from app.repositories.tool_repo import ToolRepository


class _Query:
    def __init__(self, log, data):
        self.log, self.data = log, data
        self.calls = []

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append((name, args))
            return self

        return method

    def execute(self):
        self.log.append(self.calls)
        return type("R", (), {"data": self.data})()


class _Client:
    def __init__(self, data=None):
        self.log, self.data = [], data or []

    def table(self, name):
        q = _Query(self.log, self.data)
        q.calls.append(("table", (name,)))
        return q


def test_to_message_reads_tool_calls():
    m = _to_message(
        {
            "id": "m",
            "role": "assistant",
            "content": "",
            "seq": 2,
            "status": "running",
            "created_at": "t",
            "tool_calls": [{"type": "call"}],
        }
    )
    assert m.tool_calls == [{"type": "call"}]
    assert (
        _to_message(
            {
                "id": "m",
                "role": "user",
                "content": "x",
                "seq": 1,
                "status": "complete",
                "created_at": "t",
            }
        ).tool_calls
        == []
    )


def test_update_message_sends_only_given_fields():
    row = {
        "id": "m",
        "role": "assistant",
        "content": "hi",
        "seq": 2,
        "status": "running",
        "created_at": "t",
        "tool_calls": [],
    }
    client = _Client([row])
    repo = ProjectRepository(client, "u")
    out = repo.update_message("m", content="hi", tool_calls=[])
    calls = client.log[0]
    update = next(a for n, a in calls if n == "update")[0]
    assert update == {"content": "hi", "tool_calls": []}
    assert ("eq", ("owner_id", "u")) in calls
    assert out.content == "hi"


def test_set_agent_status_filters_kind():
    client = _Client([{"id": "n"}])
    ProjectRepository(client, "u").set_agent_status("n", "running")
    calls = client.log[0]
    assert next(a for n, a in calls if n == "update")[0] == {"status": "running"}
    assert ("eq", ("kind", "agent")) in calls


def test_latest_message_with_status_orders_desc():
    client = _Client([])
    assert (
        ProjectRepository(client, "u").latest_message_with_status("c", "awaiting_approval") is None
    )
    calls = client.log[0]
    assert ("eq", ("status", "awaiting_approval")) in calls
    assert ("order", ("seq",)) in calls or any(n == "order" for n, _ in calls)


def test_cancel_calls_targets_statuses():
    client = _Client([])
    ToolRepository(client, "u").cancel_calls("c", ["running", "pending_approval"])
    calls = client.log[0]
    assert next(a for n, a in calls if n == "update")[0] == {"status": "cancelled"}
    assert ("in_", ("status", ["running", "pending_approval"])) in calls
