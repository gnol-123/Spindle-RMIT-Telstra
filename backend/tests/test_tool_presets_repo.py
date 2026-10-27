from app.repositories.project_repo import AgentType
from app.repositories.tool_repo import ToolPreset, _to_tool_preset


def test_to_tool_preset_flattens_type_join():
    row = {
        "id": "p1",
        "slug": "research_method",
        "name": "Research Method",
        "description": "How to research",
        "tool_type_id": "tt1",
        "config": {"text": "Do research.", "description": "Load first."},
        "tool_types": {"slug": "skill"},
    }
    preset = _to_tool_preset(row)
    assert preset == ToolPreset(
        id="p1",
        slug="research_method",
        name="Research Method",
        description="How to research",
        tool_type_id="tt1",
        tool_slug="skill",
        config={"text": "Do research.", "description": "Load first."},
    )


def test_to_tool_preset_tolerates_missing_optional_fields():
    preset = _to_tool_preset({"id": "p1", "slug": "x", "name": "X", "tool_type_id": "tt1"})
    assert preset.description is None
    assert preset.config == {}
    assert preset.tool_slug == ""


def test_agent_type_default_presets_defaults_empty():
    a = AgentType(
        id="a", slug="coding", name="Coding", description="d", system_prompt="x", model="m"
    )
    assert a.default_presets == []
