"""The environment lifecycle: provision, stop, teardown, verify.

No E2B and no database. The spec is faked at the registry boundary, the
repository at the EnvNode boundary.
"""

import pytest

from app.environments import lifecycle
from app.environments.base import EnvSpec
from app.repositories.environment_repo import EnvNode
from app.tools.base import VerifyResult

_NODE = "11111111-1111-1111-1111-111111111111"
_PROJECT = "22222222-2222-2222-2222-222222222222"


def _node(**over) -> EnvNode:
    base = {
        "id": _NODE,
        "project_id": _PROJECT,
        "name": "Coding Environment",
        "config": {"runtime": "e2b", "role": "user", "sandbox_id": None},
        "status": "pending",
        "status_detail": None,
        "tool_policy": "ask",
        "position_x": 0.0,
        "position_y": 0.0,
    }
    base.update(over)
    return EnvNode(**base)


def _replace(node: EnvNode, **over) -> EnvNode:
    fields = {
        "id": node.id,
        "project_id": node.project_id,
        "name": node.name,
        "config": node.config,
        "status": node.status,
        "status_detail": node.status_detail,
        "tool_policy": node.tool_policy,
        "position_x": node.position_x,
        "position_y": node.position_y,
    }
    fields.update(over)
    return EnvNode(**fields)


class _FakeEnvRepo:
    """Holds one node. Records every write in order."""

    def __init__(self, node: EnvNode, *, claim_succeeds: bool = True):
        self.node = node
        self.claim_succeeds = claim_succeeds
        self.writes: list[tuple] = []

    def get_environment_nodes(self, ids):
        return [n for n in map(self.get_environment_node, ids) if n is not None]

    def get_environment_node(self, node_id: str) -> EnvNode | None:
        return self.node if node_id == self.node.id else None

    def set_status(self, node_id: str, status: str, detail: str | None) -> None:
        self.writes.append(("status", status, detail))
        self.node = _replace(self.node, status=status, status_detail=detail)

    def set_config(self, node_id: str, config: dict) -> None:
        self.writes.append(("config", config.get("sandbox_id")))
        self.node = _replace(self.node, config=config)

    def try_begin_provisioning(self, node_id: str) -> bool:
        self.writes.append(("claim", self.claim_succeeds))
        if self.claim_succeeds:
            self.node = _replace(self.node, status="provisioning", status_detail=None)
        return self.claim_succeeds


def _spec(
    monkeypatch,
    *,
    provision_id: str = "sbx_new",
    provision_error: Exception | None = None,
    verify_ok: bool = True,
    verify_detail: str = "Sandbox running",
    teardown_error: Exception | None = None,
) -> dict:
    """Install a fake EnvSpec and return a record of what it was asked to do."""
    calls: dict = {"provision": 0, "verify": 0, "teardown": []}

    async def _provision(ctx):
        calls["provision"] += 1
        if provision_error is not None:
            raise provision_error
        return provision_id

    async def _verify(ctx):
        calls["verify"] += 1
        return VerifyResult(ok=verify_ok, detail=verify_detail)

    async def _teardown(sandbox_id):
        calls["teardown"].append(sandbox_id)
        if teardown_error is not None:
            raise teardown_error

    spec = EnvSpec(
        runtime="e2b",
        provision=_provision,
        build=lambda ctx: None,
        verify=_verify,
        teardown=_teardown,
    )
    monkeypatch.setattr(lifecycle, "get_spec", lambda runtime: spec if runtime == "e2b" else None)
    return calls


# -- ensure_provisioned ------------------------------------------------------


@pytest.mark.anyio
async def test_ensure_provisioned_creates_a_sandbox_from_pending(monkeypatch):
    repo = _FakeEnvRepo(_node())
    calls = _spec(monkeypatch)

    result = await lifecycle.ensure_provisioned(repo, repo.node)

    assert calls["provision"] == 1
    assert result.status == "ready"
    assert result.sandbox_id == "sbx_new"
    # The claim comes before provisioning, the id before the ready status.
    assert repo.writes == [
        ("claim", True),
        ("config", "sbx_new"),
        ("status", "ready", "Sandbox running"),
    ]


