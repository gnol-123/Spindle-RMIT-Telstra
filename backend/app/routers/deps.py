"""Shared route dependencies."""

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from app.config import settings
from app.repositories.environment_repo import EnvironmentRepository
from app.repositories.preview_repo import PreviewRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.tool_repo import ToolRepository
from app.routers.auth import CurrentAuth
from app.services.supabase import get_service_client, get_user_client

log = logging.getLogger(__name__)


def get_project_repository(auth: CurrentAuth) -> ProjectRepository:
    """Build a repository scoped to the caller.

    The client carries the caller's own token, so RLS applies to every query it
    makes. A dependency rather than a plain call so tests can override it.
    """
    return ProjectRepository(get_user_client(auth.token), auth.user.id)


ProjectRepo = Annotated[ProjectRepository, Depends(get_project_repository)]


def get_tool_repository(auth: CurrentAuth) -> ToolRepository:
    """Tool repository scoped to the caller, so RLS applies."""
    return ToolRepository(get_user_client(auth.token), auth.user.id)


ToolRepo = Annotated[ToolRepository, Depends(get_tool_repository)]


def get_environment_repository(auth: CurrentAuth) -> EnvironmentRepository:
    """Environment repository scoped to the caller, so RLS applies."""
    return EnvironmentRepository(get_user_client(auth.token), auth.user.id)


EnvRepo = Annotated[EnvironmentRepository, Depends(get_environment_repository)]


def get_preview_repository(auth: CurrentAuth) -> PreviewRepository:
    """Preview repository scoped to the caller, so RLS applies."""
    return PreviewRepository(get_user_client(auth.token))


PreviewRepo = Annotated[PreviewRepository, Depends(get_preview_repository)]


@dataclass(frozen=True)
class TurnRepositories:
    """The three repositories a turn runs on, bound to one verified user."""

    project: ProjectRepository
    tool: ToolRepository
    env: EnvironmentRepository
    user_id: str
    preview: PreviewRepository | None = None


_warned_no_service_key = False


def get_turn_repositories(auth: CurrentAuth) -> TurnRepositories:
    """Repositories for the turn itself, not the pre-flight.

    Service client, bound to the id the bearer token already proved: a turn
    can outlive the token (detached stream, nested agent runs), and every
    repository filters by owner_id, so the service client sees exactly what
    RLS would. Falls back to the user's token when no service key is set.
    """
    global _warned_no_service_key
    if settings.supabase_service_key:
        return service_turn_repositories(auth.user.id)
    client = get_user_client(auth.token)
    if not _warned_no_service_key:
        log.warning("SUPABASE_SERVICE_KEY unset; long turns may fail when the token expires")
        _warned_no_service_key = True
    return _turn_repositories(client, auth.user.id)


def service_turn_repositories(uid: str) -> TurnRepositories:
    """Turn repositories for a user with no request in hand (recovery)."""
    return _turn_repositories(get_service_client(), uid)


def _turn_repositories(client, uid: str) -> TurnRepositories:
    return TurnRepositories(
        project=ProjectRepository(client, uid),
        tool=ToolRepository(client, uid),
        env=EnvironmentRepository(client, uid),
        user_id=uid,
        preview=PreviewRepository(client),
    )


TurnRepos = Annotated[TurnRepositories, Depends(get_turn_repositories)]
