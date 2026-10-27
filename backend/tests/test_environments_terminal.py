"""The terminal WebSocket.

A fake PTY and a fake sandbox: no E2B, no database. These test the wiring and
the teardown, which is where the real risk is. Close codes are read from the
WebSocketDisconnect the client raises.
"""

import asyncio
import json

import pytest
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.repositories.environment_repo import EnvNode
from app.routers import environments as env_router
from app.routers.auth import UserResponse
from app.routers.deps import get_environment_repository

_PROJECT_ID = "11111111-1111-1111-1111-111111111111"
_ENV_ID = "22222222-2222-2222-2222-222222222222"
_USER_ID = "33333333-3333-3333-3333-333333333333"

_URL = f"/projects/{_PROJECT_ID}/environments/{_ENV_ID}/terminal"


def _node(**over) -> EnvNode:
    base = {
        "id": _ENV_ID,
        "project_id": _PROJECT_ID,
        "name": "Coding Environment",
        "config": {"runtime": "e2b", "role": "user", "sandbox_id": "sbx_1"},
        "status": "ready",
        "status_detail": None,
        "tool_policy": "ask",
        "position_x": 0.0,
        "position_y": 0.0,
    }
    base.update(over)
    return EnvNode(**base)


class _FakeEnvRepo:
    def __init__(self, node: EnvNode | None = None):
        self.node = node
        self.status_writes: list[tuple] = []

    def get_environment_nodes(self, ids):
        return [n for n in map(self.get_environment_node, ids) if n is not None]

    def get_environment_node(self, node_id: str):
        return self.node if self.node and node_id == self.node.id else None

    def set_status(self, node_id: str, status: str, detail: str | None) -> None:
        self.status_writes.append((node_id, status, detail))


class _FakePty:
    """Records what the handler asks of the PTY."""

    def __init__(self, sandbox):
        self._s = sandbox

    async def create(self, size, on_data, **kwargs):
        self._s.created.append({"rows": size.rows, "cols": size.cols, "cwd": kwargs.get("cwd")})
        self._s.on_data = on_data
        return self._s.handle

    async def send_stdin(self, pid, data, **_k):
        self._s.stdin.append((pid, data))

    async def resize(self, pid, size, **_k):
        self._s.resizes.append((pid, size.rows, size.cols))

    async def kill(self, pid, **_k):
        self._s.killed.append(pid)
        return True


class _FakeHandle:
    """A PTY process handle. wait() blocks until the test releases it."""

    def __init__(self, pid=4242):
        self.pid = pid
        self._exit = asyncio.Event()
        self.exit_code = 0

    def finish(self, code=0):
        self.exit_code = code
        self._exit.set()

    async def wait(self):
        await self._exit.wait()

        class _Result:
            pass

        result = _Result()
        result.exit_code = self.exit_code
        return result


class _FakeSandbox:
    def __init__(self, sandbox_id="sbx_1"):
        self.sandbox_id = sandbox_id
        self.created: list[dict] = []
        self.stdin: list[tuple] = []
        self.resizes: list[tuple] = []
        self.killed: list[int] = []
        self.timeouts: list[int] = []
        self.on_data = None
        self.handle = _FakeHandle()
        self.pty = _FakePty(self)

    async def set_timeout(self, timeout, **_k):
        self.timeouts.append(timeout)


def _use(monkeypatch, *, node=None, sandbox=None, user=True, connect_error=None):
    """Wire the fakes. Returns (repo, sandbox)."""
    repo = _FakeEnvRepo(node)
    app.dependency_overrides[get_environment_repository] = lambda: repo

    async def _get_user(credentials):
        if not user:
            from app.routers.auth import _credentials_error

            raise _credentials_error("Invalid or expired token")
        return UserResponse(id=_USER_ID, email="t@example.com")

    monkeypatch.setattr(env_router, "get_current_user", _get_user)

    async def _connect(ctx):
        if connect_error is not None:
            raise connect_error
        return sandbox

    monkeypatch.setattr(env_router.e2b, "connect", _connect)
    monkeypatch.setattr(env_router, "_terminal_repo", lambda token, user_id: repo)
    return repo, sandbox


# -- rejection paths ---------------------------------------------------------


def test_terminal_without_a_token_closes_4401(client, monkeypatch):
    _use(monkeypatch, node=_node(), sandbox=_FakeSandbox())
    try:
        with client.websocket_connect(_URL) as ws, pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_bytes()
    finally:
        app.dependency_overrides.clear()

    assert exc.value.code == 4401


