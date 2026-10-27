"""scan_previews: one combined command, same result as the separate ones."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.environments import workspace

_PORTS = [
    {"port": 3000, "pid": 7, "command": "node a.js", "cwd": "/home/user/a", "local_only": False},
    {
        "port": 8080,
        "pid": 8,
        "command": "python3 -m http.server 8080 --directory /home/user/site",
        "cwd": "",
        "local_only": True,
    },
    {"port": 22, "pid": 1, "command": "sshd", "cwd": "", "local_only": False},
    {"port": workspace.ENVD_PORT, "pid": 2, "command": "envd", "cwd": "", "local_only": False},
]
_HTML = {"/home/user/site": ["deck.html"]}


def _sandbox(run):
    return SimpleNamespace(commands=SimpleNamespace(run=run))


@pytest.mark.anyio
async def test_combined_output_matches_separate_commands():
    web = [3000, 8080, workspace.ENVD_PORT]
    combined = json.dumps({"ports": _PORTS, "web": web, "html": _HTML})
    cmds = []

    async def run(cmd, **_):
        cmds.append(cmd)
        return SimpleNamespace(stdout=combined)

    listening, html = await workspace.scan_previews(_sandbox(run))

    old = [p for p in workspace.parse_ports_json(json.dumps(_PORTS)) if p.port in (3000, 8080)]
    assert listening == workspace.previewable(old)
    assert html == _HTML
    assert cmds == [workspace.SCAN_COMMAND]


@pytest.mark.anyio
async def test_falls_back_to_separate_commands_when_combined_fails(monkeypatch):
    cmd = "python3 -m http.server 8080 --directory /d"
    lp = workspace.ListeningPort(port=8080, pid=1, command=cmd, local_only=False)
    monkeypatch.setattr(workspace, "listening_ports", AsyncMock(return_value=[lp]))
    monkeypatch.setattr(workspace, "web_ports", AsyncMock(return_value=[lp]))
    monkeypatch.setattr(workspace, "folder_html_files", AsyncMock(return_value={"/d": ["a.html"]}))

    async def run(cmd, **_):
        return SimpleNamespace(stdout="not json")

    listening, html = await workspace.scan_previews(_sandbox(run))
    assert listening == [lp]
    assert html == {"/d": ["a.html"]}


def test_scan_script_compiles():
    compile(workspace._SCAN_SCRIPT, "scan", "exec")


@pytest.mark.anyio
@pytest.mark.parametrize("db_rows,reads", [(0, 1), (1, 0)])
async def test_legacy_registry_only_read_when_db_empty(monkeypatch, db_rows, reads):
    from app.routers import environments as router

    read = AsyncMock(return_value=[])
    monkeypatch.setattr(router.workspace, "read_registry", read)
    monkeypatch.setattr(router.workspace, "scan_previews", AsyncMock(return_value=([], {})))
    row = SimpleNamespace(title="t", port=3000, path="/", agent_node_id=None, created_at="x")
    repo = SimpleNamespace(list_for_env=lambda _id: [row] * db_rows)

    async def on_sandbox(_repo, _node, op):
        return await op(SimpleNamespace(get_host=str))

    monkeypatch.setattr(router, "_load_ready", AsyncMock(return_value=SimpleNamespace(id="n")))
    monkeypatch.setattr(router, "_on_sandbox", on_sandbox)

    await router.list_environment_previews(uuid4(), uuid4(), None, repo)
    assert read.await_count == reads
