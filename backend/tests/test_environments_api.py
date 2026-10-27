"""The environment lifecycle endpoints.

Real routes, fake repositories, faked lifecycle. No E2B and no database.

No ``import pytest``: every test here is synchronous and takes only the
``client`` and ``monkeypatch`` fixtures, which pytest injects by name.
"""

from e2b import FileType

from app.environments.base import WORKSPACE_ROOT
from app.main import app
from app.repositories.environment_repo import EnvNode
from app.repositories.project_repo import Project
from app.routers import environments as env_router
from app.routers.auth import AuthContext, UserResponse, get_auth_context
from app.routers.deps import (
    get_environment_repository,
    get_project_repository,
    get_tool_repository,
    get_turn_repositories,
)

_PROJECT_ID = "11111111-1111-1111-1111-111111111111"
_ENV_ID = "22222222-2222-2222-2222-222222222222"
_USER_ID = "33333333-3333-3333-3333-333333333333"
_OTHER_PROJECT = "44444444-4444-4444-4444-444444444444"
_TURN_REPOS = object()  # PATCH needs turn repos only to resume on auto


def _override_auth():
    return AuthContext(user=UserResponse(id=_USER_ID, email="t@example.com"), token="tok")


def _node(**over) -> EnvNode:
    base = {
        "id": _ENV_ID,
        "project_id": _PROJECT_ID,
        "name": "Coding Environment",
        "config": {
            "runtime": "e2b",
            "role": "user",
            "sandbox_id": "sbx_1",
            "template": "base",
            "idle_timeout_s": 300,
            "preview_ports": [],
        },
        "status": "ready",
        "status_detail": "Sandbox running",
        "tool_policy": "ask",
        "position_x": 10.0,
        "position_y": 20.0,
    }
    base.update(over)
    return EnvNode(**base)


class _FakeEnvRepo:
    def __init__(self, node: EnvNode | None = None):
        self.node = node
        self.created: list[dict] = []
        self.updates: list[dict] = []
        self.status_writes: list[tuple] = []

    def get_environment_nodes(self, ids):
        return [n for n in map(self.get_environment_node, ids) if n is not None]

    def get_environment_node(self, node_id: str):
        return self.node if self.node and node_id == self.node.id else None

    def set_status(self, node_id: str, status: str, detail: str | None) -> None:
        self.status_writes.append((node_id, status, detail))

    def list_environment_nodes(self, project_id: str):
        return [self.node] if self.node else []

    def create_environment_node(
        self, project_id, name, config, *, tool_policy="ask", position_x=0.0, position_y=0.0
    ):
        self.created.append(
            {"project_id": project_id, "name": name, "config": config, "tool_policy": tool_policy}
        )
        self.node = EnvNode(
            id=_ENV_ID,
            project_id=project_id,
            name=name,
            config=config,
            status="pending",
            status_detail=None,
            tool_policy=tool_policy,
            position_x=position_x,
            position_y=position_y,
        )
        return _ENV_ID

    def update_environment_node(self, node_id: str, changes: dict):
        if self.node is None or node_id != self.node.id:
            return None
        self.updates.append(changes)
        allowed = {"name", "position_x", "position_y", "tool_policy"}
        payload = {k: v for k, v in changes.items() if k in allowed and v is not None}
        fields = {
            "id": self.node.id,
            "project_id": self.node.project_id,
            "name": self.node.name,
            "config": self.node.config,
            "status": self.node.status,
            "status_detail": self.node.status_detail,
            "tool_policy": self.node.tool_policy,
            "position_x": self.node.position_x,
            "position_y": self.node.position_y,
        }
        fields.update(payload)
        self.node = EnvNode(**fields)
        return self.node

    def ensure_scratch_node(self, project_id: str, new_project: bool = False):
        return self.node


class _FakeChatRepo:
    def get_project(self, project_id: str):
        return Project(id=project_id, name="Test Project")

    def get_conversation_for_node(self, node_id: str) -> str | None:
        return None


def _use(env_repo, chat_repo=None):
    app.dependency_overrides[get_auth_context] = _override_auth
    app.dependency_overrides[get_environment_repository] = lambda: env_repo
    app.dependency_overrides[get_project_repository] = lambda: chat_repo or _FakeChatRepo()
    app.dependency_overrides[get_tool_repository] = lambda: object()
    app.dependency_overrides[get_turn_repositories] = lambda: _TURN_REPOS