def test_terminal_with_a_bad_token_closes_4401(client, monkeypatch):
    _use(monkeypatch, node=_node(), sandbox=_FakeSandbox(), user=False)
    try:
        with (
            client.websocket_connect(f"{_URL}?token=bad") as ws,
            pytest.raises(WebSocketDisconnect) as exc,
        ):
            ws.receive_bytes()
    finally:
        app.dependency_overrides.clear()

    assert exc.value.code == 4401


def test_terminal_on_a_missing_environment_closes_4404(client, monkeypatch):
    _use(monkeypatch, node=None, sandbox=_FakeSandbox())
    try:
        with (
            client.websocket_connect(f"{_URL}?token=t") as ws,
            pytest.raises(WebSocketDisconnect) as exc,
        ):
            ws.receive_bytes()
    finally:
        app.dependency_overrides.clear()

    assert exc.value.code == 4404


def test_terminal_on_a_stopped_environment_closes_4409(client, monkeypatch):
    stopped = _node(status="stopped", config={"runtime": "e2b", "role": "user"})
    _use(monkeypatch, node=stopped, sandbox=_FakeSandbox())
    try:
        with (
            client.websocket_connect(f"{_URL}?token=t") as ws,
            pytest.raises(WebSocketDisconnect) as exc,
        ):
            ws.receive_bytes()
    finally:
        app.dependency_overrides.clear()

    assert exc.value.code == 4409


def test_terminal_when_the_sandbox_is_unreachable_closes_4502(client, monkeypatch):
    repo, _ = _use(monkeypatch, node=_node(), sandbox=None, connect_error=ConnectionError("gone"))
    try:
        with (
            client.websocket_connect(f"{_URL}?token=t") as ws,
            pytest.raises(WebSocketDisconnect) as exc,
        ):
            ws.receive_bytes()
    finally:
        app.dependency_overrides.clear()

    assert exc.value.code == 4502
    # The canvas should show the failure rather than waiting for a turn.
    assert repo.status_writes and repo.status_writes[-1][1] == "error"


# -- the session ---------------------------------------------------------


def test_terminal_starts_a_pty_with_the_requested_size(client, monkeypatch):
    sandbox = _FakeSandbox()
    _use(monkeypatch, node=_node(), sandbox=sandbox)
    try:
        with client.websocket_connect(f"{_URL}?token=t&cols=120&rows=40"):
            pass
    finally:
        app.dependency_overrides.clear()

    assert sandbox.created
    assert sandbox.created[0]["cols"] == 120
    assert sandbox.created[0]["rows"] == 40


def test_terminal_defaults_the_size(client, monkeypatch):
    sandbox = _FakeSandbox()
    _use(monkeypatch, node=_node(), sandbox=sandbox)
    try:
        with client.websocket_connect(f"{_URL}?token=t"):
            pass
    finally:
        app.dependency_overrides.clear()

    assert sandbox.created[0]["cols"] == 80
    assert sandbox.created[0]["rows"] == 24


def test_terminal_clamps_an_absurd_size(client, monkeypatch):
    """A hostile or buggy client must not ask for a 100000 column PTY."""
    sandbox = _FakeSandbox()
    _use(monkeypatch, node=_node(), sandbox=sandbox)
    try:
        with client.websocket_connect(f"{_URL}?token=t&cols=100000&rows=99999"):
            pass
    finally:
        app.dependency_overrides.clear()

    assert sandbox.created[0]["cols"] <= 500
    assert sandbox.created[0]["rows"] <= 200


def test_terminal_registers_a_queueing_output_callback(client, monkeypatch):
    """Output reaches the browser through a queue the handler drains.

    The callback cannot be invoked from inside the ``with`` block: under
    TestClient the handler does not advance to pty.create while the client is
    driving the socket, so anything asserted there would race. What is
    checkable is the contract E2B is handed: a sync callable that only queues,
    keeping any await out of E2B's read loop.
    """
    sandbox = _FakeSandbox()
    _use(monkeypatch, node=_node(), sandbox=sandbox)
    try:
        with client.websocket_connect(f"{_URL}?token=t"):
            pass
    finally:
        app.dependency_overrides.clear()

    assert sandbox.on_data is not None
    # asyncio.Queue.put_nowait, bound: sync, so E2B's reader never awaits.
    assert not asyncio.iscoroutinefunction(sandbox.on_data)
    assert sandbox.on_data.__name__ == "put_nowait"


