"""EnvironmentRepository against a fake PostgREST client. No database."""

from typing import Any

from postgrest.exceptions import APIError

from app.repositories.environment_repo import (
    EnvironmentRepository,
    EnvNode,
    scratch_config,
)

_PROJECT = "11111111-1111-1111-1111-111111111111"
_USER = "22222222-2222-2222-2222-222222222222"
_NODE = "33333333-3333-3333-3333-333333333333"


class _Result:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _Query:
    """One chained PostgREST call. Records filters, defers to the fake db."""

    def __init__(self, db: "_FakeDB", table: str, op: str, payload: Any = None) -> None:
        self._db = db
        self._table = table
        self._op = op
        self._payload = payload
        self.filters: dict[str, Any] = {}

    def select(self, *_a: Any, **_k: Any) -> "_Query":
        return self

    def eq(self, key: str, value: Any) -> "_Query":
        self.filters[key] = value
        return self

    def in_(self, key: str, values: list) -> "_Query":
        self.filters[f"{key}__in"] = values
        return self

    def limit(self, *_a: Any) -> "_Query":
        return self

    def order(self, *_a: Any, **_k: Any) -> "_Query":
        return self

    def execute(self) -> _Result:
        return self._db.run(self._table, self._op, self._payload, self.filters)


class _TableRef:
    def __init__(self, db: "_FakeDB", name: str) -> None:
        self._db = db
        self._name = name

    def select(self, *_a: Any, **_k: Any) -> _Query:
        return _Query(self._db, self._name, "select")

    def insert(self, payload: dict) -> _Query:
        return _Query(self._db, self._name, "insert", payload)

    def update(self, payload: dict) -> _Query:
        return _Query(self._db, self._name, "update", payload)


class _FakeDB:
    """Rows in a list. Only the matching behaviour the repository relies on."""

    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []
        self.raise_on_insert: Exception | None = None
        self.on_insert = None
        self.ops: list[tuple[str, str, dict]] = []

    def table(self, name: str) -> _TableRef:
        return _TableRef(self, name)

    def run(self, table: str, op: str, payload: Any, filters: dict) -> _Result:
        self.ops.append((table, op, filters))
        if op == "insert":
            if self.on_insert is not None:
                self.on_insert()
            if self.raise_on_insert is not None:
                exc, self.raise_on_insert = self.raise_on_insert, None
                raise exc
            row = {"id": _NODE, **payload}
            self.rows.append(row)
            return _Result([row])
        matched = [r for r in self.rows if self._matches(r, filters)]
        if op == "update":
            for row in matched:
                row.update(payload)
        return _Result(list(matched))

    @staticmethod
    def _matches(row: dict, filters: dict) -> bool:
        for key, value in filters.items():
            if key.endswith("__in"):
                if row.get(key[:-4]) not in value:
                    return False
            elif key == "config->>role":
                if (row.get("config") or {}).get("role") != value:
                    return False
            elif row.get(key) != value:
                return False
        return True


def _row(**over: Any) -> dict:
    base = {
        "id": _NODE,
        "project_id": _PROJECT,
        "owner_id": _USER,
        "kind": "environment",
        "name": "Scratch Space",
        "config": scratch_config(),
        "status": "pending",
        "status_detail": None,
        "tool_policy": "auto",
        "position_x": 0.0,
        "position_y": 0.0,
    }
    base.update(over)
    return base


def _repo(db: _FakeDB) -> EnvironmentRepository:
    return EnvironmentRepository(db, _USER)


# -- config and dataclass ----------------------------------------------------


def test_scratch_config_shape():
    cfg = scratch_config()
    assert cfg["runtime"] == "e2b"
    assert cfg["role"] == "scratch"
    assert cfg["sandbox_id"] is None
    assert cfg["preview_ports"] == []
    assert isinstance(cfg["idle_timeout_s"], int)


def test_env_node_reads_identity_from_config():
    node = EnvNode(
        id=_NODE,
        project_id=_PROJECT,
        name="Coding",
        config={"runtime": "e2b", "role": "user", "sandbox_id": "sbx_1"},
        status="ready",
        status_detail=None,
        tool_policy="ask",
        position_x=0.0,
        position_y=0.0,
    )
    assert (node.runtime, node.role, node.sandbox_id) == ("e2b", "user", "sbx_1")


def test_env_node_defaults_when_config_is_empty():
    node = EnvNode(_NODE, _PROJECT, "x", {}, "pending", None, "ask", 0.0, 0.0)
    assert (node.runtime, node.role, node.sandbox_id) == ("e2b", "user", None)


def test_env_node_blank_sandbox_id_reads_as_none():
    """A cleared sandbox_id is written as null but may round trip as ''."""
    node = EnvNode(_NODE, _PROJECT, "x", {"sandbox_id": ""}, "stopped", None, "ask", 0.0, 0.0)
    assert node.sandbox_id is None


# -- reads -------------------------------------------------------------------