def _fake_lifecycle(monkeypatch, **returns):
    """Record lifecycle calls and return whatever each was told to."""
    calls: dict = {"ensure": [], "stop": [], "verify": [], "teardown": []}

    async def _ensure(env_repo, node, *, force=False):
        calls["ensure"].append({"node_id": node.id, "force": force})
        return returns.get("ensure", node)

    async def _stop(env_repo, node):
        calls["stop"].append(node.id)
        return returns.get("stop", node)

    async def _verify(env_repo, node):
        calls["verify"].append(node.id)
        return returns.get("verify", node)

    async def _teardown(env_repo, node):
        calls["teardown"].append(node.id)

    monkeypatch.setattr(env_router.lifecycle, "ensure_provisioned", _ensure)
    monkeypatch.setattr(env_router.lifecycle, "stop", _stop)
    monkeypatch.setattr(env_router.lifecycle, "verify", _verify)
    monkeypatch.setattr(env_router.lifecycle, "teardown", _teardown)
    return calls


# -- auth --------------------------------------------------------------------


def test_every_endpoint_requires_auth(client):
    base = f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}"
    assert client.get(base).status_code == 401
    assert client.patch(base, json={"name": "x"}).status_code == 401
    assert client.post(f"{base}/start").status_code == 401
    assert client.post(f"{base}/stop").status_code == 401
    assert client.post(f"{base}/verify").status_code == 401


# -- GET ---------------------------------------------------------------------