def test_terminal_delivers_queued_output_to_the_browser(client, monkeypatch):
    """Bytes queued before the client reads still arrive.

    Seeding the queue at pty.create time is the only way to have output
    pending when the socket opens, since the handler does not run further
    while the test drives the connection.
    """
    sandbox = _FakeSandbox()
    _use(monkeypatch, node=_node(), sandbox=sandbox)

    real_create = sandbox.pty.create

    async def _create_and_seed(size, on_data, **kwargs):
        handle = await real_create(size, on_data, **kwargs)
        on_data(b"hello from the shell")
        return handle

    sandbox.pty.create = _create_and_seed

    try:
        with client.websocket_connect(f"{_URL}?token=t") as ws:
            assert ws.receive_bytes() == b"hello from the shell"
    finally:
        app.dependency_overrides.clear()


def test_terminal_forwards_binary_input_to_the_pty(client, monkeypatch):
    sandbox = _FakeSandbox()
    _use(monkeypatch, node=_node(), sandbox=sandbox)
    try:
        with client.websocket_connect(f"{_URL}?token=t") as ws:
            ws.send_bytes(b"ls\n")
            # Give the input pump a moment to forward it.
            for _ in range(50):
                if sandbox.stdin:
                    break
                ws.send_bytes(b"")
    finally:
        app.dependency_overrides.clear()

    assert any(data == b"ls\n" for _pid, data in sandbox.stdin)


def test_terminal_forwards_json_input(client, monkeypatch):
    sandbox = _FakeSandbox()
    _use(monkeypatch, node=_node(), sandbox=sandbox)
    try:
        with client.websocket_connect(f"{_URL}?token=t") as ws:
            ws.send_text(json.dumps({"type": "input", "data": "whoami\n"}))
            for _ in range(50):
                if sandbox.stdin:
                    break
                ws.send_text(json.dumps({"type": "input", "data": ""}))
    finally:
        app.dependency_overrides.clear()

    assert any(data == b"whoami\n" for _pid, data in sandbox.stdin)


def test_terminal_handles_a_resize_frame(client, monkeypatch):
    sandbox = _FakeSandbox()
    _use(monkeypatch, node=_node(), sandbox=sandbox)
    try:
        with client.websocket_connect(f"{_URL}?token=t") as ws:
            ws.send_text(json.dumps({"type": "resize", "cols": 100, "rows": 30}))
            for _ in range(50):
                if sandbox.resizes:
                    break
                ws.send_text(json.dumps({"type": "input", "data": ""}))
    finally:
        app.dependency_overrides.clear()

    assert sandbox.resizes
    assert sandbox.resizes[-1][1:] == (30, 100)


def test_terminal_ignores_a_malformed_frame(client, monkeypatch):
    """Garbage from the client must not kill the session."""
    sandbox = _FakeSandbox()
    _use(monkeypatch, node=_node(), sandbox=sandbox)
    try:
        with client.websocket_connect(f"{_URL}?token=t") as ws:
            ws.send_text("not json at all")
            ws.send_text(json.dumps({"type": "wat"}))
            # Still alive: a real frame after the garbage still works.
            ws.send_bytes(b"echo\n")
            for _ in range(50):
                if sandbox.stdin:
                    break
                ws.send_bytes(b"")
    finally:
        app.dependency_overrides.clear()

    assert any(data == b"echo\n" for _pid, data in sandbox.stdin)


# -- teardown ------------------------------------------------------------


def test_terminal_kills_the_pty_on_disconnect(client, monkeypatch):
    """A PTY is a process: closing the socket does not stop it."""
    sandbox = _FakeSandbox()
    _use(monkeypatch, node=_node(), sandbox=sandbox)
    try:
        with client.websocket_connect(f"{_URL}?token=t"):
            pass
    finally:
        app.dependency_overrides.clear()

    assert sandbox.killed == [sandbox.handle.pid]


def test_terminal_reports_the_exit_code_when_the_shell_ends(client, monkeypatch):
    sandbox = _FakeSandbox()
    _use(monkeypatch, node=_node(), sandbox=sandbox)
    try:
        with client.websocket_connect(f"{_URL}?token=t") as ws:
            sandbox.handle.finish(code=7)
            message = json.loads(ws.receive_text())
    finally:
        app.dependency_overrides.clear()

    assert message == {"type": "exit", "code": 7}


def test_terminal_kills_the_pty_when_the_shell_exits(client, monkeypatch):
    sandbox = _FakeSandbox()
    _use(monkeypatch, node=_node(), sandbox=sandbox)
    try:
        with client.websocket_connect(f"{_URL}?token=t") as ws:
            sandbox.handle.finish(code=0)
            ws.receive_text()
    finally:
        app.dependency_overrides.clear()

    assert sandbox.killed == [sandbox.handle.pid]
