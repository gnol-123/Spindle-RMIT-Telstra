"""One summariser call per distinct summary_max_words, whatever the edge count."""

import dataclasses

import pytest

import app.workflows as workflows
from app.repositories.project_repo import Edge, Message


def _edge(i, words):
    return Edge(
        id=f"e{i}",
        source_node_id="src",
        target_node_id=f"t{i}",
        kind="context",
        summary=None,
        summarised_through_seq=None,
        summary_updated_at=None,
        summary_max_words=words,
    )


class _Repo:
    def __init__(self, edges):
        self.edges = edges
        self.updates = []

    def list_outbound_context_edges(self, node_id):
        return self.edges

    def get_conversation_for_node(self, node_id):
        return "conv"

    def list_messages(self, conversation_id, limit=50):
        return [
            Message(
                id="m", role="assistant", content="scope", seq=1, status="complete", created_at="t"
            )
        ]

    def update_edge_summary(self, edge_id, summary, through_seq):
        self.updates.append((edge_id, summary, through_seq))
        return next(e for e in self.edges if e.id == edge_id)


@pytest.mark.anyio
async def test_dedupes_by_max_words(monkeypatch):
    calls = []

    async def fake_summarise(history, max_words):
        calls.append(max_words)
        return f"sum{max_words}"

    monkeypatch.setattr(workflows, "summarise_conversation", fake_summarise)
    repo = _Repo([_edge(1, 1000), _edge(2, 1000), _edge(3, 200)])

    failed = await workflows.refresh_outbound(repo, "src")

    assert failed == []
    assert sorted(calls) == [200, 1000]
    assert sorted(repo.updates) == [("e1", "sum1000", 1), ("e2", "sum1000", 1), ("e3", "sum200", 1)]


@pytest.mark.anyio
async def test_failure_reported_not_raised(monkeypatch):
    async def boom(history, max_words):
        raise RuntimeError("summariser down")

    monkeypatch.setattr(workflows, "summarise_conversation", boom)
    repo = _Repo([_edge(1, 1000)])

    failed = await workflows.refresh_outbound(repo, "src")

    assert failed == ["e1"]
    assert repo.updates == []


@pytest.mark.anyio
async def test_refresh_edge_without_conversation_stores_empty():
    class R(_Repo):
        def get_conversation_for_node(self, node_id):
            return None

    repo = R([_edge(1, 1000)])
    await workflows.refresh_edge(repo, repo.edges[0])
    assert repo.updates == [("e1", "", 0)]


@pytest.mark.anyio
async def test_refresh_head_ignores_running_row(monkeypatch):
    """A running assistant row must not count toward the summarised head."""

    async def fake_summarise(history, max_words):
        return "sum"

    monkeypatch.setattr(workflows, "summarise_conversation", fake_summarise)

    class R(_Repo):
        def list_messages(self, conversation_id, limit=50):
            return [
                Message(
                    id="u1", role="user", content="hi", seq=1, status="complete", created_at="t"
                ),
                Message(
                    id="a1",
                    role="assistant",
                    content="done",
                    seq=2,
                    status="complete",
                    created_at="t",
                ),
                Message(
                    id="a2",
                    role="assistant",
                    content="partial",
                    seq=3,
                    status="running",
                    created_at="t",
                ),
            ]

    repo = R([_edge(1, 1000)])
    await workflows.refresh_edge(repo, repo.edges[0])
    assert repo.updates == [("e1", "sum", 2)]


@pytest.mark.anyio
async def test_refresh_outbound_head_ignores_running_row(monkeypatch):
    async def fake_summarise(history, max_words):
        return "sum"

    monkeypatch.setattr(workflows, "summarise_conversation", fake_summarise)

    class R(_Repo):
        def list_messages(self, conversation_id, limit=50):
            return [
                Message(
                    id="u1", role="user", content="hi", seq=1, status="complete", created_at="t"
                ),
                Message(
                    id="a1",
                    role="assistant",
                    content="done",
                    seq=2,
                    status="complete",
                    created_at="t",
                ),
                Message(
                    id="a2",
                    role="assistant",
                    content="partial",
                    seq=3,
                    status="running",
                    created_at="t",
                ),
            ]

    repo = R([_edge(1, 1000)])
    failed = await workflows.refresh_outbound(repo, "src")
    assert failed == []
    assert repo.updates == [("e1", "sum", 2)]


# -- read side agrees with write side -----------------------------------------


