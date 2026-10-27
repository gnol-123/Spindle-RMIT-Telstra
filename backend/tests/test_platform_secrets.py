from app.config import settings
from app.repositories.tool_repo import ToolNode
from app.tools import assembly, registry
from app.tools.assembly import assemble
from app.tools.base import ToolContext, ToolSpec, VerifyResult


def test_platform_secrets_empty_when_unset(monkeypatch):
    monkeypatch.setattr(settings, "brave_api_key", "")
    assert registry.platform_secrets("brave_search") == {}


def test_platform_secrets_brave_key(monkeypatch):
    monkeypatch.setattr(settings, "brave_api_key", "platform-key")
    assert registry.platform_secrets("brave_search") == {"api_key": "platform-key"}


def test_platform_secrets_unknown_slug_is_empty(monkeypatch):
    monkeypatch.setattr(settings, "brave_api_key", "platform-key")
    assert registry.platform_secrets("skill") == {}


def _brave_node():
    return ToolNode(
        id="n1",
        project_id="p1",
        name="Brave",
        tool_type_id="tt1",
        tool_slug="brave_search",
        config={},
        status="ready",
        status_detail=None,
    )


class _Repo:
    def __init__(self, keys):
        self._keys = keys

    def secret_keys(self, node_id):
        return list(self._keys)

    def secret_keys_for_nodes(self, ids):
        return {i: list(self._keys) for i in ids} if self._keys else {}


async def test_assemble_uses_platform_key_when_node_has_none(monkeypatch):
    seen = {}

    def fake_build(ctx: ToolContext):
        seen.update(ctx.secrets)
        from pydantic_ai.toolsets import FunctionToolset

        return FunctionToolset()

    async def fake_verify(ctx):
        return VerifyResult(ok=True)

    monkeypatch.setattr(assembly, "get_spec", lambda s: ToolSpec("api", fake_build, fake_verify))
    monkeypatch.setattr(assembly, "platform_secrets", lambda s: {"api_key": "platform-key"})
    monkeypatch.setattr(assembly, "load_node_secrets", lambda node_id, keys: {})

    await assemble(_Repo([]), [_brave_node()], policy=lambda: "auto")
    assert seen == {"api_key": "platform-key"}


async def test_assemble_user_key_overrides_platform_key(monkeypatch):
    seen = {}

    def fake_build(ctx: ToolContext):
        seen.update(ctx.secrets)
        from pydantic_ai.toolsets import FunctionToolset

        return FunctionToolset()

    async def fake_verify(ctx):
        return VerifyResult(ok=True)

    monkeypatch.setattr(assembly, "get_spec", lambda s: ToolSpec("api", fake_build, fake_verify))
    monkeypatch.setattr(assembly, "platform_secrets", lambda s: {"api_key": "platform-key"})
    monkeypatch.setattr(
        assembly, "load_node_secrets", lambda node_id, keys: {"api_key": "user-key"}
    )

    await assemble(_Repo(["api_key"]), [_brave_node()], policy=lambda: "auto")
    assert seen == {"api_key": "user-key"}


def test_platform_secrets_context7_key(monkeypatch):
    monkeypatch.setattr(settings, "context7_api_key", "c7-key")
    assert registry.platform_secrets("context7") == {"auth_token": "c7-key"}


def test_platform_secrets_generic_mcp_never_gets_a_platform_key(monkeypatch):
    monkeypatch.setattr(settings, "context7_api_key", "c7-key")
    assert registry.platform_secrets("mcp_server") == {}