@pytest.mark.anyio
async def test_ensure_provisioned_is_a_no_op_when_already_ready(monkeypatch):
    repo = _FakeEnvRepo(_node(status="ready", config={"runtime": "e2b", "sandbox_id": "sbx_1"}))
    calls = _spec(monkeypatch)

    result = await lifecycle.ensure_provisioned(repo, repo.node)

    assert calls["provision"] == 0
    assert repo.writes == []
    assert result.sandbox_id == "sbx_1"


@pytest.mark.anyio
async def test_ensure_provisioned_reprovisions_a_ready_node_with_no_sandbox(monkeypatch):
    """ready without an id is incoherent; treat it as needing a sandbox."""
    repo = _FakeEnvRepo(_node(status="ready"))
    calls = _spec(monkeypatch)

    result = await lifecycle.ensure_provisioned(repo, repo.node)

    assert calls["provision"] == 1
    assert result.status == "ready"
    assert result.sandbox_id == "sbx_new"


@pytest.mark.anyio
async def test_ensure_provisioned_leaves_a_stopped_node_alone(monkeypatch):
    """Stopping is explicit. A turn must not silently restart it."""
    repo = _FakeEnvRepo(_node(status="stopped"))
    calls = _spec(monkeypatch)

    result = await lifecycle.ensure_provisioned(repo, repo.node)

    assert calls["provision"] == 0
    assert repo.writes == []
    assert result.status == "stopped"


@pytest.mark.anyio
async def test_ensure_provisioned_force_restarts_a_stopped_node(monkeypatch):
    """POST /start is the user's deliberate act, so it may rebuild."""
    repo = _FakeEnvRepo(_node(status="stopped"))
    calls = _spec(monkeypatch)

    result = await lifecycle.ensure_provisioned(repo, repo.node, force=True)

    assert calls["provision"] == 1
    assert result.status == "ready"
    assert result.sandbox_id == "sbx_new"


@pytest.mark.anyio
async def test_ensure_provisioned_force_does_not_bypass_the_claim(monkeypatch):
    """force skips the early return, never the compare and set."""
    repo = _FakeEnvRepo(_node(status="stopped"), claim_succeeds=False)
    calls = _spec(monkeypatch)

    await lifecycle.ensure_provisioned(repo, repo.node, force=True)

    assert calls["provision"] == 0
    assert repo.writes == [("claim", False)]


@pytest.mark.anyio
async def test_ensure_provisioned_force_still_skips_a_ready_node(monkeypatch):
    """force is about stopped nodes, not about paying for a second sandbox."""
    repo = _FakeEnvRepo(_node(status="ready", config={"runtime": "e2b", "sandbox_id": "sbx_1"}))
    calls = _spec(monkeypatch)

    result = await lifecycle.ensure_provisioned(repo, repo.node, force=True)

    assert calls["provision"] == 0
    assert result.sandbox_id == "sbx_1"


@pytest.mark.anyio
async def test_ensure_provisioned_leaves_a_provisioning_node_alone(monkeypatch):
    """Someone else is already on it."""
    repo = _FakeEnvRepo(_node(status="provisioning"))
    calls = _spec(monkeypatch)

    result = await lifecycle.ensure_provisioned(repo, repo.node)

    assert calls["provision"] == 0
    assert result.status == "provisioning"


@pytest.mark.anyio
async def test_ensure_provisioned_loser_of_the_race_does_not_provision(monkeypatch):
    """Two turns reach a pending node at once; only one sandbox is created."""
    repo = _FakeEnvRepo(_node(), claim_succeeds=False)
    calls = _spec(monkeypatch)

    await lifecycle.ensure_provisioned(repo, repo.node)

    assert calls["provision"] == 0
    assert repo.writes == [("claim", False)]


@pytest.mark.anyio
async def test_ensure_provisioned_records_a_provision_failure(monkeypatch):
    repo = _FakeEnvRepo(_node())
    _spec(monkeypatch, provision_error=RuntimeError("E2B_API_KEY is not configured"))

    result = await lifecycle.ensure_provisioned(repo, repo.node)

    assert result.status == "error"
    assert "RuntimeError" in (result.status_detail or "")
    assert "E2B_API_KEY" in (result.status_detail or "")


@pytest.mark.anyio
async def test_ensure_provisioned_caps_the_error_detail(monkeypatch):
    repo = _FakeEnvRepo(_node())
    _spec(monkeypatch, provision_error=RuntimeError("x" * 2000))

    result = await lifecycle.ensure_provisioned(repo, repo.node)

    assert len(result.status_detail or "") <= 500


