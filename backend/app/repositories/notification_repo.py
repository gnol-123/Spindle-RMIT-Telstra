"""Turn notifications and Web Push subscriptions for one user.

Takes the caller's client; RLS applies, and every query also filters by owner.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

_COLUMNS = (
    "id, project_id, node_id, message_id, status, node_name, project_name, "
    "nested, excerpt, read_at, created_at"
)

# A subscription counts as foregrounded this long after its last ping.
_VISIBLE_FOR = timedelta(seconds=60)


@dataclass(frozen=True)
class NotificationRow:
    id: str
    project_id: str
    node_id: str
    message_id: str
    status: str
    node_name: str
    project_name: str
    nested: bool
    excerpt: str | None
    read_at: str | None
    created_at: str


def _to_row(r: dict[str, Any]) -> NotificationRow:
    return NotificationRow(
        id=r["id"],
        project_id=r["project_id"],
        node_id=r["node_id"],
        message_id=r["message_id"],
        status=r["status"],
        node_name=r["node_name"],
        project_name=r["project_name"],
        nested=r["nested"],
        excerpt=r.get("excerpt"),
        read_at=r.get("read_at"),
        created_at=r["created_at"],
    )


class NotificationRepository:
    def __init__(self, client: Any, uid: str) -> None:
        self._db = client
        self._uid = uid

    def list_recent(self, limit: int) -> list[NotificationRow]:
        """Newest first."""
        rows = (
            self._db.table("notifications")
            .select(_COLUMNS)
            .eq("owner_id", self._uid)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        ).data
        return [_to_row(r) for r in rows]

    def mark_read(self, project_id: str | None) -> int:
        """Read every unread row, or only one project's. Returns the count."""
        q = (
            self._db.table("notifications")
            .update({"read_at": datetime.now(UTC).isoformat()})
            .eq("owner_id", self._uid)
            .is_("read_at", "null")
        )
        if project_id:
            q = q.eq("project_id", project_id)
        return len(q.execute().data)

    def upsert_subscription(self, endpoint: str, p256dh: str, auth: str, user_agent: str) -> str:
        return (
            self._db.rpc(
                "upsert_push_subscription",
                {
                    "p_endpoint": endpoint,
                    "p_p256dh": p256dh,
                    "p_auth": auth,
                    "p_user_agent": user_agent,
                },
            ).execute()
        ).data

    def set_visible(self, endpoint: str, visible: bool) -> None:
        now = datetime.now(UTC)
        (
            self._db.table("push_subscriptions")
            .update(
                {
                    "visible_until": (now + _VISIBLE_FOR).isoformat() if visible else None,
                    "updated_at": now.isoformat(),
                }
            )
            .eq("endpoint", endpoint)
            .eq("owner_id", self._uid)
            .execute()
        )

    def delete_subscription(self, endpoint: str) -> None:
        (
            self._db.table("push_subscriptions")
            .delete()
            .eq("endpoint", endpoint)
            .eq("owner_id", self._uid)
            .execute()
        )
