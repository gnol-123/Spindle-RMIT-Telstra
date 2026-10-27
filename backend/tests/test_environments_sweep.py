"""The orphan sweep: sandboxes tagged ours with no matching node row."""

import pytest

from app.environments import sweep


class _FakeSandboxInfo:
    def __init__(self, sandbox_id, node_id=None, project_id=None):
        self.sandbox_id = sandbox_id
        self.metadata = {"app": "murud"}
        if node_id is not None:
            self.metadata["node_id"] = node_id
        if project_id is not None:
            self.metadata["project_id"] = project_id


class _FakePaginator:
    def __init__(self, pages):
        self._pages = list(pages)

    async def next_items(self):
        return self._pages.pop(0) if self._pages else []

    @property
    def has_next(self):
        return bool(self._pages)


class _FakeDB:
    """Stands in for the service-role Supabase client. One table: nodes."""

    def __init__(self, rows):
        self._rows = rows

    def table(self, name):
        assert name == "nodes"
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def execute(self):
        class _Result:
            pass

        r = _Result()
        r.data = self._rows
        return r


def _node_row(node_id, sandbox_id):
    return {"id": node_id, "config": {"sandbox_id": sandbox_id}}


@pytest.mark.anyio
async def test_finds_a_sandbox_with_no_node_row(monkeypatch):
    sandboxes = [_FakeSandboxInfo("sbx_orphan", node_id="node-gone")]
    monkeypatch.setattr(sweep, "_list_sandboxes", lambda: _FakePaginator([sandboxes]))
    monkeypatch.setattr(sweep, "_all_nodes", lambda: [])

    orphans = await sweep.find_orphans()

    assert [o.sandbox_id for o in orphans] == ["sbx_orphan"]
    assert orphans[0].reason == "no matching node"


@pytest.mark.anyio
async def test_a_sandbox_matching_its_nodes_current_id_is_not_an_orphan(monkeypatch):
    sandboxes = [_FakeSandboxInfo("sbx_current", node_id="node-1")]
    monkeypatch.setattr(sweep, "_list_sandboxes", lambda: _FakePaginator([sandboxes]))
    monkeypatch.setattr(sweep, "_all_nodes", lambda: [_node_row("node-1", "sbx_current")])

    orphans = await sweep.find_orphans()

    assert orphans == []


@pytest.mark.anyio
async def test_a_sandbox_superseded_by_a_newer_one_is_an_orphan(monkeypatch):
    """The node restarted; this old sandbox_id was never killed."""
    sandboxes = [_FakeSandboxInfo("sbx_old", node_id="node-1")]
    monkeypatch.setattr(sweep, "_list_sandboxes", lambda: _FakePaginator([sandboxes]))
    monkeypatch.setattr(sweep, "_all_nodes", lambda: [_node_row("node-1", "sbx_new")])

    orphans = await sweep.find_orphans()

    assert [o.sandbox_id for o in orphans] == ["sbx_old"]
    assert orphans[0].reason == "superseded by a newer sandbox"


@pytest.mark.anyio
async def test_a_sandbox_with_no_node_id_tag_is_reported_but_not_killable(monkeypatch):
    """Not created by our provision path. Report it, never auto-kill it."""
    sandboxes = [_FakeSandboxInfo("sbx_untagged")]
    monkeypatch.setattr(sweep, "_list_sandboxes", lambda: _FakePaginator([sandboxes]))
    monkeypatch.setattr(sweep, "_all_nodes", lambda: [])

    orphans = await sweep.find_orphans()

    assert [o.sandbox_id for o in orphans] == ["sbx_untagged"]
    assert orphans[0].reason == "no node_id in metadata"
    assert orphans[0].killable is False


@pytest.mark.anyio
async def test_pages_through_multiple_batches(monkeypatch):
    page1 = [_FakeSandboxInfo("sbx_a", node_id="gone-a")]
    page2 = [_FakeSandboxInfo("sbx_b", node_id="gone-b")]
    monkeypatch.setattr(sweep, "_list_sandboxes", lambda: _FakePaginator([page1, page2]))
    monkeypatch.setattr(sweep, "_all_nodes", lambda: [])

    orphans = await sweep.find_orphans()

    assert {o.sandbox_id for o in orphans} == {"sbx_a", "sbx_b"}


def test_main_report_only_never_kills(monkeypatch, capsys):
    calls = []

    async def _find():
        from app.environments.sweep import Orphan

        return [Orphan(sandbox_id="sbx_1", node_id="gone", reason="no matching node")]

    async def _kill(sandbox_id):
        calls.append(sandbox_id)

    monkeypatch.setattr(sweep, "find_orphans", _find)
    monkeypatch.setattr(sweep, "_kill", _kill)

    sweep.main([])

    assert calls == []
    assert "sbx_1" in capsys.readouterr().out


def test_main_apply_kills_every_orphan(monkeypatch):
    from app.environments.sweep import Orphan

    calls = []

    async def _find():
        return [
            Orphan(sandbox_id="sbx_1", node_id="gone", reason="no matching node"),
            Orphan(
                sandbox_id="sbx_2",
                node_id=None,
                reason="no node_id in metadata",
                killable=False,
            ),
        ]

    async def _kill(sandbox_id):
        calls.append(sandbox_id)

    monkeypatch.setattr(sweep, "find_orphans", _find)
    monkeypatch.setattr(sweep, "_kill", _kill)

    sweep.main(["--apply"])

    # The untagged sandbox is never killable, apply or not.
    assert calls == ["sbx_1"]