def test_get_environment_node_filters_owner_and_kind():
    db = _FakeDB([_row()])
    assert _repo(db).get_environment_node(_NODE) is not None
    _table, _op, filters = db.ops[-1]
    assert filters["kind"] == "environment"
    assert filters["owner_id"] == _USER


def test_get_environment_node_missing_is_none():
    assert _repo(_FakeDB([])).get_environment_node(_NODE) is None


def test_get_environment_node_ignores_other_kinds():
    db = _FakeDB([_row(kind="agent")])
    assert _repo(db).get_environment_node(_NODE) is None


def test_list_environment_nodes_scopes_to_project():
    db = _FakeDB([_row(), _row(id="other", project_id="99999999-9999-9999-9999-999999999999")])
    nodes = _repo(db).list_environment_nodes(_PROJECT)
    assert [n.id for n in nodes] == [_NODE]


# -- scratch -----------------------------------------------------------------


def test_ensure_scratch_node_returns_existing_without_inserting():
    db = _FakeDB([_row()])
    node = _repo(db).ensure_scratch_node(_PROJECT)
    assert node.role == "scratch"
    assert not any(op == "insert" for _t, op, _f in db.ops)


def test_ensure_scratch_node_creates_when_missing():
    db = _FakeDB([])
    node = _repo(db).ensure_scratch_node(_PROJECT)
    assert node.role == "scratch"
    assert node.tool_policy == "auto"


def test_ensure_scratch_node_rereads_after_unique_violation():
    """A concurrent create wins nodes_one_scratch_per_project: re-read, do not raise."""
    db = _FakeDB([])
    db.raise_on_insert = APIError({"code": "23505", "message": "duplicate key"})
    # The other writer's row lands just before our insert is rejected.
    db.on_insert = lambda: db.rows.append(_row())

    node = _repo(db).ensure_scratch_node(_PROJECT)
    assert node.role == "scratch"


def test_ensure_scratch_node_reraises_other_api_errors():
    db = _FakeDB([])
    db.raise_on_insert = APIError({"code": "42501", "message": "permission denied"})
    try:
        _repo(db).ensure_scratch_node(_PROJECT)
    except APIError as exc:
        assert exc.code == "42501"
    else:
        raise AssertionError("expected APIError to propagate")


# -- writes ------------------------------------------------------------------


def test_create_environment_node_sets_kind_and_pending_status():
    db = _FakeDB([])
    node_id = _repo(db).create_environment_node(
        _PROJECT, "Coding", {"runtime": "e2b", "role": "user"}
    )
    assert node_id == _NODE
    row = db.rows[0]
    assert row["kind"] == "environment"
    assert row["status"] == "pending"
    assert "agent_type_id" not in row
    assert "tool_type_id" not in row


def test_set_status_writes_detail_and_last_checked_at():
    db = _FakeDB([_row()])
    _repo(db).set_status(_NODE, "ready", "Sandbox running")
    assert db.rows[0]["status"] == "ready"
    assert db.rows[0]["status_detail"] == "Sandbox running"
    assert db.rows[0]["last_checked_at"] is not None


def test_set_config_replaces_config():
    db = _FakeDB([_row()])
    _repo(db).set_config(_NODE, {"runtime": "e2b", "role": "scratch", "sandbox_id": "sbx_9"})
    assert db.rows[0]["config"]["sandbox_id"] == "sbx_9"


def test_update_environment_node_ignores_unknown_and_none_fields():
    db = _FakeDB([_row(name="old")])
    _repo(db).update_environment_node(
        _NODE, {"name": "new", "status": "ready", "config": {}, "tool_policy": None}
    )
    assert db.rows[0]["name"] == "new"
    assert db.rows[0]["status"] == "pending"
    assert db.rows[0]["tool_policy"] == "auto"


def test_update_environment_node_empty_payload_is_a_read():
    db = _FakeDB([_row(name="same")])
    node = _repo(db).update_environment_node(_NODE, {})
    assert node is not None and node.name == "same"


def test_update_environment_node_missing_returns_none():
    assert _repo(_FakeDB([])).update_environment_node(_NODE, {"name": "x"}) is None


# -- compare and set ---------------------------------------------------------


def test_try_begin_provisioning_claims_pending():
    db = _FakeDB([_row(status="pending")])
    assert _repo(db).try_begin_provisioning(_NODE) is True
    assert db.rows[0]["status"] == "provisioning"
    assert db.rows[0]["status_detail"] is None


def test_try_begin_provisioning_claims_error_and_stopped():
    for status in ("error", "stopped"):
        db = _FakeDB([_row(status=status)])
        assert _repo(db).try_begin_provisioning(_NODE) is True


def test_try_begin_provisioning_loses_against_ready():
    db = _FakeDB([_row(status="ready")])
    assert _repo(db).try_begin_provisioning(_NODE) is False
    assert db.rows[0]["status"] == "ready"


def test_try_begin_provisioning_loses_against_concurrent_claim():
    """The second caller finds provisioning and must not start a second sandbox."""
    db = _FakeDB([_row(status="provisioning")])
    assert _repo(db).try_begin_provisioning(_NODE) is False