class _FakeQuery:
    """Enough PostgREST to answer get_conversation_head over a message list."""

    def __init__(self, table, history):
        self.table, self.history, self.filters = table, history, {}

    def select(self, *_):
        return self

    def eq(self, k, v):
        self.filters[k] = v
        return self

    def order(self, *_, **__):
        self._desc = True
        return self

    def limit(self, *_):
        return self

    def execute(self):
        if self.table == "conversations":
            rows = [{"id": "conv", "message_count": len(self.history)}]
        else:
            rows = [
                {"seq": m.seq}
                for m in sorted(self.history, key=lambda m: -m.seq)
                if m.status == self.filters.get("status", m.status)
            ][:1]
        return type("R", (), {"data": rows})()


class _FakeDb:
    def __init__(self, history):
        self.history = history

    def table(self, name):
        return _FakeQuery(name, self.history)


class _StaleRepo(_Repo):
    """Read and write sides over one fake history.

    get_conversation_head is the real ProjectRepository method, bound over a
    fake PostgREST client, so the read side is exercised rather than faked.
    """

    def __init__(self, edges, history):
        super().__init__(edges)
        self.history = history

    def list_messages(self, conversation_id, limit=50):
        return self.history

    def get_conversation_head(self, node_id):
        from app.repositories.project_repo import ProjectRepository

        return ProjectRepository(_FakeDb(self.history), "u1").get_conversation_head(node_id)

    def conversation_ids_for_nodes(self, node_ids):
        return {n: "conv" for n in node_ids}

    def conversation_head_seq(self, conversation_id):
        from app.repositories.project_repo import ProjectRepository

        return ProjectRepository(_FakeDb(self.history), "u1").conversation_head_seq(conversation_id)

    def update_edge_summary(self, edge_id, summary, through_seq):
        self.updates.append((edge_id, summary, through_seq))
        edge = next(e for e in self.edges if e.id == edge_id)
        fresh = dataclasses.replace(edge, summary=summary, summarised_through_seq=through_seq)
        self.edges = [fresh if e.id == edge_id else e for e in self.edges]
        return fresh

    def get_project(self, project_id):
        return object()

    def list_edges(self, project_id):
        return self.edges


_UUID = "11111111-1111-1111-1111-11111111111{}"


def _uuid_edge(words):
    return Edge(
        id=_UUID.format(1),
        source_node_id=_UUID.format(2),
        target_node_id=_UUID.format(3),
        kind="context",
        summary=None,
        summarised_through_seq=None,
        summary_updated_at=None,
        summary_max_words=words,
    )


def _msg(seq, status, role="assistant"):
    return Message(id=f"m{seq}", role=role, content="x", seq=seq, status=status, created_at="t")


@pytest.mark.parametrize("tail_status", ["cancelled", "running", "failed"])
@pytest.mark.anyio
async def test_edge_reads_fresh_after_refresh_with_non_complete_tail(monkeypatch, tail_status):
    """A cancelled, running or failed tail must not leave the edge permanently stale."""
    from app.routers.projects import list_edges

    async def fake_summarise(history, max_words):
        return "sum"

    monkeypatch.setattr(workflows, "summarise_conversation", fake_summarise)

    history = [
        _msg(1, "complete", "user"),
        _msg(2, "complete"),
        _msg(3, "complete", "user"),
        _msg(4, tail_status),
    ]
    repo = _StaleRepo([_uuid_edge(1000)], history)

    await workflows.refresh_edge(repo, repo.edges[0])
    assert repo.updates == [(_UUID.format(1), "sum", 3)]

    out = await list_edges("11111111-1111-1111-1111-111111111111", repo)
    assert [(e.is_stale, e.messages_behind) for e in out] == [(False, 0)]


@pytest.mark.anyio
async def test_edge_goes_stale_when_a_new_complete_row_lands(monkeypatch):
    from app.routers.projects import list_edges

    async def fake_summarise(history, max_words):
        return "sum"

    monkeypatch.setattr(workflows, "summarise_conversation", fake_summarise)

    history = [_msg(1, "complete", "user"), _msg(2, "complete")]
    repo = _StaleRepo([_uuid_edge(1000)], history)
    await workflows.refresh_edge(repo, repo.edges[0])

    history.append(_msg(3, "complete", "user"))
    history.append(_msg(4, "complete"))

    out = await list_edges("11111111-1111-1111-1111-111111111111", repo)
    assert [(e.is_stale, e.messages_behind) for e in out] == [(True, 2)]
