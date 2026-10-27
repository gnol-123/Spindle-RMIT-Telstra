"""A fake AsyncSandbox, shared by the environment test modules.

Records calls rather than reaching E2B. Async where the real SDK is async.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class FakeEntry:
    """Stands in for e2b.EntryInfo. Only the fields build() reads."""

    name: str
    type: str  # compare against the real e2b.FileType values in tests
    size: int = 0


class FakeFiles:
    def __init__(self, sandbox: "FakeSandbox") -> None:
        self._s = sandbox

    async def make_dir(self, path: str, **_k: Any) -> bool:
        self._s.calls.append(("make_dir", path))
        self._s.users.append(_k.get("user"))
        if self._s.raise_on_make_dir is not None:
            raise self._s.raise_on_make_dir
        self._s.dirs.add(path)
        return True

    async def list(self, path: str, depth: int = 1, **_k: Any) -> list:
        self._s.calls.append(("list", path))
        self._s.users.append(_k.get("user"))
        if self._s.raise_on_list is not None:
            raise self._s.raise_on_list
        return self._s.entries

    async def read(self, path: str, **_k: Any) -> str:
        self._s.calls.append(("read", path))
        self._s.users.append(_k.get("user"))
        if self._s.raise_on_read is not None:
            raise self._s.raise_on_read
        return self._s.stored.get(path, "")

    async def write(self, path: str, data, **_k: Any):
        self._s.calls.append(("write", path))
        self._s.users.append(_k.get("user"))
        if self._s.raise_on_write is not None:
            raise self._s.raise_on_write
        self._s.stored[path] = data
        return None


class FakeCommands:
    def __init__(self, sandbox: "FakeSandbox") -> None:
        self._s = sandbox

    async def run(self, cmd: str, **kwargs: Any):
        self._s.calls.append(("run", cmd, kwargs.get("cwd"), kwargs.get("timeout")))
        self._s.users.append(kwargs.get("user"))
        if self._s.raise_on_run is not None:
            raise self._s.raise_on_run
        return self._s.run_result


class FakeSandbox:
    """Stands in for AsyncSandbox. Only the surface this feature uses."""

    def __init__(self, sandbox_id: str = "sbx_fake_1") -> None:
        self.sandbox_id = sandbox_id
        self.calls: list[tuple] = []
        # The user= passed on each files/commands call, in order.
        self.users: list[str | None] = []
        self.dirs: set[str] = set()
        self.stored: dict[str, Any] = {}
        self.entries: list = []
        self.run_result: Any = None
        self.killed = False
        self.timeouts: list[int] = []
        self.running = True
        # Set any of these to an exception instance to make that call raise.
        self.raise_on_make_dir: Exception | None = None
        self.raise_on_list: Exception | None = None
        self.raise_on_read: Exception | None = None
        self.raise_on_write: Exception | None = None
        self.raise_on_run: Exception | None = None
        self.files = FakeFiles(self)
        self.commands = FakeCommands(self)

    async def set_timeout(self, timeout: int, **_k: Any) -> None:
        self.timeouts.append(timeout)

    async def is_running(self, **_k: Any) -> bool:
        return self.running

    async def kill(self, **_k: Any) -> bool:
        self.killed = True
        return True

    def get_mcp_url(self) -> str:
        return f"https://50005-{self.sandbox_id}.e2b.app/mcp"

    async def get_mcp_token(self) -> str:
        return "mcp-token"

    def get_host(self, port: int) -> str:
        return f"{port}-{self.sandbox_id}.e2b.app"
