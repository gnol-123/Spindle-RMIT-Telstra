import re

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import CombinedToolset
from pydantic_ai.usage import RunUsage

from app.tools import skills
from app.tools.api import brave_search
from app.tools.base import ToolContext
from app.tools.registry import get_spec


def _ctx(config):
    return ToolContext(node_id="n1", name="Code Review", config=config, secrets={})


def _run_context() -> RunContext:
    return RunContext(deps=None, model=TestModel(), usage=RunUsage())


def test_unknown_slug_returns_none():
    assert get_spec("does_not_exist") is None


async def test_skill_verify_rejects_empty_text():
    spec = get_spec("skill")
    assert spec is not None
    result = await spec.verify(_ctx({"text": "   "}))
    assert result.ok is False
    assert "text" in (result.detail or "").lower()


async def test_skill_verify_accepts_text():
    spec = get_spec("skill")
    result = await spec.verify(_ctx({"text": "Always check for N+1 queries."}))
    assert result.ok is True


async def test_skill_toolset_returns_the_text():
    spec = get_spec("skill")
    toolset = spec.build(_ctx({"text": "Always check for N+1 queries."}))
    tools = await toolset.get_tools(_run_context())
    assert len(tools) == 1
    name = next(iter(tools))
    assert name.startswith("load_")


# --- skill tool naming -------------------------------------------------------
# A duplicate tool name raises UserError from pydantic-ai and fails the whole
# turn, so these guard a crash, not a cosmetic detail.

_UUID_A = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
_UUID_B = "11111111-2222-3333-4444-555555555555"


def _skill(name: str, node_id: str = _UUID_A):
    return ToolContext(node_id=node_id, name=name, config={"text": "x"}, secrets={})


def test_tool_name_is_explicit_not_dunder_name():
    """The name must be passed to add_function, not set via __name__."""
    toolset = skills.build(_skill("Code Review"))
    assert list(toolset.tools) == [skills.tool_name(_skill("Code Review"))]


@pytest.mark.parametrize(
    "label",
    ["Code Review", "Code-Review", "   ", "!!!", "Research 日本語", "123 Start", "a" * 300, "def"],
)
def test_tool_name_is_always_provider_valid(label):
    """Providers reject names over 64 chars or outside [a-zA-Z0-9_-]."""
    name = skills.tool_name(_skill(label))
    assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name), name


def test_labels_that_sanitise_alike_do_not_collide():
    assert skills.tool_name(_skill("Code-Review", _UUID_A)) != skills.tool_name(
        _skill("Code_Review!!", _UUID_B)
    )


async def test_two_similar_skills_combine_without_error():
    """Regression: this raised UserError and failed the turn."""
    a = skills.build(_skill("Code-Review", _UUID_A))
    b = skills.build(_skill("Code_Review!!", _UUID_B))
    tools = await CombinedToolset([a, b]).get_tools(_run_context())
    assert len(tools) == 2


async def test_name_and_description_reach_the_tool_definition():
    ctx = ToolContext(
        node_id=_UUID_A,
        name="Code Review",
        config={"text": "x", "description": "Use for X"},
        secrets={},
    )
    tools = await skills.build(ctx).get_tools(_run_context())
    definition = tools[skills.tool_name(ctx)].tool_def
    assert definition.name == skills.tool_name(ctx)
    assert definition.description == "Use for X"


# --- brave_search -------------------------------------------------------------


async def test_brave_search_verify_fails_without_key():
    spec = get_spec("brave_search")
    assert spec is not None
    result = await spec.verify(ToolContext(node_id="n1", name="Brave", config={}, secrets={}))
    assert result.ok is False
    assert "api key" in (result.detail or "").lower()


async def test_brave_search_exposes_one_tool():
    spec = get_spec("brave_search")
    assert spec is not None
    ctx = ToolContext(node_id="n1", name="Brave", config={}, secrets={"api_key": "x"})
    toolset = spec.build(ctx)
    tools = await toolset.get_tools(_run_context())
    assert list(tools) == [brave_search.tool_name(ctx)]


# --- mcp_servers --------------------------------------------------------------


async def test_mcp_verify_requires_url():
    spec = get_spec("mcp_server")
    assert spec is not None
    result = await spec.verify(ToolContext(node_id="n1", name="GitHub", config={}, secrets={}))
    assert result.ok is False
    assert "url" in (result.detail or "").lower()


# --- context7 -----------------------------------------------------------------


def test_context7_is_an_mcp_spec():
    spec = get_spec("context7")
    assert spec is not None
    assert spec.kind == "mcp"


async def test_context7_verify_requires_url():
    spec = get_spec("context7")
    result = await spec.verify(ToolContext(node_id="n1", name="Context7", config={}, secrets={}))
    assert result.ok is False
    assert "url" in (result.detail or "").lower()
