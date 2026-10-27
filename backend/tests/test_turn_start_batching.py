"""Turn-start batching: batch node reads, concurrent history read, one resume check."""

from dataclasses import replace
from unittest.mock import MagicMock

import pytest

import app.workflows as workflows
from app.repositories.project_repo import _to_node
from app.repositories.tool_repo import ToolRepository
from app.services import runs
from tests.test_chat_routes_turns import (  # noqa: F401
    _CONVERSATION_ID,
    _NODE_ID,
    _PROJECT_ID,
    client_with_fakes,
)
from tests.test_turn_persistence import _Repo


@pytest.fixture(autouse=True)
def clean():
    runs._RUNS.clear()
    yield
    runs._RUNS.clear()


def _tool_row(i):
    return {
        "id": i,
        "project_id": "p",
        "name": i,
        "tool_type_id": "tt",
        "config": {},
        "status": "ready",
        "status_detail": None,
        "tool_types": {"slug": "web_fetch"},
    }


def test_get_tool_nodes_is_one_query_in_input_order_dropping_missing():
    client = MagicMock()
    chain = client.table.return_value
    for m in ("select", "eq", "in_"):
        getattr(chain, m).return_value = chain
    chain.execute.return_value = MagicMock(data=[_tool_row("b"), _tool_row("a")])

    got = ToolRepository(client, "u").get_tool_nodes(["a", "gone", "b"])

    assert [n.id for n in got] == ["a", "b"]
    assert chain.execute.call_count == 1
    chain.in_.assert_called_once_with("id", ["a", "gone", "b"])


def test_node_carries_embedded_conversation_id_object_or_list():
    base = {"id": "n", "project_id": "p", "name": "A", "agent_types": None}
    assert _to_node({**base, "conversations": {"id": "c1"}}).conversation_id == "c1"
    assert _to_node({**base, "conversations": [{"id": "c2"}]}).conversation_id == "c2"
    assert _to_node({**base, "conversations": []}).conversation_id is None
    assert _to_node(base).conversation_id is None


async def _history_for(monkeypatch, repo):
    seen = {}

    async def fake_stream(system_prompt, model, prompt, history, **kw):
        seen["history"] = history
        yield "done", {"turn": workflows.AgentTurn(output="ok", model=model)}

    monkeypatch.setattr(workflows, "_stream_agent", fake_stream)
    run = await workflows.start_turn(repo, "c", "s", "m", "hi", node_id="n", project_id="p")
    await run.task
    return [m.content for m in seen["history"]]


class _RacingRepo(_Repo):
    """list_messages lands after the user insert, so it sees the new row."""

    def __init__(self, replay=False):
        super().__init__()
        self.old = [
            self._msg("user", "old-q", "complete"),
            self._msg("assistant", "old-a", "complete"),
        ]
        self.replay = replay
        if replay:
            # The retried prompt's row already exists, with a reply after it.
            self.sent = self._msg("user", "hi", "complete")
            self.old += [self.sent, self._msg("assistant", "hi-a", "complete")]

    def list_messages(self, conversation_id, limit=50):
        # Deterministic race: the new user row (next seq) is always visible.
        new = (
            [] if self.replay else [replace(self.old[0], id="new", seq=self._seq + 1, content="hi")]
        )
        return [*self.old, *new][-limit:]

    def add_message(self, conversation_id, role, content, **kw):
        if self.replay and role == "user":
            return replace(self.sent, replayed=True)
        return super().add_message(conversation_id, role, content, **kw)


@pytest.mark.anyio
async def test_start_turn_history_excludes_the_new_user_row(monkeypatch):
    assert await _history_for(monkeypatch, _RacingRepo()) == ["old-q", "old-a"]


@pytest.mark.anyio
async def test_start_turn_replayed_token_stops_history_before_the_replayed_row(monkeypatch):
    assert await _history_for(monkeypatch, _RacingRepo(replay=True)) == ["old-q", "old-a"]


def test_resume_validates_all_approvals_in_one_query(client_with_fakes):  # noqa: F811
    client, chat_repo, tool_repo = client_with_fakes
    chat_repo.get_or_create_conversation(_NODE_ID, _PROJECT_ID)
    for t in ("call_1", "call_2"):
        tool_repo.calls[t] = {"tool_call_id": t, "status": "pending_approval"}
    tool_repo.set_pending_run(_CONVERSATION_ID, "[]")
    batches = []
    tool_repo.get_calls_by_tool_call_ids = lambda c, ids: batches.append(ids) or {
        t: tool_repo.calls[t] for t in ids if t in tool_repo.calls
    }
    tool_repo.get_call_by_tool_call_id = MagicMock(side_effect=AssertionError("per-call read"))

    response = client.post(
        "/chat/resume",
        json={"node_id": _NODE_ID, "approvals": {"call_1": True, "call_2": False}},
    )

    # No awaiting row in the fake: validation passed, then 409.
    assert response.status_code == 409
    assert batches == [["call_1", "call_2"]]