def test_get_returns_the_environment(client):
    _use(_FakeEnvRepo(_node()))
    try:
        response = client.get(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == _ENV_ID
    assert body["kind"] == "environment"
    assert body["runtime"] == "e2b"
    assert body["role"] == "user"
    assert body["status"] == "ready"
    assert body["sandbox_id"] == "sbx_1"
    assert body["tool_policy"] == "ask"


def test_get_missing_is_404(client):
    _use(_FakeEnvRepo(None))
    try:
        response = client.get(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Environment not found"


def test_get_from_the_wrong_project_is_404(client):
    """A node id from another canvas must not resolve here."""
    _use(_FakeEnvRepo(_node()))
    try:
        response = client.get(f"/projects/{_OTHER_PROJECT}/environments/{_ENV_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


# -- PATCH -------------------------------------------------------------------


def test_patch_updates_name_and_policy(client, monkeypatch):
    resumed = []
    monkeypatch.setattr(
        env_router, "resume_waiting", lambda repos, *, env_id: resumed.append((repos, env_id))
    )
    repo = _FakeEnvRepo(_node())
    _use(repo)
    try:
        response = client.patch(
            f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}",
            json={"name": "Renamed", "tool_policy": "auto"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    assert response.json()["tool_policy"] == "auto"
    # Flipping to auto resumes turns parked on this environment.
    assert resumed == [(_TURN_REPOS, _ENV_ID)]


def test_patch_rejects_an_unknown_tool_policy(client):
    _use(_FakeEnvRepo(_node()))
    try:
        response = client.patch(
            f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}",
            json={"tool_policy": "whenever"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_patch_missing_is_404(client):
    _use(_FakeEnvRepo(None))
    try:
        response = client.patch(
            f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}", json={"name": "x"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


# -- start -------------------------------------------------------------------


def test_start_forces_provisioning(client, monkeypatch):
    """force is what lets Start restart a stopped node; a turn cannot."""
    stopped = _node(status="stopped", config={"runtime": "e2b", "role": "user"})
    started = _node(status="ready")
    repo = _FakeEnvRepo(stopped)
    calls = _fake_lifecycle(monkeypatch, ensure=started)
    _use(repo)
    try:
        response = client.post(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/start")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert calls["ensure"] == [{"node_id": _ENV_ID, "force": True}]


def test_start_reports_a_failure_as_a_status_not_an_error(client, monkeypatch):
    """The client reads status and status_detail; the call itself succeeded."""
    failed = _node(status="error", status_detail="RuntimeError: no key")
    repo = _FakeEnvRepo(_node(status="pending"))
    _fake_lifecycle(monkeypatch, ensure=failed)
    _use(repo)
    try:
        response = client.post(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/start")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert "no key" in response.json()["status_detail"]


def test_start_missing_is_404(client, monkeypatch):
    _fake_lifecycle(monkeypatch)
    _use(_FakeEnvRepo(None))
    try:
        response = client.post(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/start")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


# -- stop --------------------------------------------------------------------


def test_stop_kills_and_reports_stopped(client, monkeypatch):
    stopped = _node(status="stopped", config={"runtime": "e2b", "role": "user"})
    repo = _FakeEnvRepo(_node())
    calls = _fake_lifecycle(monkeypatch, stop=stopped)
    _use(repo)
    try:
        response = client.post(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/stop")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "stopped"
    assert response.json()["sandbox_id"] is None
    assert calls["stop"] == [_ENV_ID]


def test_stop_while_provisioning_is_409(client, monkeypatch):
    """Killing a half created sandbox would leak it: its id is not written yet."""
    repo = _FakeEnvRepo(_node(status="provisioning", config={"runtime": "e2b", "role": "user"}))
    calls = _fake_lifecycle(monkeypatch)
    _use(repo)
    try:
        response = client.post(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/stop")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "provisioning" in response.json()["detail"].lower()
    assert calls["stop"] == []


def test_stop_an_already_stopped_node_is_fine(client, monkeypatch):
    """Idempotent: the user clicking twice is not an error."""
    stopped = _node(status="stopped", config={"runtime": "e2b", "role": "user"})
    repo = _FakeEnvRepo(stopped)
    _fake_lifecycle(monkeypatch, stop=stopped)
    _use(repo)
    try:
        response = client.post(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/stop")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


# -- verify ------------------------------------------------------------------


def test_verify_reports_the_checked_status(client, monkeypatch):
    checked = _node(status="error", status_detail="Sandbox not found.")
    repo = _FakeEnvRepo(_node())
    calls = _fake_lifecycle(monkeypatch, verify=checked)
    _use(repo)
    try:
        response = client.post(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/verify")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert calls["verify"] == [_ENV_ID]


# -- creation ----------------------------------------------------------------


def test_create_an_environment_node(client):
    repo = _FakeEnvRepo(None)
    _use(repo)
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={"kind": "environment", "name": "Build Box"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "environment"
    assert body["name"] == "Build Box"
    assert body["role"] == "user"
    assert body["runtime"] == "e2b"
    assert body["status"] == "pending"
    # Not provisioned on create: Start or the first turn does that.
    assert body["sandbox_id"] is None


def test_create_defaults_the_name(client):
    repo = _FakeEnvRepo(None)
    _use(repo)
    try:
        response = client.post(f"/projects/{_PROJECT_ID}/nodes", json={"kind": "environment"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["name"] == "Environment"


def test_create_rejects_a_client_supplied_role(client):
    """Only the backend makes a scratch space; a client cannot claim to be one."""
    repo = _FakeEnvRepo(None)
    _use(repo)
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={"kind": "environment", "config": {"role": "scratch"}},
        )
    finally:
        app.dependency_overrides.clear()

    # role is not an accepted config key, so this is a rejected unknown field.
    assert response.status_code == 422
    assert "role" in response.json()["detail"]


def test_create_rejects_unknown_config_keys(client):
    repo = _FakeEnvRepo(None)
    _use(repo)
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={"kind": "environment", "config": {"sandbox_id": "sbx_stolen"}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "sandbox_id" in response.json()["detail"]


def test_create_accepts_the_documented_config_keys(client):
    repo = _FakeEnvRepo(None)
    _use(repo)
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={
                "kind": "environment",
                "config": {
                    "template": "custom",
                    "idle_timeout_s": 900,
                    "preview_ports": [3000, 5173],
                    "description": "the API repo",
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["template"] == "custom"
    assert body["idle_timeout_s"] == 900
    assert body["preview_ports"] == [3000, 5173]
    assert body["description"] == "the API repo"


def test_create_rejects_an_out_of_range_idle_timeout(client):
    repo = _FakeEnvRepo(None)
    _use(repo)
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={"kind": "environment", "config": {"idle_timeout_s": 5}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_create_rejects_a_bad_preview_port(client):
    repo = _FakeEnvRepo(None)
    _use(repo)
    try:
        response = client.post(
            f"/projects/{_PROJECT_ID}/nodes",
            json={"kind": "environment", "config": {"preview_ports": [99999]}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


# -- delete hooks ------------------------------------------------------------


def test_deleting_an_environment_node_tears_down_its_sandbox(client, monkeypatch):
    repo = _FakeEnvRepo(_node())
    calls = _fake_lifecycle(monkeypatch)

    class _ChatRepoWithDelete(_FakeChatRepo):
        def __init__(self):
            self.deleted: str | None = None

        def delete_node(self, node_id):
            self.deleted = node_id
            return [node_id]

    chat_repo = _ChatRepoWithDelete()
    _use(repo, chat_repo)
    try:
        response = client.delete(f"/projects/{_PROJECT_ID}/nodes/{_ENV_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert calls["teardown"] == [_ENV_ID]
    assert chat_repo.deleted == _ENV_ID


def test_deleting_a_non_environment_node_skips_teardown(client, monkeypatch):
    repo = _FakeEnvRepo(None)
    calls = _fake_lifecycle(monkeypatch)

    class _ChatRepoWithDelete(_FakeChatRepo):
        def delete_node(self, node_id):
            return [node_id]

    _use(repo, _ChatRepoWithDelete())
    try:
        response = client.delete(f"/projects/{_PROJECT_ID}/nodes/{_ENV_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert calls["teardown"] == []


def test_deleting_a_project_tears_down_every_environment(client, monkeypatch):
    repo = _FakeEnvRepo(_node())
    calls = _fake_lifecycle(monkeypatch)

    class _ChatRepoWithDelete(_FakeChatRepo):
        def delete_project(self, project_id):
            return True

    _use(repo, _ChatRepoWithDelete())
    try:
        response = client.delete(f"/projects/{_PROJECT_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert calls["teardown"] == [_ENV_ID]


# -- files, content and preview ----------------------------------------------


class _FakeEntry:
    """Stands in for e2b.EntryInfo. Only the fields the router reads.

    ``type`` is a real FileType member, matching e2b.EntryInfo.type exactly:
    the router looks it up in a dict keyed by FileType, not by string.
    """

    def __init__(self, name, type_: FileType, path, size=0):
        self.name = name
        self.type = type_
        self.path = path
        self.size = size


class _FakeFiles:
    def __init__(self, sandbox):
        self._s = sandbox

    async def list(self, path, depth=1, **_k):
        self._s.listed.append(path)
        if self._s.raise_on_list is not None:
            raise self._s.raise_on_list
        return self._s.entries

    async def read(self, path, **_k):
        self._s.read_paths.append(path)
        if self._s.raise_on_read is not None:
            raise self._s.raise_on_read
        return self._s.content


class _FakeSandbox:
    def __init__(self, sandbox_id="sbx_1"):
        self.sandbox_id = sandbox_id
        self.entries: list = []
        self.content = ""
        self.listed: list[str] = []
        self.read_paths: list[str] = []
        self.raise_on_list: Exception | None = None
        self.raise_on_read: Exception | None = None
        self.files = _FakeFiles(self)

    def get_host(self, port: int) -> str:
        return f"{port}-{self.sandbox_id}.e2b.app"


def _use_sandbox(monkeypatch, sandbox=None, connect_error=None):
    """Patch e2b.connect as the router imports it."""

    async def _connect(ctx):
        if connect_error is not None:
            raise connect_error
        return sandbox

    monkeypatch.setattr(env_router.e2b, "connect", _connect)
    return sandbox


# -- guards ------------------------------------------------------------------


def test_files_on_a_pending_environment_is_409(client, monkeypatch):
    """Nothing to browse before the sandbox exists."""
    repo = _FakeEnvRepo(_node(status="pending", config={"runtime": "e2b", "role": "user"}))
    _use_sandbox(monkeypatch, _FakeSandbox())
    _use(repo)
    try:
        response = client.get(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/files")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "pending" in response.json()["detail"].lower()


def test_files_on_a_stopped_environment_names_the_status(client, monkeypatch):
    repo = _FakeEnvRepo(_node(status="stopped", config={"runtime": "e2b", "role": "user"}))
    _use_sandbox(monkeypatch, _FakeSandbox())
    _use(repo)
    try:
        response = client.get(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/files")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "stopped" in response.json()["detail"].lower()


def test_files_when_the_sandbox_is_unreachable_is_502(client, monkeypatch):
    repo = _FakeEnvRepo(_node())
    _use_sandbox(monkeypatch, connect_error=ConnectionError("network down"))
    _use(repo)
    try:
        response = client.get(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/files")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert "unreachable" in response.json()["detail"].lower()


def test_an_unreachable_sandbox_is_marked_errored(client, monkeypatch):
    """The canvas should show the failure, not wait for the next turn."""
    repo = _FakeEnvRepo(_node())
    _use_sandbox(monkeypatch, connect_error=ConnectionError("network down"))
    _use(repo)
    try:
        client.get(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/files")
    finally:
        app.dependency_overrides.clear()

    assert repo.status_writes
    assert repo.status_writes[-1][1] == "error"


def test_files_requires_auth(client):
    base = f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}"
    assert client.get(f"{base}/files").status_code == 401
    assert client.get(f"{base}/files/content?path=x").status_code == 401
    assert client.get(f"{base}/preview?port=3000").status_code == 401


# -- listing -----------------------------------------------------------------


def test_files_lists_entries_with_their_kind(client, monkeypatch):
    sandbox = _FakeSandbox()
    sandbox.entries = [
        _FakeEntry("app", FileType.DIR, "/home/user/workspace/app"),
        _FakeEntry("notes.md", FileType.FILE, "/home/user/workspace/notes.md", size=42),
        _FakeEntry("link", FileType.SYMLINK, "/home/user/workspace/link"),
    ]
    repo = _FakeEnvRepo(_node())
    _use_sandbox(monkeypatch, sandbox)
    _use(repo)
    try:
        response = client.get(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/files")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    by_name = {e["name"]: e for e in body["entries"]}
    assert by_name["app"]["type"] == "dir"
    assert by_name["notes.md"]["type"] == "file"
    assert by_name["notes.md"]["size"] == 42
    # A symlink is its own kind: calling it a file would mislead the tree.
    assert by_name["link"]["type"] == "symlink"


def test_files_defaults_to_the_workspace_root(client, monkeypatch):
    sandbox = _FakeSandbox()
    repo = _FakeEnvRepo(_node())
    _use_sandbox(monkeypatch, sandbox)
    _use(repo)
    try:
        client.get(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/files")
    finally:
        app.dependency_overrides.clear()

    assert sandbox.listed == [WORKSPACE_ROOT]


def test_files_normalises_the_requested_path(client, monkeypatch):
    sandbox = _FakeSandbox()
    repo = _FakeEnvRepo(_node())
    _use_sandbox(monkeypatch, sandbox)
    _use(repo)
    try:
        client.get(
            f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/files",
            params={"path": "/home/user/workspace/app/../app"},
        )
    finally:
        app.dependency_overrides.clear()

    assert sandbox.listed == ["/home/user/workspace/app"]


def test_files_missing_directory_is_404(client, monkeypatch):
    from e2b import FileNotFoundException

    sandbox = _FakeSandbox()
    sandbox.raise_on_list = FileNotFoundException("nope")
    repo = _FakeEnvRepo(_node())
    _use_sandbox(monkeypatch, sandbox)
    _use(repo)
    try:
        response = client.get(
            f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/files",
            params={"path": "/nowhere"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_files_rejects_a_null_byte_in_the_path(client, monkeypatch):
    sandbox = _FakeSandbox()
    repo = _FakeEnvRepo(_node())
    _use_sandbox(monkeypatch, sandbox)
    _use(repo)
    try:
        response = client.get(
            f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/files",
            params={"path": "/tmp/a\x00b"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert sandbox.listed == []


# -- content -----------------------------------------------------------------


def test_content_returns_the_file(client, monkeypatch):
    sandbox = _FakeSandbox()
    sandbox.content = "hello world"
    repo = _FakeEnvRepo(_node())
    _use_sandbox(monkeypatch, sandbox)
    _use(repo)
    try:
        response = client.get(
            f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/files/content",
            params={"path": "notes.md"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "hello world"
    assert body["truncated"] is False


def test_content_truncates_a_large_file(client, monkeypatch):
    from app.config import settings

    sandbox = _FakeSandbox()
    sandbox.content = "x" * (settings.environment_max_file_chars + 500)
    repo = _FakeEnvRepo(_node())
    _use_sandbox(monkeypatch, sandbox)
    _use(repo)
    try:
        response = client.get(
            f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/files/content",
            params={"path": "big.txt"},
        )
    finally:
        app.dependency_overrides.clear()

    body = response.json()
    assert body["truncated"] is True
    assert len(body["content"]) == settings.environment_max_file_chars


def test_content_missing_file_is_404(client, monkeypatch):
    from e2b import FileNotFoundException

    sandbox = _FakeSandbox()
    sandbox.raise_on_read = FileNotFoundException("nope")
    repo = _FakeEnvRepo(_node())
    _use_sandbox(monkeypatch, sandbox)
    _use(repo)
    try:
        response = client.get(
            f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/files/content",
            params={"path": "ghost.md"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_content_of_a_binary_file_is_415(client, monkeypatch):
    """A tree view cannot render bytes; say so rather than returning mojibake."""
    sandbox = _FakeSandbox()
    sandbox.raise_on_read = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
    repo = _FakeEnvRepo(_node())
    _use_sandbox(monkeypatch, sandbox)
    _use(repo)
    try:
        response = client.get(
            f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/files/content",
            params={"path": "image.png"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 415
    assert "binary" in response.json()["detail"].lower()


def test_content_requires_a_path(client, monkeypatch):
    repo = _FakeEnvRepo(_node())
    _use_sandbox(monkeypatch, _FakeSandbox())
    _use(repo)
    try:
        response = client.get(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/files/content")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


# -- preview -----------------------------------------------------------------


def test_preview_returns_an_https_url(client, monkeypatch):
    sandbox = _FakeSandbox("sbx_abc")
    repo = _FakeEnvRepo(_node())
    _use_sandbox(monkeypatch, sandbox)
    _use(repo)
    try:
        response = client.get(
            f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/preview",
            params={"port": 3000},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["url"] == "https://3000-sbx_abc.e2b.app"
    assert response.json()["port"] == 3000


def test_preview_rejects_an_out_of_range_port(client, monkeypatch):
    repo = _FakeEnvRepo(_node())
    _use_sandbox(monkeypatch, _FakeSandbox())
    _use(repo)
    try:
        low = client.get(
            f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/preview", params={"port": 0}
        )
        high = client.get(
            f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/preview", params={"port": 70000}
        )
    finally:
        app.dependency_overrides.clear()

    assert low.status_code == 422
    assert high.status_code == 422


def test_preview_on_a_stopped_environment_is_409(client, monkeypatch):
    repo = _FakeEnvRepo(_node(status="stopped", config={"runtime": "e2b", "role": "user"}))
    _use_sandbox(monkeypatch, _FakeSandbox())
    _use(repo)
    try:
        response = client.get(
            f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/preview",
            params={"port": 3000},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409


# -- previews registry -------------------------------------------------------


class _FakePreviewRepo:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.deleted: list[tuple] = []

    def list_for_env(self, env_node_id):
        return sorted(self.rows, key=lambda r: r.created_at, reverse=True)

    def delete(self, env_node_id, port):
        self.deleted.append((env_node_id, port))


def _prow(port, title, created_at="2025-01-01T00:00:00+00:00"):
    from app.repositories.preview_repo import PreviewRow

    return PreviewRow(
        id=f"p{port}",
        project_id=_PROJECT_ID,
        env_node_id=_ENV_ID,
        port=port,
        path="/",
        title=title,
        agent_node_id=None,
        thumbnail_path=None,
        created_at=created_at,
    )


def _live(monkeypatch, *ports):
    from app.environments import workspace

    lps = [workspace.ListeningPort(port=p, pid=1, command="node", local_only=False) for p in ports]

    async def _listening(_sbx):
        return lps

    async def _web(_sbx, given):
        return given

    monkeypatch.setattr(env_router.workspace, "listening_ports", _listening)
    monkeypatch.setattr(env_router.workspace, "web_ports", _web)


def _use_previews(env_repo, preview_repo):
    from app.routers.deps import get_preview_repository

    _use(env_repo)
    app.dependency_overrides[get_preview_repository] = lambda: preview_repo


def test_list_previews_merges_db_rows_with_live_ports(client, monkeypatch):
    _use_sandbox(monkeypatch, _FakeSandbox("sbx_1"))
    _live(monkeypatch, 3000, 5173)
    previews = _FakePreviewRepo([_prow(3000, "Todo app"), _prow(3001, "Dead app")])
    _use_previews(_FakeEnvRepo(_node()), previews)
    try:
        response = client.get(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/previews")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    got = [(p["port"], p["published"]) for p in response.json()["previews"]]
    assert got == [(3000, True), (5173, False)]
    assert response.json()["previews"][0]["title"] == "Todo app"


def test_list_previews_falls_back_to_legacy_file(client, monkeypatch):
    sandbox = _FakeSandbox("sbx_1")
    sandbox.content = '[{"title": "Old app", "port": 3000, "path": "/"}]'
    _use_sandbox(monkeypatch, sandbox)
    _live(monkeypatch, 3000)
    _use_previews(_FakeEnvRepo(_node()), _FakePreviewRepo())
    try:
        response = client.get(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/previews")
    finally:
        app.dependency_overrides.clear()

    assert [(p["port"], p["published"]) for p in response.json()["previews"]] == [(3000, True)]


def test_delete_preview_removes_db_row(client, monkeypatch):
    _use_sandbox(monkeypatch, _FakeSandbox("sbx_1"))
    previews = _FakePreviewRepo([_prow(3000, "Todo app")])
    _use_previews(_FakeEnvRepo(_node()), previews)
    try:
        response = client.delete(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/previews/3000")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert previews.deleted == [(_ENV_ID, 3000)]


def _folder_sandbox(output=None, error=None):
    from types import SimpleNamespace

    sandbox = _FakeSandbox("sbx_1")
    sandbox.cmds = []

    async def run(cmd, **_k):
        sandbox.cmds.append(cmd)
        if error:
            raise error
        return SimpleNamespace(stdout=output)

    sandbox.commands = SimpleNamespace(run=run)
    return sandbox


def _live_folders(monkeypatch, *ports):
    from app.environments import workspace

    lps = [
        workspace.ListeningPort(
            port=p,
            pid=1,
            command=f"python3 -m http.server {p} --directory /home/user/d{p}",
            local_only=False,
        )
        for p in ports
    ]

    async def _listening(_sbx):
        return lps

    async def _web(_sbx, given):
        return given

    monkeypatch.setattr(env_router.workspace, "listening_ports", _listening)
    monkeypatch.setattr(env_router.workspace, "web_ports", _web)


def _get_previews(client, sandbox, monkeypatch):
    _use_sandbox(monkeypatch, sandbox)
    _use_previews(_FakeEnvRepo(_node()), _FakePreviewRepo())
    try:
        return client.get(f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/previews")
    finally:
        app.dependency_overrides.clear()


def test_list_previews_points_folder_servers_at_html_in_one_command(client, monkeypatch):
    import json

    ports = [
        {
            "port": p,
            "pid": 1,
            "command": f"python3 -m http.server {p} --directory /home/user/d{p}",
            "cwd": "",
            "local_only": False,
        }
        for p in (8080, 8081)
    ]
    out = json.dumps(
        {
            "ports": ports,
            "web": [8080, 8081],
            "html": {"/home/user/d8080": ["deck.html"], "/home/user/d8081": []},
        }
    )
    sandbox = _folder_sandbox(out)
    response = _get_previews(client, sandbox, monkeypatch)

    assert response.status_code == 200
    assert [(p["port"], p["path"]) for p in response.json()["previews"]] == [(8080, "/deck.html")]
    assert len(sandbox.cmds) == 1


def test_list_previews_survives_listing_failure(client, monkeypatch):
    sandbox = _folder_sandbox(error=RuntimeError("boom"))
    _live_folders(monkeypatch, 8080)
    response = _get_previews(client, sandbox, monkeypatch)

    assert response.status_code == 200
    assert [(p["port"], p["path"]) for p in response.json()["previews"]] == [(8080, "/")]
