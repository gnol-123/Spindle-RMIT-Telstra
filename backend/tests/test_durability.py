"""Durable turns: checkpoints, recovery loop claims, shutdown handoff, run_agent rejoin."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.toolsets import FunctionToolset

import app.tools.canvas as canvas
import app.workflows as workflows
from app.config import settings
from app.repositories.project_repo import Message, ProjectRepository, _to_message
from app.routers.deps import TurnRepositories
from app.services import recovery, runs
from app.workflows import TurnSetup
from tests.test_canvas_tools import ORCH, _node


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    runs._RUNS.clear()
    monkeypatch.setattr(runs, "_handing_off", False)
    monkeypatch.setattr(settings, "supabase_service_key", "k")
    yield
    runs._RUNS.clear()


def _iso(age_s=0):
    return (datetime.now(UTC) - timedelta(seconds=age_s)).isoformat()


# -- in-memory store ----------------------------------------------------------


class _Store:
    """messages rows as dicts, plus checkpoints, behind both repo fakes."""

    def __init__(self):
        self.rows: list[dict] = []
        self.checkpoints: dict[str, dict] = {}
        self.saved: list[list[ModelMessage]] = []
        self.clears: list[bool] = []
        self.node_status: list[tuple[str, str]] = []
        self.pending: dict[str, str] = {}
        self.calls: dict[str, dict] = {}

    def add(self, conversation_id, role, content, **kw):
        row = {
            "id": f"m{len(self.rows) + 1}",
            "conversation_id": conversation_id,
            "owner_id": "u",
            "role": role,
            "content": content,
            "seq": len(self.rows) + 1,
            "status": kw.get("status", "complete"),
            "created_at": _iso(),
            "tool_calls": kw.get("tool_calls", []),
            "sender_node_id": None,
            "client_token": kw.get("client_token"),
            "heartbeat_at": kw.get("heartbeat_at"),
            "resume_count": kw.get("resume_count", 0),
            "parent_message_id": kw.get("parent_message_id"),
            "error": None,
        }
        self.rows.append(row)
        return row

    def row(self, message_id):
        return next(r for r in self.rows if r["id"] == message_id)


class _Repo:
    def __init__(self, store: _Store, nodes=()):
        self.s = store
        self.nodes = {n.id: n for n in nodes}

    def list_messages(self, conversation_id, limit=50, *, before_seq=None):
        rows = [
            r
            for r in self.s.rows
            if r["conversation_id"] == conversation_id
            and (before_seq is None or r["seq"] < before_seq)
        ]
        return [_to_message(r) for r in rows[-limit:]]

    def add_message(self, conversation_id, role, content, **kw):
        token = kw.get("client_token")
        if token:
            hit = self.find_by_client_token(conversation_id, token)
            if hit is not None:
                return Message(**{**hit.__dict__, "replayed": True})
        return _to_message(self.s.add(conversation_id, role, content, **kw))

    def find_by_client_token(self, conversation_id, token):
        hit = next(
            (
                r
                for r in self.s.rows
                if r["conversation_id"] == conversation_id and r["client_token"] == token
            ),
            None,
        )
        return _to_message(hit) if hit else None

    def update_message(self, message_id, **fields):
        row = self.s.row(message_id)
        row.update(fields)
        return _to_message(row)

    def claim_message(self, message_id, seen_heartbeat_at, **fields):
        row = self.s.row(message_id)
        if row["status"] != "running" or row["heartbeat_at"] != seen_heartbeat_at:
            return None
        return self.update_message(message_id, **fields)

    def request_cancel(self, message_id):
        row = self.s.row(message_id)
        if row["status"] != "running":
            return None
        row["cancel_requested"] = True
        return _to_message(row)

    def latest_reply_to(self, conversation_id, user_seq):
        reply = None
        for r in self.s.rows:
            if r["conversation_id"] != conversation_id or r["seq"] <= user_seq:
                continue
            if r["role"] == "user":
                break
            reply = r
        return _to_message(reply) if reply else None

    def save_checkpoint(
        self, message_id, history, content_len, events_len, *, clear_approvals=False
    ):
        self.s.saved.append(ModelMessagesTypeAdapter.validate_python(history))
        self.s.clears.append(clear_approvals)
        old = self.s.checkpoints.get(message_id, {})
        self.s.checkpoints[message_id] = {
            "history": history,
            "content_len": content_len,
            "events_len": events_len,
            "approvals": None if clear_approvals else old.get("approvals"),
        }

    def set_approvals(self, message_id, approvals):
        if message_id in self.s.checkpoints:
            self.s.checkpoints[message_id]["approvals"] = approvals

    def get_checkpoint(self, message_id):
        return self.s.checkpoints.get(message_id)

    def clear_checkpoint(self, message_id):
        self.s.checkpoints.pop(message_id, None)

    def set_agent_status(self, node_id, status):
        self.s.node_status.append((node_id, status))

    def get_agent_node(self, node_id):
        return self.nodes.get(node_id)

    def latest_message_with_status(self, conversation_id, status):
        rows = [
            r
            for r in self.s.rows
            if r["conversation_id"] == conversation_id and r["status"] == status
        ]
        return _to_message(rows[-1]) if rows else None

    def list_outbound_context_edges(self, node_id):
        return []

    def get_or_create_conversation(self, node_id, project_id):
        return f"conv-{node_id}"

    # tool repo
    def get_pending_run(self, conversation_id):
        p = self.s.pending.get(conversation_id)
        return (p, datetime.now(UTC)) if p else None

    def set_pending_run(self, conversation_id, payload):
        if payload is None:
            self.s.pending.pop(conversation_id, None)
        else:
            self.s.pending[conversation_id] = payload

    def get_calls_by_tool_call_ids(self, conversation_id, ids):
        return {i: self.s.calls[i] for i in ids if i in self.s.calls}

    def cancel_calls(self, conversation_id, from_statuses, status="cancelled"):
        for c in self.s.calls.values():
            if c["status"] in from_statuses:
                c["status"] = status


def _repos(store, nodes=()):
    repo = _Repo(store, nodes)
    return TurnRepositories(project=repo, tool=repo, env=repo, user_id="u")


# -- scripted model: call add once, then answer ---------------------------------

ADDS: list[int] = []


def add(x: int) -> str:
    ADDS.append(x)
    return f"added {x}"


def _toolset():
    return FunctionToolset([add])


async def _stream(messages: list[ModelMessage], info: AgentInfo):
    returned = any(isinstance(p, ToolReturnPart) for m in messages for p in m.parts)
    if not returned:
        yield "thinking "
        yield {0: DeltaToolCall(name="add", json_args='{"x": 1}', tool_call_id="c1")}
        return
    yield "done"


def _use_model(monkeypatch, stream=_stream):
    def fake(system_prompt, model):
        return Agent(
            FunctionModel(lambda m, i: ModelResponse(parts=[]), stream_function=stream),
            name="t",
            output_type=[str, DeferredToolRequests],
        )

    monkeypatch.setattr(workflows, "get_agent_for", fake)


@pytest.fixture(autouse=True)
def _reset_adds():
    ADDS.clear()


# -- checkpoints ----------------------------------------------------------------


@pytest.mark.anyio
async def test_checkpoint_per_node_holds_response_and_tool_returns(monkeypatch):
    _use_model(monkeypatch)
    store = _Store()
    repo = _Repo(store)

    run = await workflows.start_turn(
        repo, "c", "s", "m", "hi", node_id="n", project_id="p", toolsets=[_toolset()]
    )
    await run.task

    tails = [h[-1] for h in store.saved]
    # Prompt request, the tool-call response, then the request carrying its return.
    assert isinstance(tails[0], ModelRequest) and isinstance(tails[0].parts[0], UserPromptPart)
    assert isinstance(tails[1], ModelResponse) and tails[1].tool_calls[0].tool_call_id == "c1"
    assert isinstance(tails[2], ModelRequest) and isinstance(tails[2].parts[0], ToolReturnPart)
    # The final answer is not checkpointed, and finalise drops the checkpoint.
    assert len(store.saved) == 3
    # Approvals survive only the first node: after it the run is past their calls.
    assert store.clears == [False, True, True]
    assert store.checkpoints == {}
    assert store.row(run.message.id)["status"] == "complete"


@pytest.mark.anyio
async def test_no_checkpoint_without_service_key(monkeypatch):
    monkeypatch.setattr(settings, "supabase_service_key", "")
    _use_model(monkeypatch)
    store = _Store()
    run = await workflows.start_turn(
        _Repo(store), "c", "s", "m", "hi", node_id="n", project_id="p", toolsets=[_toolset()]
    )
    await run.task
    assert store.saved == []


# -- recovery loop ----------------------------------------------------------------


class _Client:
    """Just the two reads recover_once makes, evaluated against the store."""

    def __init__(self, store):
        self.s = store

    def table(self, name):
        return _Query(self.s)


class _Query:
    def __init__(self, store):
        self.s, self.filters, self.n, self.negate = store, [], None, False
        self.nulls_first = None

    def select(self, _cols):
        return self

    @property
    def not_(self):
        self.negate = True
        return self

    def _filter(self, f):
        neg, self.negate = self.negate, False
        self.filters.append((lambda r: not f(r)) if neg else f)
        return self

    def eq(self, col, val):
        return self._filter(lambda r: r.get(col) == val)

    def in_(self, col, vals):
        return self._filter(lambda r: r.get(col) in vals)

    def or_(self, _expr):
        return self._filter(lambda r: runs.is_stale(_to_message(r)))

    def order(self, col, nullsfirst=None):
        if nullsfirst:
            self.nulls_first = col
        return self

    def limit(self, n):
        self.n = n
        return self

    def execute(self):
        rows = [
            {**r, "conversations": {"node_id": r["conversation_id"].removeprefix("conv-")}}
            for r in self.s.rows
            if all(f(r) for f in self.filters)
        ]
        if self.nulls_first:
            rows.sort(key=lambda r: r[self.nulls_first] is not None)
        rows = rows[: self.n] if self.n else rows

        class _R:
            data = rows

        return _R()


def _stale_turn(store, *, conv="conv-a", prompt="hi", **kw):
    store.add(conv, "user", prompt)
    return store.add(
        conv, "assistant", "thinking stale tail", status="running", heartbeat_at=_iso(600), **kw
    )


def _patch_recovery(monkeypatch, store, nodes):
    repos = _repos(store, nodes)
    monkeypatch.setattr(recovery, "service_turn_repositories", lambda uid: repos)

    def setup(turn_repos, node, conversation_id):
        async def build():
            return TurnSetup(None, [_toolset()], None)

        return build

    monkeypatch.setattr(recovery, "turn_setup", setup)
    return repos


async def _settle():
    for r in list(runs._RUNS.values()):
        await r.task


async def _finalisers():
    loop = asyncio.get_running_loop()
    await asyncio.gather(*(t for t in runs._FINALISERS if t.get_loop() is loop))


@pytest.mark.anyio
async def test_resume_from_checkpoint_reruns_the_interrupted_call(monkeypatch):
    _use_model(monkeypatch)
    store = _Store()
    row = _stale_turn(store)
    history = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(parts=[ToolCallPart(tool_name="add", args={"x": 1}, tool_call_id="c1")]),
    ]
    store.checkpoints[row["id"]] = {
        "history": ModelMessagesTypeAdapter.dump_python(history, mode="json"),
        "content_len": len("thinking "),
        "events_len": 0,
    }
    _patch_recovery(monkeypatch, store, [_node("a")])

    assert await recovery.recover_once(_Client(store)) == 1
    await _settle()

    assert ADDS == [1]
    final = store.row(row["id"])
    assert final["status"] == "complete"
    assert final["resume_count"] == 1
    # Trimmed to the checkpoint, then the resumed run's own text.
    assert final["content"] == "thinking done"
    assert [e["type"] for e in final["tool_calls"]] == ["call", "result"]


@pytest.mark.anyio
async def test_resume_without_checkpoint_restarts_from_the_prompt(monkeypatch):
    seen = []

    async def stream(messages, info):
        seen.append([p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart)])
        yield "fresh"

    _use_model(monkeypatch, stream)
    store = _Store()
    store.add("conv-a", "user", "earlier")
    store.add("conv-a", "assistant", "earlier reply")
    row = _stale_turn(store, prompt="the prompt")
    _patch_recovery(monkeypatch, store, [_node("a")])

    assert await recovery.recover_once(_Client(store)) == 1
    await _settle()

    assert seen[0] == ["earlier", "the prompt"]
    assert store.row(row["id"])["content"] == "fresh"
    assert store.row(row["id"])["status"] == "complete"


def test_claim_is_compare_and_set_on_the_heartbeat_read():
    """Two instances read the same stale row: one update lands, the other gets nothing."""

    class _Db:
        def __init__(self):
            self.row = {
                "id": "m",
                "owner_id": "u",
                "status": "running",
                "heartbeat_at": "2026-01-01T00:00:00+00:00",
                "resume_count": 0,
                "role": "assistant",
                "content": "",
                "seq": 2,
                "created_at": "2026-01-01T00:00:00+00:00",
            }

        def table(self, _name):
            db = self

            class Q:
                def __init__(self):
                    self.ok = True

                def update(self, payload):
                    self.payload = payload
                    return self

                def eq(self, col, val):
                    self.ok = self.ok and db.row.get(col) == val
                    return self

                def is_(self, col, _null):
                    self.ok = self.ok and db.row.get(col) is None
                    return self

                def execute(self):
                    class R:
                        data = []

                    if self.ok:
                        db.row.update(self.payload)
                        R.data = [dict(db.row)]
                    return R()

            return Q()

    repo = ProjectRepository(_Db(), "u")
    seen = "2026-01-01T00:00:00+00:00"
    first = repo.claim_message("m", seen, heartbeat_at=_iso(), resume_count=1)
    second = repo.claim_message("m", seen, heartbeat_at=_iso(), resume_count=1)
    assert first is not None and first.resume_count == 1
    assert second is None


@pytest.mark.anyio
async def test_loop_claim_is_exclusive(monkeypatch):
    _use_model(monkeypatch)
    store = _Store()
    _stale_turn(store)
    _patch_recovery(monkeypatch, store, [_node("a")])

    # Two pollers on the same read: only one start_turn.
    results = await asyncio.gather(
        recovery.recover_once(_Client(store)), recovery.recover_once(_Client(store))
    )
    await _settle()
    assert sorted(results) == [0, 1]


@pytest.mark.anyio
async def test_resume_cap_fails_the_row(monkeypatch):
    store = _Store()
    row = _stale_turn(store, resume_count=recovery.MAX_RESUMES)
    _patch_recovery(monkeypatch, store, [_node("a")])

    assert await recovery.recover_once(_Client(store)) == 0
    final = store.row(row["id"])
    assert (final["status"], final["error"]) == ("failed", "could not resume")
    assert ("a", "ready") in store.node_status


@pytest.mark.anyio
async def test_nested_orphan_with_finished_parent_is_failed(monkeypatch):
    store = _Store()
    parent = store.add("conv-orch", "assistant", "done", status="complete")
    row = _stale_turn(store, parent_message_id=parent["id"])
    _patch_recovery(monkeypatch, store, [_node("a")])

    await recovery.recover_once(_Client(store))
    final = store.row(row["id"])
    assert (final["status"], final["error"]) == ("failed", "parent run ended")


@pytest.mark.anyio
async def test_nested_orphan_with_cancelled_parent_is_cancelled(monkeypatch):
    store = _Store()
    parent = store.add("conv-orch", "assistant", "", status="cancelled")
    row = _stale_turn(store, parent_message_id=parent["id"])
    _patch_recovery(monkeypatch, store, [_node("a")])

    await recovery.recover_once(_Client(store))
    final = store.row(row["id"])
    assert (final["status"], final["error"]) == ("cancelled", None)


@pytest.mark.anyio
async def test_nested_row_with_running_parent_is_left_for_the_parent(monkeypatch):
    store = _Store()
    parent = store.add("conv-orch", "assistant", "", status="running", heartbeat_at=_iso())
    row = _stale_turn(store, parent_message_id=parent["id"])
    _patch_recovery(monkeypatch, store, [_node("a")])

    assert await recovery.recover_once(_Client(store)) == 0
    assert store.row(row["id"])["status"] == "running"
    assert store.row(row["id"])["resume_count"] == 0


@pytest.mark.anyio
async def test_died_inside_an_approved_resume_replays_the_approval(monkeypatch):
    from pydantic_ai.toolsets import ApprovalRequiredToolset

    _use_model(monkeypatch)
    store = _Store()
    row = _stale_turn(store)
    history = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(parts=[ToolCallPart(tool_name="add", args={"x": 1}, tool_call_id="c1")]),
    ]
    dumped = ModelMessagesTypeAdapter.dump_python(history, mode="json")
    store.checkpoints[row["id"]] = {
        "history": dumped,
        "content_len": 0,
        "events_len": 0,
        "approvals": {"c1": True},
    }
    store.pending["conv-a"] = ModelMessagesTypeAdapter.dump_json(history).decode()
    store.calls["c1"] = {"tool_call_id": "c1", "status": "running"}
    _patch_recovery(monkeypatch, store, [_node("a")])

    def setup(turn_repos, node, conversation_id):
        async def build():
            return TurnSetup(None, [ApprovalRequiredToolset(_toolset())], None)

        return build

    monkeypatch.setattr(recovery, "turn_setup", setup)

    assert await recovery.recover_once(_Client(store)) == 1
    await _settle()
    await _finalisers()

    # Ran without asking again, then the parked run was dropped.
    assert ADDS == [1]
    assert store.row(row["id"])["status"] == "complete"
    assert "conv-a" not in store.pending


@pytest.mark.anyio
async def test_gated_call_without_stored_approvals_asks_again(monkeypatch):
    """Parked and pending_approval, but nobody approved it: a crash mid-park, say."""
    from pydantic_ai.toolsets import ApprovalRequiredToolset

    _use_model(monkeypatch)
    store = _Store()
    row = _stale_turn(store)
    history = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(parts=[ToolCallPart(tool_name="add", args={"x": 1}, tool_call_id="c1")]),
    ]
    dumped = ModelMessagesTypeAdapter.dump_python(history, mode="json")
    store.checkpoints[row["id"]] = {"history": dumped, "content_len": 0, "events_len": 0}
    store.pending["conv-a"] = ModelMessagesTypeAdapter.dump_json(history).decode()
    store.calls["c1"] = {"tool_call_id": "c1", "status": "pending_approval"}
    _patch_recovery(monkeypatch, store, [_node("a")])

    def setup(turn_repos, node, conversation_id):
        async def build():
            return TurnSetup(None, [ApprovalRequiredToolset(_toolset())], None)

        return build

    monkeypatch.setattr(recovery, "turn_setup", setup)

    await recovery.recover_once(_Client(store))
    await _settle()

    assert ADDS == []
    assert store.row(row["id"])["status"] == "awaiting_approval"


def _call(name, tid, **args):
    return ToolCallPart(tool_name=name, args=args, tool_call_id=tid)


def test_approvals_skip_answered_and_need_every_open_call():
    prompt = ModelRequest(parts=[UserPromptPart(content="hi")])
    mixed = ModelResponse(parts=[_call("auto", "a1"), _call("add", "g1", x=1)])
    answered = ModelRequest(
        parts=[ToolReturnPart(tool_name="auto", content="ok", tool_call_id="a1")]
    )
    history = [prompt, mixed, answered]

    got = recovery._approvals(history, {"g1": True, "a1": True})
    assert got.approvals == {"g1": True}
    assert recovery._approvals(history, None) is None
    # Something open with no stored decision: ask again, not run.
    two = ModelResponse(parts=[_call("add", "g1", x=1), _call("add", "g2", x=2)])
    assert recovery._approvals([prompt, two], {"g1": True}) is None
    # Everything answered: nothing to replay.
    assert recovery._approvals(history, {"a1": True}) is None


@pytest.mark.anyio
async def test_mixed_pause_replays_only_the_gated_approval(monkeypatch):
    from pydantic_ai.toolsets import ApprovalRequiredToolset

    autos = []

    def auto() -> str:
        autos.append(1)
        return "ok"

    _use_model(monkeypatch)
    store = _Store()
    row = _stale_turn(store)
    history = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(parts=[_call("auto", "a1"), _call("add", "g1", x=1)]),
        ModelRequest(parts=[ToolReturnPart(tool_name="auto", content="ok", tool_call_id="a1")]),
    ]
    store.checkpoints[row["id"]] = {
        "history": ModelMessagesTypeAdapter.dump_python(history, mode="json"),
        "content_len": 0,
        "events_len": 0,
        "approvals": {"g1": True},
    }
    _patch_recovery(monkeypatch, store, [_node("a")])

    def setup(turn_repos, node, conversation_id):
        async def build():
            gated = ApprovalRequiredToolset(_toolset())
            return TurnSetup(None, [FunctionToolset([auto]), gated], None)

        return build

    monkeypatch.setattr(recovery, "turn_setup", setup)

    assert await recovery.recover_once(_Client(store)) == 1
    await _settle()

    assert (ADDS, autos) == ([1], [])
    assert store.row(row["id"])["status"] == "complete"


@pytest.mark.anyio
async def test_handoff_claim_does_not_count_toward_the_cap(monkeypatch):
    _use_model(monkeypatch)
    store = _Store()
    row = _stale_turn(store, resume_count=recovery.MAX_RESUMES - 1)
    row["heartbeat_at"] = runs._EPOCH
    _patch_recovery(monkeypatch, store, [_node("a")])

    assert await recovery.recover_once(_Client(store)) == 1
    await _settle()
    assert store.row(row["id"])["resume_count"] == recovery.MAX_RESUMES - 1

    # A crash does count.
    crashed = _stale_turn(store, conv="conv-b")
    assert recovery.claim(_Repo(store), _to_message(crashed)).resume_count == 1


@pytest.mark.anyio
async def test_nested_row_with_awaiting_parent_is_left_for_the_parent(monkeypatch):
    store = _Store()
    parent = store.add("conv-orch", "assistant", "", status="awaiting_approval")
    row = _stale_turn(store, parent_message_id=parent["id"])
    _patch_recovery(monkeypatch, store, [_node("a")])

    assert await recovery.recover_once(_Client(store)) == 0
    assert store.row(row["id"])["status"] == "running"


@pytest.mark.anyio
async def test_resume_without_approvals_keeps_an_older_parked_run(monkeypatch):
    _use_model(monkeypatch, lambda m, i: _one("fresh"))
    store = _Store()
    row = _stale_turn(store)
    store.pending["conv-a"] = "older parked run"
    _patch_recovery(monkeypatch, store, [_node("a")])

    assert await recovery.recover_once(_Client(store)) == 1
    await _settle()
    await _finalisers()

    assert store.row(row["id"])["status"] == "complete"
    assert store.pending["conv-a"] == "older parked run"


@pytest.mark.anyio
async def test_no_checkpoint_walks_back_past_a_failed_reply(monkeypatch):
    seen = []

    async def stream(messages, info):
        seen.append([p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart)])
        yield "fresh"

    _use_model(monkeypatch, stream)
    store = _Store()
    store.add("conv-a", "user", "the prompt")
    store.add("conv-a", "assistant", "", status="failed")
    row = store.add("conv-a", "assistant", "", status="running", heartbeat_at=_iso(600))
    _patch_recovery(monkeypatch, store, [_node("a")])

    assert await recovery.recover_once(_Client(store)) == 1
    await _settle()
    assert seen[0] == ["the prompt"]
    assert store.row(row["id"])["status"] == "complete"


@pytest.mark.anyio
async def test_batch_is_not_starved_by_rows_skipped_every_poll(monkeypatch):
    _use_model(monkeypatch, lambda m, i: _one("fresh"))
    store = _Store()
    parent = store.add("conv-orch", "assistant", "", status="running", heartbeat_at=_iso())
    for i in range(recovery._BATCH):
        _stale_turn(store, conv=f"conv-n{i}", parent_message_id=parent["id"])
    # Live here with a late beat.
    for i in range(recovery._BATCH):
        _stale_turn(store, conv=f"conv-l{i}")
        runs.register(runs.RunningTurn(f"conv-l{i}", "n", "p", "m"))
    row = _stale_turn(store)
    _patch_recovery(monkeypatch, store, [_node("a")])

    assert await recovery.recover_once(_Client(store)) == 1
    for i in range(recovery._BATCH):
        runs.unregister(f"conv-l{i}")
    await _settle()
    assert store.row(row["id"])["status"] == "complete"


@pytest.mark.anyio
async def test_cancel_orphan_stops_a_stale_row_and_flags_a_beating_one():
    store = _Store()
    repos = _repos(store)
    store.add("conv-a", "user", "hi")
    row = store.add(
        "conv-a",
        "assistant",
        "",
        status="running",
        heartbeat_at=_iso(600),
        tool_calls=[{"type": "call", "tool_call_id": "c1", "name": "add"}],
    )
    store.checkpoints[row["id"]] = {"history": [], "content_len": 0, "events_len": 0}
    store.calls["c1"] = {"tool_call_id": "c1", "status": "running"}
    store.pending["conv-a"] = "parked"

    assert recovery.cancel_orphan(repos, "conv-a", "a").id == row["id"]
    assert (row["status"], row["error"]) == ("cancelled", None)
    assert row["tool_calls"][-1]["status"] == "cancelled"
    assert store.calls["c1"]["status"] == "cancelled"
    assert row["id"] not in store.checkpoints
    assert "conv-a" not in store.pending
    assert ("a", "ready") in store.node_status

    # Still beating: flagged for its driver, not finalised here.
    live = store.add("conv-b", "assistant", "", status="running", heartbeat_at=_iso())
    assert recovery.cancel_orphan(repos, "conv-b", "b").id == live["id"]
    assert (live["status"], live["cancel_requested"]) == ("running", True)
    assert recovery.cancel_orphan(repos, "conv-c", "c") is None


@pytest.mark.anyio
async def test_flagged_row_is_cancelled_not_resumed(monkeypatch):
    store = _Store()
    row = _stale_turn(store)
    row["cancel_requested"] = True
    _patch_recovery(monkeypatch, store, [_node("a")])

    assert await recovery.recover_once(_Client(store)) == 0
    assert (store.row(row["id"])["status"], row["resume_count"]) == ("cancelled", 0)
    assert ("a", "ready") in store.node_status


@pytest.mark.anyio
async def test_heartbeat_cancels_a_run_flagged_elsewhere(monkeypatch):
    store = _Store()
    row = store.add("conv-a", "assistant", "", status="running", heartbeat_at=_iso())
    run = runs.RunningTurn(conversation_id="conv-a", node_id="a", project_id="p", model="m")
    run.message = _to_message(row)
    cancelled = asyncio.Event()

    async def fake_cancel(r):
        assert r is run
        cancelled.set()

    monkeypatch.setattr(workflows, "cancel_turn", fake_cancel)
    monkeypatch.setattr(workflows, "_HEARTBEAT_S", 0.01)
    beat = workflows._Heartbeat(_Repo(store, ()), run)
    beat.start()
    await asyncio.sleep(0.05)
    assert not cancelled.is_set()
    row["cancel_requested"] = True
    await asyncio.wait_for(cancelled.wait(), 1)
    await beat.stop()


@pytest.mark.anyio
async def test_turn_busy_after_claim_cancels_only_the_claimed_row(monkeypatch):
    store = _Store()
    row = _stale_turn(store)
    store.calls["new"] = {"tool_call_id": "new", "status": "running"}
    _patch_recovery(monkeypatch, store, [_node("a")])

    async def busy(*a, **k):
        raise runs.TurnBusy("conv-a")

    monkeypatch.setattr(recovery, "start_turn", busy)

    assert await recovery.recover_once(_Client(store)) == 0
    assert store.row(row["id"])["status"] == "cancelled"
    # The new turn's call and node are left alone.
    assert store.calls["new"]["status"] == "running"
    assert store.node_status == []


@pytest.mark.anyio
async def test_cancel_route_stops_an_orphan(monkeypatch):
    from types import SimpleNamespace

    from app.routers import chat

    node_id, conv, msg = (f"00000000-0000-0000-0000-00000000000{c}" for c in "abc")
    store = _Store()
    row = _stale_turn(store, conv=conv)
    row["id"] = msg
    node = SimpleNamespace(id=node_id, conversation_id=conv)
    out = await chat.chat_cancel(
        SimpleNamespace(node_id=node_id),
        SimpleNamespace(get_agent_node=lambda _id: node),
        _repos(store),
    )
    assert str(out.message_id) == msg
    assert row["status"] == "cancelled"


# -- shutdown handoff ---------------------------------------------------------------


@pytest.mark.anyio
async def test_handoff_leaves_the_row_running_with_a_stale_heartbeat(monkeypatch):
    gate = asyncio.Event()
    reached = asyncio.Event()

    async def slow(messages, info):
        yield "partial"
        reached.set()
        await gate.wait()
        yield " never"

    _use_model(monkeypatch, slow)
    store = _Store()
    run = await workflows.start_turn(_Repo(store), "c", "s", "m", "hi", node_id="n", project_id="p")
    async with asyncio.timeout(5):
        await reached.wait()
    await asyncio.sleep(0.05)

    assert await runs.hand_off(5) == 1

    row = store.row(run.message.id)
    assert row["status"] == "running"
    assert row["heartbeat_at"] == runs._EPOCH
    assert row["content"] == "partial"
    assert runs.is_stale(_to_message(row))
    assert ("n", "ready") not in store.node_status
    assert run.task.done()


@pytest.mark.anyio
async def test_user_cancel_during_handoff_still_finalises(monkeypatch):
    gate = asyncio.Event()
    reached = asyncio.Event()

    async def slow(messages, info):
        yield "partial"
        reached.set()
        await gate.wait()

    _use_model(monkeypatch, slow)
    store = _Store()
    run = await workflows.start_turn(_Repo(store), "c", "s", "m", "hi", node_id="n", project_id="p")
    async with asyncio.timeout(5):
        await reached.wait()
    await workflows.cancel_turn(run)
    monkeypatch.setattr(runs, "_handing_off", True)
    await run.task
    await _finalisers()
    assert store.row(run.message.id)["status"] == "cancelled"


async def _approved_resume(store, add_fn):
    """An approved resume of call c1, parked on conversation c."""
    from pydantic_ai import DeferredToolResults

    history = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(parts=[ToolCallPart(tool_name="add", args={"x": 1}, tool_call_id="c1")]),
    ]
    store.pending["c"] = ModelMessagesTypeAdapter.dump_json(history).decode()
    parked = _to_message(store.add("c", "assistant", "", status="awaiting_approval"))
    # Kept from the pause.
    store.checkpoints[parked.id] = {
        "history": ModelMessagesTypeAdapter.dump_python(history, mode="json"),
        "content_len": 0,
        "events_len": 0,
    }
    repo = _Repo(store)
    return await workflows.start_turn(
        repo,
        "c",
        "s",
        "m",
        None,
        node_id="n",
        project_id="p",
        tool_repo=repo,
        toolsets=[FunctionToolset([add_fn])],
        resume=workflows.ResumeInput(history, DeferredToolResults(approvals={"c1": True}), parked),
    )


@pytest.mark.anyio
async def test_approved_resume_clears_its_parked_run_before_done(monkeypatch):
    _use_model(monkeypatch)
    store = _Store()
    run = await _approved_resume(store, add)

    events = [e async for e, _ in workflows.attach_events(run)]

    # Cleared before the terminal event, so no reader sees the end with it still set.
    assert events[-1] == "done"
    assert "c" not in store.pending
    assert ADDS == [1]


@pytest.mark.anyio
async def test_approved_resume_keeps_its_parked_run_through_a_handoff(monkeypatch):
    gate, reached = asyncio.Event(), asyncio.Event()

    async def add(x: int) -> str:
        reached.set()
        await gate.wait()
        return "never"

    _use_model(monkeypatch)
    store = _Store()
    run = await _approved_resume(store, add)
    async with asyncio.timeout(5):
        await reached.wait()

    assert await runs.hand_off(5) == 1
    await _finalisers()

    # Recovery reads both to replay exactly the approval given.
    assert "c" in store.pending
    assert store.checkpoints[run.message.id]["approvals"] == {"c1": True}
    assert run.task.done()


@pytest.mark.anyio
async def test_handoff_waits_out_a_pause_still_parking(monkeypatch):
    from pydantic_ai.toolsets import ApprovalRequiredToolset

    gate, parking = asyncio.Event(), asyncio.Event()

    async def on_paused(pending, messages):
        parking.set()
        await gate.wait()

    _use_model(monkeypatch)
    store = _Store()
    run = await workflows.start_turn(
        _Repo(store),
        "c",
        "s",
        "m",
        "hi",
        node_id="n",
        project_id="p",
        toolsets=[ApprovalRequiredToolset(_toolset())],
        on_paused=on_paused,
    )
    async with asyncio.timeout(5):
        await parking.wait()
    handoff = asyncio.ensure_future(runs.hand_off(5))
    await asyncio.sleep(0.05)
    gate.set()
    await handoff

    # Parked, and no stale beat stamped on it after.
    row = store.row(run.message.id)
    assert row["status"] == "awaiting_approval"
    assert row["heartbeat_at"] != runs._EPOCH


@pytest.mark.anyio
async def test_run_agent_token_is_scoped_to_the_orchestrator_row(monkeypatch):
    from types import SimpleNamespace

    store = _Store()
    orch_row = store.add("conv-orch", "assistant", "", status="running")
    runs.register(runs.RunningTurn("conv-orch", "orch", "p", "m", message=_to_message(orch_row)))
    tools = _canvas(store)
    seen = []

    async def fake_run_agent(node_id, prompt, *, client_token=None):
        seen.append(client_token)
        return "ok"

    monkeypatch.setattr(tools, "run_agent", fake_run_agent)
    await tools._run_agent_tool(SimpleNamespace(tool_call_id="call_0"), "a", "go")
    assert seen == [f"run_agent:{orch_row['id']}:call_0"]


@pytest.mark.anyio
async def test_rejoin_cancelled_child_stays_cancelled(monkeypatch):
    monkeypatch.setattr(canvas, "prepare_turn", _prepared_async)
    store = _Store()
    store.add("conv-a", "user", "go", client_token="run_agent:c9")
    store.add("conv-a", "assistant", "", status="cancelled")

    out = await _canvas(store).run_agent("a", "go", client_token="run_agent:c9")

    assert out.startswith("Cancelled by user")
    assert len(store.rows) == 2


@pytest.mark.anyio
async def test_rejoin_flagged_stale_child_is_cancelled_not_resumed(monkeypatch):
    monkeypatch.setattr(canvas, "prepare_turn", _prepared_async)
    store = _Store()
    store.add("conv-a", "user", "go", client_token="run_agent:c9")
    child = store.add("conv-a", "assistant", "", status="running", heartbeat_at=_iso(600))
    child["cancel_requested"] = True

    out = await _canvas(store).run_agent("a", "go", client_token="run_agent:c9")

    assert out.startswith("Cancelled by user")
    assert (child["status"], child["resume_count"]) == ("cancelled", 0)
    assert len(store.rows) == 2


# -- run_agent rejoin -----------------------------------------------------------------


def _canvas(store, conversation_id="conv-orch"):
    return canvas.CanvasTools(_repos(store, [ORCH, _node("a")]), ORCH, conversation_id)


async def _prepared_async(*a, **k):
    from tests.test_canvas_tools import _prepared

    return _prepared()


@pytest.mark.anyio
async def test_rejoin_complete_child_returns_its_reply_without_running(monkeypatch):
    monkeypatch.setattr(canvas, "prepare_turn", _prepared_async)
    store = _Store()
    store.add("conv-a", "user", "go", client_token="run_agent:c9")
    store.add(
        "conv-a",
        "assistant",
        "let me look the answer",
        tool_calls=[{"type": "call", "offset": 12}, {"type": "result", "offset": 12}],
    )

    out = await _canvas(store).run_agent("a", "go", client_token="run_agent:c9")

    assert out == "the answer"
    assert len(store.rows) == 2


@pytest.mark.anyio
async def test_rejoin_stale_running_child_resumes_it_under_this_run(monkeypatch):
    _use_model(monkeypatch)
    monkeypatch.setattr(canvas, "prepare_turn", _prepared_async)

    async def prepared_with_tool(*a, **k):
        from app.services.turns import PreparedTurn
        from app.tools.assembly import AssembledTools

        return PreparedTurn(instructions=None, toolsets=[_toolset()], tools=AssembledTools())

    monkeypatch.setattr(canvas, "prepare_turn", prepared_with_tool)
    store = _Store()
    orch_row = store.add("conv-orch", "assistant", "", status="running", heartbeat_at=_iso())
    orch = runs.RunningTurn(
        conversation_id="conv-orch",
        node_id="orch",
        project_id="p",
        model="m",
        message=_to_message(orch_row),
    )
    runs.register(orch)
    store.add("conv-a", "user", "go", client_token="run_agent:c9")
    child = store.add(
        "conv-a",
        "assistant",
        "",
        status="running",
        heartbeat_at=_iso(600),
        parent_message_id="old-parent",
    )

    out = await _canvas(store).run_agent("a", "go", client_token="run_agent:c9")

    assert out == "done"
    final = store.row(child["id"])
    assert final["status"] == "complete"
    assert final["parent_message_id"] == orch_row["id"]
    assert final["resume_count"] == 1
    # No second user or assistant row.
    assert [r["role"] for r in store.rows if r["conversation_id"] == "conv-a"] == [
        "user",
        "assistant",
    ]


@pytest.mark.anyio
async def test_rejoin_live_child_awaits_it(monkeypatch):
    gate = asyncio.Event()

    async def slow(messages, info):
        await gate.wait()
        yield "live reply"

    _use_model(monkeypatch, slow)
    monkeypatch.setattr(canvas, "prepare_turn", _prepared_async)
    store = _Store()
    repo = _Repo(store)
    live = await workflows.start_turn(
        repo, "conv-a", "s", "m", "go", node_id="a", project_id="p", client_token="run_agent:c9"
    )

    task = asyncio.ensure_future(_canvas(store).run_agent("a", "go", client_token="run_agent:c9"))
    await asyncio.sleep(0.05)
    gate.set()
    async with asyncio.timeout(5):
        out = await task

    assert out == "live reply"
    assert store.row(live.message.id)["status"] == "complete"
    assert [r["role"] for r in store.rows] == ["user", "assistant"]


@pytest.mark.anyio
async def test_failed_child_runs_fresh_on_the_same_user_row(monkeypatch):
    _use_model(monkeypatch, lambda m, i: _one("again"))
    monkeypatch.setattr(canvas, "prepare_turn", _prepared_async)
    store = _Store()
    store.add("conv-a", "user", "go", client_token="run_agent:c9")
    store.add("conv-a", "assistant", "", status="failed")

    out = await _canvas(store).run_agent("a", "go", client_token="run_agent:c9")

    assert out == "again"
    assert [r["role"] for r in store.rows] == ["user", "assistant", "assistant"]


async def _one(text):
    yield text


def test_run_agent_tool_schema_has_no_ctx_or_token():
    tools = _canvas(_Store()).toolset().tools
    schema = tools["run_agent"].function_schema.json_schema
    assert set(schema["properties"]) == {"node_id", "prompt"}
    assert tools["run_agent"].takes_ctx
    assert "Send prompt to an agent" in tools["run_agent"].description
