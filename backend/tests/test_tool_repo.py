from unittest.mock import MagicMock

from app.repositories.tool_repo import ToolRepository, ToolType


def _client_returning(rows):
    client = MagicMock()
    chain = client.table.return_value
    for method in ("select", "eq", "limit", "order", "insert", "update"):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = MagicMock(data=rows)
    return client


def test_get_tool_type_maps_row():
    client = _client_returning(
        [
            {
                "id": "t1",
                "slug": "brave_search",
                "name": "Brave Search",
                "description": "Web search",
                "config_schema": {"fields": []},
                "secret_fields": ["api_key"],
            }
        ]
    )
    repo = ToolRepository(client, "user-1")
    got = repo.get_tool_type("brave_search")
    assert got == ToolType(
        id="t1",
        slug="brave_search",
        name="Brave Search",
        description="Web search",
        config_schema={"fields": []},
        secret_fields=["api_key"],
    )


def test_get_tool_type_missing_returns_none():
    repo = ToolRepository(_client_returning([]), "user-1")
    assert repo.get_tool_type("nope") is None
