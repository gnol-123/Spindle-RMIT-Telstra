"""Repository additions for the orchestrator: tool_policy on create, summary_max_words on edges,
outbound edge listing, messages after a seq."""

from app.repositories.project_repo import ProjectRepository


class _Query:
    def __init__(self, log, table, rows):
        self.log, self.table, self.rows = log, table, rows
        self.filters = {}

    def insert(self, payload):
        self.log.append((self.table, "insert", payload))
        return self

    def select(self, *_):
        return self

    def update(self, payload):
        self.log.append((self.table, "update", payload))
        return self

    def eq(self, k, v):
        self.filters[k] = v
        return self

    def gt(self, k, v):
        self.filters[f"{k}>"] = v
        return self

    def order(self, *_, **__):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        self.log.append((self.table, "filters", dict(self.filters)))
        return type("R", (), {"data": self.rows})()


class _Db:
    def __init__(self, rows_by_table):
        self.log = []
        self.rows = rows_by_table

    def table(self, name):
        return _Query(self.log, name, self.rows.get(name, []))


def test_create_node_passes_tool_policy():
    db = _Db({"nodes": [{"id": "n1"}], "conversations": [{"id": "c1"}]})
    repo = ProjectRepository(db, "u1")
    repo.create_node("p1", "at1", "Scoping", tool_policy="auto")
    payload = next(p for t, op, p in db.log if t == "nodes" and op == "insert")
    assert payload["tool_policy"] == "auto"


def test_create_edge_passes_summary_max_words():
    row = {"id": "e1", "source_node_id": "a", "target_node_id": "b", "kind": "context"}
    db = _Db({"edges": [row]})
    ProjectRepository(db, "u1").create_edge("a", "b", summary_max_words=1000)
    payload = next(p for t, op, p in db.log if t == "edges" and op == "insert")
    assert payload["summary_max_words"] == 1000


def test_create_edge_omits_summary_max_words_by_default():
    row = {"id": "e1", "source_node_id": "a", "target_node_id": "b", "kind": "context"}
    db = _Db({"edges": [row]})
    ProjectRepository(db, "u1").create_edge("a", "b")
    payload = next(p for t, op, p in db.log if t == "edges" and op == "insert")
    assert "summary_max_words" not in payload


def test_list_outbound_context_edges_filters_source_kind_owner():
    row = {"id": "e1", "source_node_id": "a", "target_node_id": "b", "kind": "context"}
    db = _Db({"edges": [row]})
    edges = ProjectRepository(db, "u1").list_outbound_context_edges("a")
    assert [e.id for e in edges] == ["e1"]
    filters = next(p for t, op, p in db.log if t == "edges" and op == "filters")
    assert filters == {"source_node_id": "a", "kind": "context", "owner_id": "u1"}


def test_get_conversation_head_reads_last_complete_seq():
    """Head must be max(seq) over complete rows, not the message_count counter."""
    db = _Db(
        {
            "conversations": [{"id": "c1", "message_count": 4}],
            "messages": [{"seq": 2}],
        }
    )
    assert ProjectRepository(db, "u1").get_conversation_head("n1") == 2
    filters = next(p for t, op, p in db.log if t == "messages" and op == "filters")
    assert filters == {"conversation_id": "c1", "owner_id": "u1", "status": "complete"}


def test_get_conversation_head_zero_without_conversation():
    assert ProjectRepository(_Db({}), "u1").get_conversation_head("n1") == 0


def test_get_conversation_head_zero_without_complete_rows():
    db = _Db({"conversations": [{"id": "c1", "message_count": 2}], "messages": []})
    assert ProjectRepository(db, "u1").get_conversation_head("n1") == 0


def test_list_messages_after_uses_gt_and_ascending():
    row = {
        "id": "m2",
        "role": "user",
        "content": "x",
        "seq": 2,
        "status": "complete",
        "created_at": "t",
    }
    db = _Db({"messages": [row]})
    out = ProjectRepository(db, "u1").list_messages_after("c1", after_seq=1)
    assert [m.seq for m in out] == [2]
    filters = next(p for t, op, p in db.log if t == "messages" and op == "filters")
    assert filters["seq>"] == 1 and filters["owner_id"] == "u1"
