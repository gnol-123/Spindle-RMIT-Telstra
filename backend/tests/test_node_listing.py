from app.repositories.project_repo import _to_node
from app.routers.projects import NodeResponse


def test_tool_node_row_survives_agent_node_mapping_and_response():
    """A tool node has agent_type_id NULL, enforced by nodes_type_matches_kind.

    list_agent_nodes no longer filters on kind, so a tool node row can reach
    _to_node and then NodeResponse.of. Neither must raise.
    """
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "project_id": "22222222-2222-2222-2222-222222222222",
        "name": "Brave",
        "agent_type_id": None,
        "tool_policy": "ask",
        "position_x": 0,
        "position_y": 0,
        "kind": "tool",
        "agent_types": None,
    }
    node = _to_node(row)
    assert node.agent_type_id is None
    assert node.kind == "tool"

    response = NodeResponse.of(node)
    assert response.kind == "tool"
    assert response.agent_slug is None


def test_listing_reports_agent_slug_for_agent_and_null_for_tool():
    """A canvas listing mixes agent and tool rows. The agent must report its
    template slug; the tool must report null. Regression: list_agent_nodes'
    select omitted agent_types.slug and .of() was called with no override, so
    every row came back with agent_slug: None.
    """
    agent_row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "project_id": "22222222-2222-2222-2222-222222222222",
        "name": "Researcher",
        "agent_type_id": "33333333-3333-3333-3333-333333333333",
        "tool_policy": "ask",
        "position_x": 0,
        "position_y": 0,
        "kind": "agent",
        "agent_types": {"slug": "researcher", "system_prompt": "You research.", "model": "gpt-5"},
    }
    tool_row = {
        "id": "44444444-4444-4444-4444-444444444444",
        "project_id": "22222222-2222-2222-2222-222222222222",
        "name": "Brave",
        "agent_type_id": None,
        "tool_policy": "ask",
        "position_x": 0,
        "position_y": 0,
        "kind": "tool",
        "agent_types": None,
    }

    agent_node = _to_node(agent_row)
    tool_node = _to_node(tool_row)

    agent_response = NodeResponse.of(agent_node)
    tool_response = NodeResponse.of(tool_node)

    assert agent_response.agent_slug == "researcher"
    assert agent_response.kind == "agent"
    assert tool_response.agent_slug is None
    assert tool_response.kind == "tool"


def test_environment_row_maps_status_and_config():
    """An environment row carries its lifecycle and identity through _to_node."""
    row = {
        "id": "55555555-5555-5555-5555-555555555555",
        "project_id": "22222222-2222-2222-2222-222222222222",
        "name": "Scratch Space",
        "agent_type_id": None,
        "tool_policy": "auto",
        "position_x": 0,
        "position_y": 0,
        "kind": "environment",
        "status": "ready",
        "status_detail": "Sandbox running",
        "config": {"runtime": "e2b", "role": "scratch", "sandbox_id": "sbx_1"},
        "agent_types": None,
    }
    node = _to_node(row)
    assert node.kind == "environment"
    assert node.status == "ready"
    assert node.status_detail == "Sandbox running"
    assert node.config["role"] == "scratch"

    response = NodeResponse.of(node)
    assert response.status == "ready"
    assert response.status_detail == "Sandbox running"
    assert response.role == "scratch"
    assert response.runtime == "e2b"


def test_environment_response_reports_user_role():
    """A user provisioned environment is the same kind, distinguished by role."""
    row = {
        "id": "66666666-6666-6666-6666-666666666666",
        "project_id": "22222222-2222-2222-2222-222222222222",
        "name": "Coding Environment",
        "agent_type_id": None,
        "tool_policy": "ask",
        "position_x": 120.0,
        "position_y": 40.0,
        "kind": "environment",
        "status": "provisioning",
        "status_detail": None,
        "config": {"runtime": "e2b", "role": "user"},
        "agent_types": None,
    }
    response = NodeResponse.of(_to_node(row))
    assert response.kind == "environment"
    assert response.role == "user"
    assert response.runtime == "e2b"
    assert response.status == "provisioning"


def test_agent_and_tool_rows_report_no_role_or_runtime():
    """role and runtime are environment only. Other kinds must not invent them."""
    base = {
        "project_id": "22222222-2222-2222-2222-222222222222",
        "agent_type_id": None,
        "tool_policy": "ask",
        "position_x": 0,
        "position_y": 0,
        "agent_types": None,
    }
    tool = NodeResponse.of(
        _to_node(
            {**base, "id": "77777777-7777-7777-7777-777777777777", "name": "Brave", "kind": "tool"}
        )
    )
    agent = NodeResponse.of(
        _to_node(
            {
                **base,
                "id": "88888888-8888-8888-8888-888888888888",
                "name": "Researcher",
                "kind": "agent",
            }
        )
    )
    assert tool.role is None and tool.runtime is None
    assert agent.role is None and agent.runtime is None


def test_row_without_the_new_columns_still_maps():
    """get_agent_node's select omits status and config; the defaults must hold.

    Regression guard: adding columns to list_nodes must not make the other
    caller of _to_node raise a KeyError.
    """
    row = {
        "id": "99999999-9999-9999-9999-999999999999",
        "project_id": "22222222-2222-2222-2222-222222222222",
        "name": "Researcher",
        "agent_type_id": "33333333-3333-3333-3333-333333333333",
        "tool_policy": "ask",
        "position_x": 0,
        "position_y": 0,
        "agent_types": {"slug": "researcher", "system_prompt": "You research.", "model": "gpt-5"},
    }
    node = _to_node(row)
    assert node.kind == "agent"
    assert node.status == "ready"
    assert node.status_detail is None
    assert node.config == {}

    response = NodeResponse.of(node)
    assert response.status == "ready"
    assert response.role is None


def test_environment_row_with_null_config_does_not_crash():
    """A row whose config came back null must map to an empty dict, not None."""
    row = {
        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "project_id": "22222222-2222-2222-2222-222222222222",
        "name": "Broken",
        "agent_type_id": None,
        "tool_policy": "ask",
        "position_x": 0,
        "position_y": 0,
        "kind": "environment",
        "status": "error",
        "status_detail": "Sandbox not found",
        "config": None,
        "agent_types": None,
    }
    response = NodeResponse.of(_to_node(row))
    assert response.status == "error"
    assert response.status_detail == "Sandbox not found"
    # No runtime or role in config: report null rather than guessing a default.
    assert response.role is None
    assert response.runtime is None


def test_node_config_default_is_not_shared_between_instances():
    """A mutable default on a frozen dataclass must be a factory, not a literal."""
    a = _to_node(
        {
            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "project_id": "22222222-2222-2222-2222-222222222222",
            "name": "A",
            "agent_type_id": None,
            "tool_policy": "ask",
            "position_x": 0,
            "position_y": 0,
            "agent_types": None,
        }
    )
    b = _to_node(
        {
            "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            "project_id": "22222222-2222-2222-2222-222222222222",
            "name": "B",
            "agent_type_id": None,
            "tool_policy": "ask",
            "position_x": 0,
            "position_y": 0,
            "agent_types": None,
        }
    )
    a.config["poisoned"] = True
    assert b.config == {}
