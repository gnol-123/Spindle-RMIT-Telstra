from pydantic_ai.toolsets import PrefixedToolset

from app.repositories.tool_repo import ToolNode
from app.tools.assembly import assemble, unavailable_note


def _node(node_id="n1", slug="skill", status="ready", config=None):
    return ToolNode(
        id=node_id,
        project_id="p1",
        name="Code Review",
        tool_type_id="tt1",
        tool_slug=slug,
        config=config or {"text": "Check for N+1 queries."},
        status=status,
        status_detail=None,
    )


async def test_unready_nodes_are_excluded_and_named():
    result = await assemble(None, [_node(status="error")], policy=lambda: "auto")
    assert result.toolsets == []
    assert result.unavailable == ["Code Review"]


async def test_unknown_slug_is_excluded():
    result = await assemble(None, [_node(slug="not_in_registry")], policy=lambda: "auto")
    assert result.toolsets == []
    assert result.unavailable == ["Code Review"]


async def test_ready_skill_node_produces_a_toolset():
    result = await assemble(None, [_node()], policy=lambda: "auto")
    assert len(result.toolsets) == 1
    assert result.unavailable == []


def test_unavailable_note_is_none_when_all_ready():
    assert unavailable_note([]) is None


def test_unavailable_note_names_the_tools():
    note = unavailable_note(["Brave Search"])
    assert "Brave Search" in note


async def test_build_failure_is_dropped_not_raised(monkeypatch):
    from app.tools import assembly

    def _boom(_ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(assembly, "get_spec", lambda _slug: registry_spec_with_broken_build(_boom))

    result = await assemble(None, [_node()], policy=lambda: "auto")
    assert result.toolsets == []
    assert result.unavailable == ["Code Review"]


def registry_spec_with_broken_build(build):
    from app.tools.base import ToolSpec

    async def _verify(_ctx):
        raise AssertionError("verify should not be called by assemble")

    return ToolSpec(kind="skill", build=build, verify=_verify)


async def test_mcp_node_is_prefixed_and_skill_node_is_not():
    mcp_node = _node(
        node_id="m1",
        slug="mcp_server",
        config={"url": "https://example.com/mcp"},
    )
    result = await assemble(None, [mcp_node, _node()], policy=lambda: "auto")
    assert len(result.toolsets) == 2
    assert isinstance(result.toolsets[0].wrapped, PrefixedToolset)
    assert not isinstance(result.toolsets[1].wrapped, PrefixedToolset)