@pytest.mark.anyio
async def test_ensure_provisioned_reuses_a_live_sandbox_on_an_errored_node(monkeypatch):
    """An errored node whose sandbox is actually alive is healed, not replaced."""
    repo = _FakeEnvRepo(_node(status="error", config={"runtime": "e2b", "sandbox_id": "sbx_old"}))
    calls = _spec(monkeypatch, verify_ok=True)

    result = await lifecycle.ensure_provisioned(repo, repo.node)

    assert calls["verify"] == 1
    assert calls["provision"] == 0
    assert calls["teardown"] == []
    assert result.status == "ready"
    assert result.sandbox_id == "sbx_old"


@pytest.mark.anyio
async def test_ensure_provisioned_replaces_a_dead_sandbox_on_an_errored_node(monkeypatch):
    repo = _FakeEnvRepo(_node(status="error", config={"runtime": "e2b", "sandbox_id": "sbx_dead"}))
    calls = _spec(monkeypatch, verify_ok=False, verify_detail="Sandbox not found.")

    result = await lifecycle.ensure_provisioned(repo, repo.node)

    assert calls["verify"] == 1
    assert calls["teardown"] == ["sbx_dead"]
    assert calls["provision"] == 1
    assert result.status == "ready"
    assert result.sandbox_id == "sbx_new"


@pytest.mark.anyio
async def test_ensure_provisioned_survives_a_teardown_failure(monkeypatch):
    """A dead sandbox we cannot kill must not block making a new one."""
    repo = _FakeEnvRepo(_node(status="error", config={"runtime": "e2b", "sandbox_id": "sbx_dead"}))
    calls = _spec(
        monkeypatch,
        verify_ok=False,
        teardown_error=ConnectionError("network down"),
    )

    result = await lifecycle.ensure_provisioned(repo, repo.node)

    assert calls["provision"] == 1
    assert result.status == "ready"


@pytest.mark.anyio
async def test_ensure_provisioned_rejects_an_unknown_runtime(monkeypatch):
    repo = _FakeEnvRepo(_node(config={"runtime": "local", "role": "user"}))
    _spec(monkeypatch)

    result = await lifecycle.ensure_provisioned(repo, repo.node)

    assert result.status == "error"
    assert "local" in (result.status_detail or "")


# -- stop --------------------------------------------------------------------


@pytest.mark.anyio
async def test_stop_kills_the_sandbox_and_clears_the_id(monkeypatch):
    repo = _FakeEnvRepo(_node(status="ready", config={"runtime": "e2b", "sandbox_id": "sbx_1"}))
    calls = _spec(monkeypatch)

    result = await lifecycle.stop(repo, repo.node)

    assert calls["teardown"] == ["sbx_1"]
    assert result.status == "stopped"
    assert result.sandbox_id is None


@pytest.mark.anyio
async def test_stop_writes_status_before_clearing_the_id(monkeypatch):
    """A crash between the two writes must not leave ready with a null id."""
    repo = _FakeEnvRepo(_node(status="ready", config={"runtime": "e2b", "sandbox_id": "sbx_1"}))
    _spec(monkeypatch)

    await lifecycle.stop(repo, repo.node)

    kinds = [w[0] for w in repo.writes]
    assert kinds.index("status") < kinds.index("config")


@pytest.mark.anyio
async def test_stop_on_a_node_with_no_sandbox_still_marks_it_stopped(monkeypatch):
    repo = _FakeEnvRepo(_node(status="error"))
    calls = _spec(monkeypatch)

    result = await lifecycle.stop(repo, repo.node)

    assert calls["teardown"] == []
    assert result.status == "stopped"


@pytest.mark.anyio
async def test_stop_survives_a_teardown_failure(monkeypatch):
    """The user asked to stop. Record it even if E2B is unreachable."""
    repo = _FakeEnvRepo(_node(status="ready", config={"runtime": "e2b", "sandbox_id": "sbx_1"}))
    _spec(monkeypatch, teardown_error=ConnectionError("network down"))

    result = await lifecycle.stop(repo, repo.node)

    assert result.status == "stopped"
    assert result.sandbox_id is None


# -- teardown ----------------------------------------------------------------


