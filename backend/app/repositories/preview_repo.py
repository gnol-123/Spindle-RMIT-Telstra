"""Agent-published previews: one row per (environment, port).

Replaces the previews.json each sandbox used to hold. Takes whichever client
the caller has; the table's RLS follows the parent project's owner.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_COLUMNS = (
    "id, project_id, env_node_id, port, path, title, agent_node_id, thumbnail_path, created_at"
)


@dataclass(frozen=True)
class PreviewRow:
    id: str
    project_id: str
    env_node_id: str
    port: int
    path: str
    title: str
    agent_node_id: str | None
    thumbnail_path: str | None
    created_at: str


def _to_row(r: dict[str, Any]) -> PreviewRow:
    return PreviewRow(
        id=r["id"],
        project_id=r["project_id"],
        env_node_id=r["env_node_id"],
        port=r["port"],
        path=r.get("path") or "/",
        title=r["title"],
        agent_node_id=r.get("agent_node_id"),
        thumbnail_path=r.get("thumbnail_path"),
        created_at=r["created_at"],
    )


class PreviewRepository:
    def __init__(self, client: Any) -> None:
        self._db = client

    def upsert(
        self,
        project_id: str,
        env_node_id: str,
        port: int,
        path: str,
        title: str,
        agent_node_id: str | None,
    ) -> str:
        """Add or replace the preview for a port. A republish counts as newest."""
        rows = (
            self._db.table("previews")
            .upsert(
                {
                    "project_id": project_id,
                    "env_node_id": env_node_id,
                    "port": port,
                    "path": path,
                    "title": title,
                    "agent_node_id": agent_node_id,
                    "created_at": datetime.now(UTC).isoformat(),
                },
                on_conflict="env_node_id,port",
            )
            .execute()
        ).data
        return rows[0]["id"]

    def list_for_env(self, env_node_id: str) -> list[PreviewRow]:
        """Newest first."""
        rows = (
            self._db.table("previews")
            .select(_COLUMNS)
            .eq("env_node_id", env_node_id)
            .order("created_at", desc=True)
            .execute()
        ).data
        return [_to_row(r) for r in rows]

    def newest_for_env(self, env_node_id: str) -> PreviewRow | None:
        rows = (
            self._db.table("previews")
            .select(_COLUMNS)
            .eq("env_node_id", env_node_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        ).data
        return _to_row(rows[0]) if rows else None

    def delete(self, env_node_id: str, port: int) -> None:
        (
            self._db.table("previews")
            .delete()
            .eq("env_node_id", env_node_id)
            .eq("port", port)
            .execute()
        )

    def set_thumbnail(self, preview_id: str, path: str) -> None:
        self._db.table("previews").update({"thumbnail_path": path}).eq("id", preview_id).execute()
