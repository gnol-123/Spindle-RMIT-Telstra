"""Turn repositories run on the service client bound to the verified user."""

import logging

import app.routers.deps as deps
from app.repositories.environment_repo import EnvironmentRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.tool_repo import ToolRepository
from app.routers.auth import AuthContext, UserResponse


def _auth() -> AuthContext:
    return AuthContext(user=UserResponse(id="user-1", email="a@b.c"), token="jwt")  # noqa: S106


def test_service_backed_when_key_set(monkeypatch):
    monkeypatch.setattr(deps.settings, "supabase_service_key", "svc")
    monkeypatch.setattr(deps, "get_service_client", lambda: "SERVICE")
    monkeypatch.setattr(deps, "get_user_client", lambda jwt: "USER")

    repos = deps.get_turn_repositories(_auth())

    assert isinstance(repos.project, ProjectRepository)
    assert isinstance(repos.tool, ToolRepository)
    assert isinstance(repos.env, EnvironmentRepository)
    assert repos.project._db == "SERVICE"
    assert repos.project._user_id == "user-1"
    assert repos.user_id == "user-1"


def test_falls_back_to_user_client_without_key(monkeypatch, caplog):
    monkeypatch.setattr(deps.settings, "supabase_service_key", "")
    monkeypatch.setattr(deps, "get_user_client", lambda jwt: f"USER:{jwt}")

    with caplog.at_level(logging.WARNING):
        repos = deps.get_turn_repositories(_auth())

    assert repos.project._db == "USER:jwt"
    assert "long turns" in caplog.text.lower()


def test_request_limit_from_settings(monkeypatch):
    import app.workflows as workflows

    monkeypatch.setattr(workflows.settings, "turn_request_limit", 7)
    assert workflows._limits().request_limit == 7