@pytest.mark.anyio
async def test_teardown_kills_without_writing_status(monkeypatch):
    """The row is about to be deleted; a status write would be pointless."""
    repo = _FakeEnvRepo(_node(status="ready", config={"runtime": "e2b", "sandbox_id": "sbx_1"}))
    calls = _spec(monkeypatch)

    await lifecycle.teardown(repo, repo.node)

    assert calls["teardown"] == ["sbx_1"]
    assert repo.writes == []


@pytest.mark.anyio
async def test_teardown_never_raises(monkeypatch):
    """A delete must not fail because E2B is down. The sweep is the backstop."""
    repo = _FakeEnvRepo(_node(status="ready", config={"runtime": "e2b", "sandbox_id": "sbx_1"}))
    _spec(monkeypatch, teardown_error=ConnectionError("network down"))

    await lifecycle.teardown(repo, repo.node)


@pytest.mark.anyio
async def test_teardown_with_no_sandbox_does_nothing(monkeypatch):
    repo = _FakeEnvRepo(_node())
    calls = _spec(monkeypatch)

    await lifecycle.teardown(repo, repo.node)

    assert calls["teardown"] == []


@pytest.mark.anyio
async def test_teardown_with_an_unknown_runtime_does_nothing(monkeypatch):
    repo = _FakeEnvRepo(_node(config={"runtime": "local", "sandbox_id": "sbx_1"}))
    calls = _spec(monkeypatch)

    await lifecycle.teardown(repo, repo.node)

    assert calls["teardown"] == []


# -- verify ------------------------------------------------------------------


@pytest.mark.anyio
async def test_verify_marks_a_live_sandbox_ready(monkeypatch):
    repo = _FakeEnvRepo(_node(status="error", config={"runtime": "e2b", "sandbox_id": "sbx_1"}))
    _spec(monkeypatch, verify_ok=True)

    result = await lifecycle.verify(repo, repo.node)

    assert result.status == "ready"
    assert result.status_detail == "Sandbox running"


@pytest.mark.anyio
async def test_verify_marks_a_dead_sandbox_error(monkeypatch):
    repo = _FakeEnvRepo(_node(status="ready", config={"runtime": "e2b", "sandbox_id": "sbx_1"}))
    _spec(monkeypatch, verify_ok=False, verify_detail="Sandbox not found.")

    result = await lifecycle.verify(repo, repo.node)

    assert result.status == "error"
    assert "not found" in (result.status_detail or "").lower()


@pytest.mark.anyio
async def test_verify_rescues_a_node_stranded_in_provisioning(monkeypatch):
    """A restart mid-provision leaves provisioning with no id. Verify is the way out."""
    repo = _FakeEnvRepo(_node(status="provisioning"))
    calls = _spec(monkeypatch)

    result = await lifecycle.verify(repo, repo.node)

    assert calls["verify"] == 0
    assert result.status == "error"
    assert "did not complete" in (result.status_detail or "").lower()


@pytest.mark.anyio
async def test_verify_rejects_an_unknown_runtime(monkeypatch):
    repo = _FakeEnvRepo(_node(config={"runtime": "local", "sandbox_id": "sbx_1"}))
    _spec(monkeypatch)

    result = await lifecycle.verify(repo, repo.node)

    assert result.status == "error"
    assert "local" in (result.status_detail or "")


@pytest.mark.anyio
async def test_verify_leaves_a_stopped_node_stopped(monkeypatch):
    """Overwriting stopped with error would defeat the no-restart guard.

    Regression: verify wrote 'error' for a stopped node because it has no
    sandbox id, and ensure_provisioned then saw error rather than stopped and
    paid for a new sandbox.
    """
    repo = _FakeEnvRepo(_node(status="stopped"))
    calls = _spec(monkeypatch)

    result = await lifecycle.verify(repo, repo.node)

    assert calls["verify"] == 0
    assert result.status == "stopped"


@pytest.mark.anyio
async def test_a_verified_stopped_node_is_still_not_restarted_by_a_turn(monkeypatch):
    """The two functions composed: verify then a turn must not provision."""
    repo = _FakeEnvRepo(_node(status="stopped"))
    calls = _spec(monkeypatch)

    verified = await lifecycle.verify(repo, repo.node)
    result = await lifecycle.ensure_provisioned(repo, verified)

    assert calls["provision"] == 0
    assert result.status == "stopped"
