"""delete_node cascades orphaned tool nodes when an agent goes.

Edges cascade in the database, other node rows do not, so a tool box used only
by the deleted agent was left stranded on the canvas.
"""

import uuid

import pytest

from app.repositories.project_repo import ProjectRepository

_OWNER = "owner-1"
_PROJECT = "project-1"


class _Query:
    """Enough PostgREST for delete_node: select/delete with eq, in_, limit."""

    def __init__(self, db, table):
        self.db, self.table = db, table
        self.filters: dict[str, object] = {}
        self.in_ids: set[str] | None = None
        self.mode = "select"

    def select(self, *_):
        self.mode = "select"
        return self

    def delete(self):
        self.mode = "delete"
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def in_(self, key, values):
        assert key == "id"
        self.in_ids = set(values)
        return self

    def limit(self, *_):
        return self

    def _matches(self, row):
        if self.in_ids is not None and row["id"] not in self.in_ids:
            return False
        return all(row.get(k) == v for k, v in self.filters.items())

    def execute(self):
        rows = self.db[self.table]
        hits = [r for r in rows if self._matches(r)]
        if self.mode == "delete":
            for hit in hits:
                rows.remove(hit)
                if self.table == "nodes":
                    # The real FK cascade: a node's edges go with it.
                    self.db["edges"] = [
                        e
                        for e in self.db["edges"]
                        if hit["id"] not in (e["source_node_id"], e["target_node_id"])
                    ]
        return type("R", (), {"data": [dict(r) for r in hits]})()


class _FakeDb:
    def __init__(self, nodes, edges):
        self.data = {"nodes": nodes, "edges": edges}

    def __getitem__(self, table):
        return self.data[table]

    def __setitem__(self, table, rows):
        self.data[table] = rows

    def table(self, name):
        return _Query(self, name)


def _node(kind, node_id=None):
    return {
        "id": node_id or str(uuid.uuid4()),
        "owner_id": _OWNER,
        "project_id": _PROJECT,
        "kind": kind,
    }


def _edge(source, target):
    return {
        "id": str(uuid.uuid4()),
        "owner_id": _OWNER,
        "project_id": _PROJECT,
        "source_node_id": source["id"],
        "target_node_id": target["id"],
    }


def _repo(nodes, edges):
    db = _FakeDb(nodes, edges)
    return ProjectRepository(db, _OWNER), db


def test_exclusive_tool_goes_with_its_agent():
    agent, tool = _node("agent"), _node("tool")
    repo, db = _repo([agent, tool], [_edge(tool, agent)])

    assert repo.delete_node(agent["id"]) == [agent["id"], tool["id"]]
    assert db["nodes"] == []


def test_shared_tool_survives():
    agent, other, tool = _node("agent"), _node("agent"), _node("tool")
    repo, db = _repo([agent, other, tool], [_edge(tool, agent), _edge(tool, other)])

    assert repo.delete_node(agent["id"]) == [agent["id"]]
    assert [n["id"] for n in db["nodes"]] == [other["id"], tool["id"]]


def test_environment_node_is_never_swept():
    agent, env = _node("agent"), _node("environment")
    repo, db = _repo([agent, env], [_edge(env, agent)])

    assert repo.delete_node(agent["id"]) == [agent["id"]]
    assert [n["id"] for n in db["nodes"]] == [env["id"]]


def test_deleting_a_tool_directly_returns_only_itself():
    agent, tool = _node("agent"), _node("tool")
    repo, db = _repo([agent, tool], [_edge(tool, agent)])

    assert repo.delete_node(tool["id"]) == [tool["id"]]
    assert [n["id"] for n in db["nodes"]] == [agent["id"]]


def test_unknown_id_returns_empty():
    agent = _node("agent")
    repo, db = _repo([agent], [])

    assert repo.delete_node(str(uuid.uuid4())) == []
    assert len(db["nodes"]) == 1


@pytest.mark.parametrize("kind", ["agent", "tool", "environment"])
def test_another_owner_cannot_delete(kind):
    node = _node(kind)
    node["owner_id"] = "someone-else"
    repo, db = _repo([node], [])

    assert repo.delete_node(node["id"]) == []
    assert len(db["nodes"]) == 1
