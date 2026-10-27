"""Data access for projects, agent nodes and their conversations.

Every method filters on owner explicitly as well as relying on RLS, so a
misconfigured policy or a service-role key cannot cross a tenant boundary.

The Supabase client is synchronous, so async callers must dispatch these
through ``anyio.to_thread.run_sync``.
"""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from app.repositories.catalog_cache import cached
from app.repositories.environment_repo import EnvNode, _to_env_node
from app.repositories.tool_repo import ToolNode, _to_tool_node

# Postgres unique_violation, surfaced by PostgREST as `code`.
_UNIQUE_VIOLATION = "23505"

# How much history to replay into the model by default.
DEFAULT_HISTORY_LIMIT = 50


class DuplicateProjectName(Exception):
    """A user already has a project with this name."""


class DuplicateEdge(Exception):
    """An arrow of this kind already joins these two nodes."""


@dataclass(frozen=True)
class AgentType:
    """A row from the agent_types catalog."""

    id: str
    slug: str
    name: str
    description: str | None
    system_prompt: str
    model: str
    # Preset slugs wired on creation. Unknown slugs are skipped by the router.
    default_presets: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    # Set when the frontend has uploaded a canvas screenshot.
    canvas_snapshot_at: str | None = None
    # Newest preview thumbnail path under the project's own folder.
    thumbnail_path: str | None = None


@dataclass(frozen=True)
class Node:
    """One box on a canvas. Agent fields are empty for a tool node."""

    id: str
    project_id: str
    name: str
    agent_type_id: str | None
    system_prompt: str
    model: str
    tool_policy: str
    position_x: float
    position_y: float
    kind: str = "agent"
    # None for a tool node row (agent_types join is null), or if the join
    # itself is absent from the select.
    agent_slug: str | None = None
    # Lifecycle, for environment boxes. get_agent_node does not select these,
    # so the defaults have to read as a live agent.
    status: str = "ready"
    status_detail: str | None = None
    # Environment identity: runtime, role, sandbox id. Empty for other kinds.
    config: dict[str, Any] = field(default_factory=dict)
    # Per agent type model request cap. None = settings.turn_request_limit.
    request_limit: int | None = None
    # Embedded by get_agent_node only. None = not selected or not created yet.
    conversation_id: str | None = None


@dataclass(frozen=True)
class InboundContext:
    """A context summary and its source agent."""

    source_node_id: str
    source_node_name: str
    summary: str


@dataclass(frozen=True)
class Inbound:
    """Everything wired into an agent, from one edges read."""

    context: list[InboundContext]
    tool_nodes: list[ToolNode]
    env_nodes: list[EnvNode]


_INBOUND_COLUMNS = (
    "kind, summary, source_node_id, nodes!edges_source_node_id_fkey("
    "id, project_id, name, kind, owner_id, tool_type_id, config, status, status_detail,"
    " tool_policy, position_x, position_y, tool_types(slug))"
)


@dataclass(frozen=True)
class Message:
    id: str
    role: str
    content: str
    seq: int
    status: str
    created_at: str
    # Ordered tool events for the bubble. Empty on user rows.
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # Agent node that wrote this user row (canvas run_agent). None = the user.
    sender_node_id: str | None = None
    # add_message returned an existing client_token row; nothing was inserted.
    replayed: bool = False
    # Selected by RUN_COLUMNS reads only, never by list selects.
    heartbeat_at: str | None = None
    resume_count: int = 0
    parent_message_id: str | None = None
    # A user stop no live driver received yet. Recovery and the heartbeat honour it.
    cancel_requested: bool = False


_MESSAGE_COLUMNS = "id, role, content, seq, status, created_at, tool_calls, sender_node_id"
# Plus what the recovery loop and run_agent rejoin compare on.
RUN_COLUMNS = f"{_MESSAGE_COLUMNS}, heartbeat_at, resume_count, parent_message_id, cancel_requested"


def _to_message(row: dict[str, Any]) -> Message:
    return Message(
        id=row["id"],
        role=row["role"],
        content=row["content"],
        seq=row["seq"],
        status=row["status"],
        created_at=row["created_at"],
        tool_calls=row.get("tool_calls") or [],
        sender_node_id=row.get("sender_node_id"),
        heartbeat_at=row.get("heartbeat_at"),
        resume_count=row.get("resume_count") or 0,
        parent_message_id=row.get("parent_message_id"),
        cancel_requested=bool(row.get("cancel_requested")),
    )


@dataclass(frozen=True)
class UsageTotal:
    """Token totals for one project on one model.

    Per model because `nodes.model` is an override: one project can run
    several, and counts are neither comparable nor equally priced across them.
    `reasoning_tokens` is a subset of `output_tokens`, not an addend.
    """

    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    requests: int
    message_count: int


def _to_usage_total(row: dict[str, Any]) -> UsageTotal:
    return UsageTotal(
        model=row["model"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        reasoning_tokens=row["reasoning_tokens"],
        cache_read_tokens=row["cache_read_tokens"],
        cache_write_tokens=row["cache_write_tokens"],
        requests=row["requests"],
        message_count=row["message_count"],
    )


@dataclass(frozen=True)
class Edge:
    """A connection between two nodes on the canvas."""

    id: str
    source_node_id: str
    target_node_id: str
    kind: str
    summary: str | None
    summarised_through_seq: int | None
    summary_updated_at: str | None
    summary_max_words: int


def _to_edge(row: dict[str, Any]) -> Edge:
    return Edge(
        id=row["id"],
        source_node_id=row["source_node_id"],
        target_node_id=row["target_node_id"],
        kind=row["kind"],
        summary=row.get("summary"),
        summarised_through_seq=row.get("summarised_through_seq"),
        summary_updated_at=row.get("summary_updated_at"),
        summary_max_words=row.get("summary_max_words", 200),
    )


class ProjectRepository:
    """PostgREST access scoped to one user."""

    def __init__(self, client: Client, user_id: str) -> None:
        self._db = client
        self._user_id = user_id

    # -- catalog ------------------------------------------------------------

    def list_agent_types(self) -> list[AgentType]:
        return list(cached(("list_agent_types",), self._fetch_agent_types))

    def get_agent_type(self, slug: str) -> AgentType | None:
        return cached(("get_agent_type", slug), lambda: self._fetch_agent_type(slug))

    def _fetch_agent_types(self) -> list[AgentType]:
        rows = (
            self._db.table("agent_types")
            .select("id, slug, name, description, system_prompt, model, default_presets")
            .eq("is_active", True)
            .order("sort_order")
            .execute()
        ).data
        return [
            AgentType(
                id=r["id"],
                slug=r["slug"],
                name=r["name"],
                description=r.get("description"),
                system_prompt=r["system_prompt"],
                model=r["model"],
                default_presets=r.get("default_presets") or [],
            )
            for r in rows
        ]

    def _fetch_agent_type(self, slug: str) -> AgentType | None:
        rows = (
            self._db.table("agent_types")
            .select("id, slug, name, description, system_prompt, model, default_presets")
            .eq("slug", slug)
            .eq("is_active", True)
            .limit(1)
            .execute()
        ).data
        if not rows:
            return None
        r = rows[0]
        return AgentType(
            id=r["id"],
            slug=r["slug"],
            name=r["name"],
            description=r.get("description"),
            system_prompt=r["system_prompt"],
            model=r["model"],
            default_presets=r.get("default_presets") or [],
        )

    # -- projects -----------------------------------------------------------

    def create_project(self, name: str, description: str | None = None) -> Project:
        """Create a project. Names are unique per user."""
        try:
            rows = (
                self._db.table("projects")
                .insert({"owner_id": self._user_id, "name": name, "description": description})
                .execute()
            ).data
        except APIError as exc:
            if exc.code == _UNIQUE_VIOLATION:
                raise DuplicateProjectName(name) from exc
            raise
        return Project(id=rows[0]["id"], name=rows[0]["name"])

    def list_projects(self) -> list[Project]:
        """Projects with their newest preview thumbnail, one query."""
        rows = (
            self._db.table("projects")
            .select("id, name, canvas_snapshot_at, previews(thumbnail_path, created_at)")
            .eq("owner_id", self._user_id)
            .is_("archived_at", "null")
            .not_.is_("previews.thumbnail_path", "null")
            .order("created_at", desc=True)
            .order("created_at", desc=True, foreign_table="previews")
            .limit(1, foreign_table="previews")
            .execute()
        ).data
        out = []
        for r in rows:
            thumb = next((v["thumbnail_path"] for v in r.get("previews") or []), None)
            # Column is user-writable: only paths under the project's own folder.
            if thumb is not None and not thumb.startswith(f"{r['id']}/"):
                thumb = None
            out.append(
                Project(
                    id=r["id"],
                    name=r["name"],
                    canvas_snapshot_at=r.get("canvas_snapshot_at"),
                    thumbnail_path=thumb,
                )
            )
        return out

    def get_project(self, project_id: str) -> Project | None:
        rows = (
            self._db.table("projects")
            .select("id, name")
            .eq("id", project_id)
            .eq("owner_id", self._user_id)
            .limit(1)
            .execute()
        ).data
        return Project(id=rows[0]["id"], name=rows[0]["name"]) if rows else None

    def rename_project(self, project_id: str, name: str) -> Project | None:
        """Rename an owned project. None when missing or not the caller's."""
        try:
            rows = (
                self._db.table("projects")
                .update({"name": name})
                .eq("id", project_id)
                .eq("owner_id", self._user_id)
                .execute()
            ).data
        except APIError as exc:
            if exc.code == _UNIQUE_VIOLATION:
                raise DuplicateProjectName(name) from exc
            raise
        return Project(id=rows[0]["id"], name=rows[0]["name"]) if rows else None

    def set_canvas_snapshot_at(self, project_id: str) -> None:
        (
            self._db.table("projects")
            .update({"canvas_snapshot_at": datetime.now(UTC).isoformat()})
            .eq("id", project_id)
            .eq("owner_id", self._user_id)
            .execute()
        )

    def delete_project(self, project_id: str) -> bool:
        """Delete a project and everything on its canvas.

        One statement: `on delete cascade` takes the nodes, edges,
        conversations and messages with it.
        """
        rows = (
            self._db.table("projects")
            .delete()
            .eq("id", project_id)
            .eq("owner_id", self._user_id)
            .execute()
        ).data
        return bool(rows)

    # -- nodes --------------------------------------------------------------

    def create_node(
        self,
        project_id: str,
        agent_type_id: str,
        name: str,
        *,
        position_x: float = 0,
        position_y: float = 0,
        tool_policy: str = "ask",
        with_conversation: bool = True,
    ) -> str:
        """Provision an agent box and give it a conversation.

        The conversation is created here rather than lazily on first message,
        so a freshly dropped box is immediately chattable. with_conversation=False
        leaves it to the caller (create_conversation), to overlap other writes.
        """
        rows = (
            self._db.table("nodes")
            .insert(
                {
                    "project_id": project_id,
                    # Satisfies the defensive WITH CHECK; a trigger overwrites
                    # it from the parent project, so a forged value is inert.
                    "owner_id": self._user_id,
                    "kind": "agent",
                    "agent_type_id": agent_type_id,
                    "name": name,
                    "position_x": position_x,
                    "position_y": position_y,
                    "status": "ready",
                    "tool_policy": tool_policy,
                }
            )
            .execute()
        ).data
        node_id = rows[0]["id"]
        if with_conversation:
            self.create_conversation(node_id, project_id)
        return node_id

    def update_node(self, node_id: str, changes: dict[str, Any]) -> Node | None:
        """Apply a partial update to an agent node.
        Only allowed fields are modifiable;
        {"name", "position_x", "position_y", "tool_policy", "model"}
        """
        allowed = {"name", "position_x", "position_y", "tool_policy", "model"}
        payload = {k: v for k, v in changes.items() if k in allowed and v is not None}
        if payload.get("model") == "":
            payload["model"] = None
        if not payload:
            # A drag that ends where it started is a no-op, not an error.
            return self.get_agent_node(node_id)

        rows = (
            self._db.table("nodes")
            .update(payload)
            .eq("id", node_id)
            .eq("owner_id", self._user_id)
            .eq("kind", "agent")
            .execute()
        ).data
        return self.get_agent_node(node_id) if rows else None

    def delete_node(self, node_id: str) -> list[str]:
        """
        Remove a node of any kind owned by the caller.
        Does not filter by kind, blanket delete over
        Every kind of node and cascades to any child objects e.g. conversations, secrets ...

        Deleting an agent also sweeps the project's now-orphaned tool nodes.
        Returns every node id removed. Empty means nothing matched.
        """
        # kind and project_id are gone after the delete, so read them first.
        found = (
            self._db.table("nodes")
            .select("kind, project_id")
            .eq("id", node_id)
            .eq("owner_id", self._user_id)
            .limit(1)
            .execute()
        ).data
        if not found:
            return []

        rows = (
            self._db.table("nodes")
            .delete()
            .eq("id", node_id)
            .eq("owner_id", self._user_id)
            .execute()
        ).data
        if not rows:
            return []
        if found[0]["kind"] != "agent":
            return [node_id]
        return [node_id, *self._sweep_orphan_tools(found[0]["project_id"])]

    def _sweep_orphan_tools(self, project_id: str) -> list[str]:
        """Delete the project's tool nodes that no edge references any more.

        ponytail: two reads and a Python subtraction, PostgREST has no
        anti-join. Canvases are small. Move to an RPC if one ever is not.
        """
        tool_ids = {
            r["id"]
            for r in (
                self._db.table("nodes")
                .select("id")
                .eq("project_id", project_id)
                .eq("owner_id", self._user_id)
                .eq("kind", "tool")
                .execute()
            ).data
        }
        if not tool_ids:
            return []

        attached: set[str] = set()
        for edge in (
            self._db.table("edges")
            .select("source_node_id, target_node_id")
            .eq("project_id", project_id)
            .eq("owner_id", self._user_id)
            .execute()
        ).data:
            attached.add(edge["source_node_id"])
            attached.add(edge["target_node_id"])

        orphans = sorted(tool_ids - attached)
        if orphans:
            (
                self._db.table("nodes")
                .delete()
                .in_("id", orphans)
                .eq("owner_id", self._user_id)
                .execute()
            )
        return orphans

    def list_nodes(self, project_id: str) -> list[Node]:
        rows = (
            self._db.table("nodes")
            .select(
                "id, project_id, name, agent_type_id, tool_policy, kind,"
                " position_x, position_y, status, status_detail, config, model,"
                " agent_types(slug, system_prompt, model, request_limit)"
            )
            .eq("project_id", project_id)
            .eq("owner_id", self._user_id)
            .order("created_at")
            .execute()
        ).data
        return [_to_node(r) for r in rows]

    def get_agent_node(self, node_id: str) -> Node | None:
        """Load one agent box together with its template's prompt and model."""
        rows = (
            self._db.table("nodes")
            .select(
                "id, project_id, name, agent_type_id, tool_policy,"
                " position_x, position_y, model,"
                " agent_types(slug, system_prompt, model, request_limit), conversations(id)"
            )
            .eq("id", node_id)
            .eq("owner_id", self._user_id)
            .eq("kind", "agent")
            .limit(1)
            .execute()
        ).data
        return _to_node(rows[0]) if rows else None

    # -- edges --------------------------------------------------------------

    def create_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        kind: str = "context",
        summary_max_words: int | None = None,
    ) -> Edge:
        """
        Connect two nodes on the canvas.
        Returns the edge object.
        """
        try:
            payload = {
                "owner_id": self._user_id,
                "source_node_id": source_node_id,
                "target_node_id": target_node_id,
                "kind": kind,
            }
            if summary_max_words is not None:
                payload["summary_max_words"] = summary_max_words
            rows = self._db.table("edges").insert(payload).execute().data
        except APIError as exc:
            if exc.code == _UNIQUE_VIOLATION:
                raise DuplicateEdge(f"{source_node_id} -> {target_node_id} ({kind})") from exc
            raise
        return _to_edge(rows[0])

    def create_edges(self, edges: list[tuple[str, str, str]]) -> list[Edge]:
        """Connect many (source, target, kind) pairs in one request. All or nothing."""
        try:
            rows = (
                self._db.table("edges")
                .insert(
                    [
                        {
                            "owner_id": self._user_id,
                            "source_node_id": src,
                            "target_node_id": tgt,
                            "kind": kind,
                        }
                        for src, tgt, kind in edges
                    ]
                )
                .execute()
                .data
            )
        except APIError as exc:
            if exc.code == _UNIQUE_VIOLATION:
                raise DuplicateEdge(f"{len(edges)} edges") from exc
            raise
        return [_to_edge(r) for r in rows]

    def node_kinds(self, node_ids: list[str]) -> dict[str, tuple[str, str]]:
        """node id -> (project_id, kind) for any kind, one query. Missing ids dropped."""
        rows = (
            self._db.table("nodes")
            .select("id, project_id, kind")
            .in_("id", node_ids)
            .eq("owner_id", self._user_id)
            .execute()
        ).data
        return {r["id"]: (r["project_id"], r["kind"]) for r in rows}

    def get_tool_policy(self, node_id: str) -> str | None:
        """One node's tool_policy, any kind. None when it is gone."""
        rows = (
            self._db.table("nodes")
            .select("tool_policy")
            .eq("id", node_id)
            .eq("owner_id", self._user_id)
            .limit(1)
            .execute()
        ).data
        return rows[0]["tool_policy"] if rows else None

    def tool_policies(self, node_ids: list[str]) -> dict[str, tuple[str, str]]:
        """node id -> (kind, tool_policy), one query. Missing ids dropped."""
        rows = (
            self._db.table("nodes")
            .select("id, kind, tool_policy")
            .in_("id", node_ids)
            .eq("owner_id", self._user_id)
            .execute()
        ).data
        return {r["id"]: (r["kind"], r["tool_policy"]) for r in rows}

    def list_edges(self, project_id: str) -> list[Edge]:
        """Every edge on a project's canvas."""
        rows = (
            self._db.table("edges")
            .select(
                "id, source_node_id, target_node_id, kind, summary,"
                " summarised_through_seq, summary_updated_at, summary_max_words"
            )
            .eq("project_id", project_id)
            .eq("owner_id", self._user_id)
            .execute()
        ).data
        return [_to_edge(r) for r in rows]

    def list_outbound_context_edges(self, node_id: str) -> list[Edge]:
        """Context edges leaving one node: what a fresh reply should re-summarise."""
        rows = (
            self._db.table("edges")
            .select(
                "id, source_node_id, target_node_id, kind, summary,"
                " summarised_through_seq, summary_updated_at, summary_max_words"
            )
            .eq("source_node_id", node_id)
            .eq("kind", "context")
            .eq("owner_id", self._user_id)
            .execute()
        ).data
        return [_to_edge(r) for r in rows]

    def get_edge(self, edge_id: str) -> Edge | None:
        """One edge, if it belongs to the caller."""
        rows = (
            self._db.table("edges")
            .select(
                "id, source_node_id, target_node_id, kind, summary,"
                " summarised_through_seq, summary_updated_at, summary_max_words"
            )
            .eq("id", edge_id)
            .eq("owner_id", self._user_id)
            .limit(1)
            .execute()
        ).data
        return _to_edge(rows[0]) if rows else None

    def update_edge_summary(self, edge_id: str, summary: str, through_seq: int) -> Edge | None:
        """Store a freshly generated summary and how far up the source it covers."""
        rows = (
            self._db.table("edges")
            .update(
                {
                    "summary": summary,
                    "summarised_through_seq": through_seq,
                    "summary_updated_at": datetime.now(UTC).isoformat(),
                }
            )
            .eq("id", edge_id)
            .eq("owner_id", self._user_id)
            .eq("kind", "context")
            .execute()
        ).data
        return _to_edge(rows[0]) if rows else None

    def list_inbound_context(self, node_id: str) -> list[InboundContext]:
        """Summaries feeding this node, each named by its source agent.

        Joined by constraint name: `edges` has two foreign keys to `nodes`.
        Edges with no summary are omitted.
        """
        rows = (
            self._db.table("edges")
            .select("source_node_id, summary, nodes!edges_source_node_id_fkey(name)")
            .eq("target_node_id", node_id)
            .eq("kind", "context")
            .eq("owner_id", self._user_id)
            .execute()
        ).data
        out = []
        for r in rows:
            summary = (r.get("summary") or "").strip()
            if not summary:
                continue
            node = r.get("nodes") or {}
            out.append(
                InboundContext(
                    source_node_id=r["source_node_id"],
                    source_node_name=node.get("name", "another agent"),
                    summary=summary,
                )
            )
        return out

    def list_inbound(self, node_id: str) -> Inbound:
        """list_inbound_context plus inbound tool and environment nodes, one query."""
        rows = (
            self._db.table("edges")
            .select(_INBOUND_COLUMNS)
            .eq("target_node_id", node_id)
            .in_("kind", ["context", "tool", "environment"])
            .eq("owner_id", self._user_id)
            .execute()
        ).data
        out = Inbound([], [], [])
        for r in rows:
            node = r.get("nodes") or {}
            if r["kind"] == "context":
                summary = (r.get("summary") or "").strip()
                if summary:
                    out.context.append(
                        InboundContext(
                            source_node_id=r["source_node_id"],
                            source_node_name=node.get("name", "another agent"),
                            summary=summary,
                        )
                    )
            elif node.get("owner_id") != self._user_id or node.get("kind") != r["kind"]:
                continue
            elif r["kind"] == "tool":
                out.tool_nodes.append(_to_tool_node(node))
            else:
                out.env_nodes.append(_to_env_node(node))
        return out

    def list_inbound_tool_node_ids(self, node_id: str) -> list[str]:
        """Tool nodes whose arrows point at this agent."""
        rows = (
            self._db.table("edges")
            .select("source_node_id")
            .eq("target_node_id", node_id)
            .eq("kind", "tool")
            .eq("owner_id", self._user_id)
            .execute()
        ).data
        return [r["source_node_id"] for r in rows]

    def list_inbound_environment_node_ids(self, node_id: str) -> list[str]:
        """Environment nodes whose arrows point at this agent."""
        rows = (
            self._db.table("edges")
            .select("source_node_id")
            .eq("target_node_id", node_id)
            .eq("kind", "environment")
            .eq("owner_id", self._user_id)
            .execute()
        ).data
        return [r["source_node_id"] for r in rows]

    def delete_edge(self, edge_id: str) -> bool:
        rows = (
            self._db.table("edges")
            .delete()
            .eq("id", edge_id)
            .eq("owner_id", self._user_id)
            .execute()
        ).data
        return bool(rows)

    def get_conversation_for_node(self, node_id: str) -> str | None:
        rows = (
            self._db.table("conversations")
            .select("id")
            .eq("node_id", node_id)
            .eq("owner_id", self._user_id)
            .limit(1)
            .execute()
        ).data
        return rows[0]["id"] if rows else None

    def conversation_ids_for_nodes(self, node_ids: list[str]) -> dict[str, str]:
        """node id -> conversation id, one query. Nodes without one are dropped."""
        rows = (
            self._db.table("conversations")
            .select("id, node_id")
            .in_("node_id", node_ids)
            .eq("owner_id", self._user_id)
            .execute()
        ).data
        return {r["node_id"]: r["id"] for r in rows}

    def get_or_create_conversation(self, node_id: str, project_id: str) -> str:
        """Return the node's conversation, creating it if it is somehow absent.

        Normally created alongside the node; this covers nodes provisioned
        before that, and races between two first messages.
        """
        existing = self.get_conversation_for_node(node_id)
        if existing is not None:
            return existing
        return self.create_conversation(node_id, project_id)

    def create_conversation(self, node_id: str, project_id: str) -> str:
        try:
            rows = (
                self._db.table("conversations")
                .insert(
                    {
                        "node_id": node_id,
                        "project_id": project_id,
                        "owner_id": self._user_id,
                    }
                )
                .execute()
            ).data
            if rows:
                return rows[0]["id"]
        except APIError as exc:
            if exc.code != _UNIQUE_VIOLATION:
                raise

        winner = self.get_conversation_for_node(node_id)
        if winner is None:
            raise RuntimeError("conversation could not be created or found")
        return winner

    # -- messages -----------------------------------------------------------

    def list_messages(
        self,
        conversation_id: str,
        limit: int = DEFAULT_HISTORY_LIMIT,
        *,
        before_seq: int | None = None,
    ) -> list[Message]:
        """Return the most recent ``limit`` messages, oldest first.

        Ordered descending then reversed: a plain ascending ``limit`` would
        return the *oldest* N and silently freeze context after N turns.
        """
        q = (
            self._db.table("messages")
            .select(_MESSAGE_COLUMNS)
            .eq("conversation_id", conversation_id)
            .eq("owner_id", self._user_id)
        )
        if before_seq is not None:
            q = q.lt("seq", before_seq)
        rows = q.order("seq", desc=True).limit(limit).execute().data
        return [_to_message(r) for r in reversed(rows)]

    def list_messages_after(
        self, conversation_id: str, after_seq: int = 0, limit: int = 500
    ) -> list[Message]:
        """Messages past a seq, oldest first. For polling a transcript."""
        rows = (
            self._db.table("messages")
            .select(_MESSAGE_COLUMNS)
            .eq("conversation_id", conversation_id)
            .eq("owner_id", self._user_id)
            .gt("seq", after_seq)
            .order("seq")
            .limit(limit)
            .execute()
        ).data
        return [_to_message(r) for r in rows]

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        client_token: str | None = None,
        model: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        cache_read_tokens: int | None = None,
        cache_write_tokens: int | None = None,
        requests: int | None = None,
        status: str = "complete",
        error: str | None = None,
        sender_node_id: str | None = None,
        heartbeat_at: str | None = None,
        parent_message_id: str | None = None,
    ) -> Message:
        """
        Insert one message, returning the stored row.
        """
        payload: dict[str, Any] = {
            "conversation_id": conversation_id,
            "owner_id": self._user_id,
            "role": role,
            "content": content,
            "status": status,
        }
        for key, value in (
            ("client_token", client_token),
            ("model", model),
            ("input_tokens", input_tokens),
            ("output_tokens", output_tokens),
            ("reasoning_tokens", reasoning_tokens),
            ("cache_read_tokens", cache_read_tokens),
            ("cache_write_tokens", cache_write_tokens),
            ("requests", requests),
            ("error", error),
            ("sender_node_id", sender_node_id),
            ("heartbeat_at", heartbeat_at),
            ("parent_message_id", parent_message_id),
        ):
            if value is not None:
                payload[key] = value

        try:
            rows = self._db.table("messages").insert(payload).execute().data
        except APIError as exc:
            if exc.code == _UNIQUE_VIOLATION and client_token is not None:
                existing = self.find_by_client_token(conversation_id, client_token)
                if existing is not None:
                    return replace(existing, replayed=True)
            raise

        return _to_message(rows[0])

    def find_by_client_token(self, conversation_id: str, client_token: str) -> Message | None:
        rows = (
            self._db.table("messages")
            .select(_MESSAGE_COLUMNS)
            .eq("conversation_id", conversation_id)
            .eq("client_token", client_token)
            .eq("owner_id", self._user_id)
            .limit(1)
            .execute()
        ).data
        return _to_message(rows[0]) if rows else None

    _UPDATABLE = {
        "content",
        "tool_calls",
        "status",
        "error",
        "heartbeat_at",
        "model",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "requests",
        "resume_count",
        "parent_message_id",
    }

    def update_message(self, message_id: str, **fields: Any) -> Message:
        """Update a message in place. Only the driver calls this, on its own running row."""
        payload = {k: v for k, v in fields.items() if k in self._UPDATABLE}
        rows = (
            self._db.table("messages")
            .update(payload)
            .eq("id", message_id)
            .eq("owner_id", self._user_id)
            .execute()
        ).data
        return _to_message(rows[0])

    def claim_message(
        self, message_id: str, seen_heartbeat_at: str | None, **fields: Any
    ) -> Message | None:
        """Compare-and-set on a running row: lands only if the heartbeat is still the
        one the caller read. None = another instance got there first."""
        payload = {k: v for k, v in fields.items() if k in self._UPDATABLE}
        q = (
            self._db.table("messages")
            .update(payload)
            .eq("id", message_id)
            .eq("owner_id", self._user_id)
            .eq("status", "running")
        )
        if seen_heartbeat_at is None:
            q = q.is_("heartbeat_at", "null")
        else:
            q = q.eq("heartbeat_at", seen_heartbeat_at)
        rows = q.execute().data
        return _to_message(rows[0]) if rows else None

    def request_cancel(self, message_id: str) -> Message | None:
        """Flag a running row for whichever backend drives or resumes it. None = not running."""
        rows = (
            self._db.table("messages")
            .update({"cancel_requested": True})
            .eq("id", message_id)
            .eq("owner_id", self._user_id)
            .eq("status", "running")
            .execute()
        ).data
        return _to_message(rows[0]) if rows else None

    def get_run_message(self, message_id: str) -> Message | None:
        rows = (
            self._db.table("messages")
            .select(RUN_COLUMNS)
            .eq("id", message_id)
            .eq("owner_id", self._user_id)
            .limit(1)
            .execute()
        ).data
        return _to_message(rows[0]) if rows else None

    def latest_reply_to(self, conversation_id: str, user_seq: int) -> Message | None:
        """Newest assistant row answering one user row, i.e. before the next user row.

        A retry after a failed reply appends a second assistant row, not a user row.
        ponytail: scans 20 rows, plenty under the resume cap; widen if retries grow.
        """
        rows = (
            self._db.table("messages")
            .select(RUN_COLUMNS)
            .eq("conversation_id", conversation_id)
            .eq("owner_id", self._user_id)
            .gt("seq", user_seq)
            .order("seq")
            .limit(20)
            .execute()
        ).data
        reply = None
        for r in rows:
            if r["role"] == "user":
                break
            if r["role"] == "assistant":
                reply = r
        return _to_message(reply) if reply else None

    # -- checkpoints ------------------------------------------------------------

    def save_checkpoint(
        self,
        message_id: str,
        history: Any,
        content_len: int,
        events_len: int,
        *,
        clear_approvals: bool = False,
    ) -> None:
        row = {
            "message_id": message_id,
            "owner_id": self._user_id,
            "history": history,
            "content_len": content_len,
            "events_len": events_len,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if clear_approvals:
            row["approvals"] = None
        self._db.table("turn_checkpoints").upsert(row, on_conflict="message_id").execute()

    def set_approvals(self, message_id: str, approvals: dict[str, bool]) -> None:
        """On the message's checkpoint, if it has one."""
        (
            self._db.table("turn_checkpoints")
            .update({"approvals": approvals})
            .eq("message_id", message_id)
            .eq("owner_id", self._user_id)
            .execute()
        )

    def get_checkpoint(self, message_id: str) -> dict[str, Any] | None:
        rows = (
            self._db.table("turn_checkpoints")
            .select("history, content_len, events_len, approvals")
            .eq("message_id", message_id)
            .eq("owner_id", self._user_id)
            .limit(1)
            .execute()
        ).data
        return rows[0] if rows else None

    def clear_checkpoint(self, message_id: str) -> None:
        (
            self._db.table("turn_checkpoints")
            .delete()
            .eq("message_id", message_id)
            .eq("owner_id", self._user_id)
            .execute()
        )

    def latest_message_with_status(self, conversation_id: str, status: str) -> Message | None:
        # "*": the durability columns (see 20261027000001_schema.sql).
        rows = (
            self._db.table("messages")
            .select("*")
            .eq("conversation_id", conversation_id)
            .eq("owner_id", self._user_id)
            .eq("status", status)
            .order("seq", desc=True)
            .limit(1)
            .execute()
        ).data
        return _to_message(rows[0]) if rows else None

    def set_agent_status(self, node_id: str, status: str) -> None:
        (
            self._db.table("nodes")
            .update({"status": status})
            .eq("id", node_id)
            .eq("owner_id", self._user_id)
            .eq("kind", "agent")
            .execute()
        )

    # -- stale context ---------------------------------------------------------

    def get_conversation_head(self, node_id: str) -> int:
        """Last complete seq in this node's conversation. 0 when there is none.

        Complete rows only, matching what refresh_edge summarises through: a
        cancelled or running tail would otherwise read as permanently stale.
        Not conversations.message_count, which counts every row.
        """
        conversation_id = self.get_conversation_for_node(node_id)
        return self.conversation_head_seq(conversation_id) if conversation_id else 0

    def conversation_head_seq(self, conversation_id: str) -> int:
        """Last complete seq in one conversation. 0 when there is none."""
        seqs = (
            self._db.table("messages")
            .select("seq")
            .eq("owner_id", self._user_id)
            .eq("conversation_id", conversation_id)
            .eq("status", "complete")
            .order("seq", desc=True)
            .limit(1)
            .execute()
        ).data
        return seqs[0]["seq"] if seqs else 0

    # -- usage -----------------------------------------------------------------

    _USAGE_COLUMNS = (
        "model, input_tokens, output_tokens, reasoning_tokens, "
        "cache_read_tokens, cache_write_tokens, requests, message_count"
    )

    def get_usage(self, project_id: str) -> list[UsageTotal]:
        """This user's token totals in one project, one row per model.

        Read straight off the trigger-maintained rollup: no sum over messages.
        Scoped to the caller, so a shared project shows their own spend rather
        than everyone's.
        """
        rows = (
            self._db.table("usage_totals")
            .select(self._USAGE_COLUMNS)
            .eq("owner_id", self._user_id)
            .eq("project_id", project_id)
            .order("output_tokens", desc=True)
            .execute()
        ).data
        return [_to_usage_total(r) for r in rows]

    def get_user_usage(self) -> list[UsageTotal]:
        """This user's totals across every project, one row per model.

        What a per-user cap reads. Rows are already per (project, owner, model),
        so this re-aggregates by model in Python: the row count is bounded by
        projects x models, small enough that a database-side sum is not worth
        the view.
        """
        rows = (
            self._db.table("usage_totals")
            .select(self._USAGE_COLUMNS)
            .eq("owner_id", self._user_id)
            .execute()
        ).data

        summed = (
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "requests",
            "message_count",
        )
        by_model: dict[str, dict[str, Any]] = {}
        for r in rows:
            acc = by_model.get(r["model"])
            if acc is None:
                by_model[r["model"]] = dict(r)
                continue
            for key in summed:
                acc[key] += r[key]

        return sorted(
            (_to_usage_total(r) for r in by_model.values()),
            key=lambda t: t.output_tokens,
            reverse=True,
        )


def _to_node(row: dict[str, Any]) -> Node:
    """Flatten a node row joined to its agent_types template."""
    template = row.get("agent_types") or {}
    # One-to-one embed: an object, or a one-element list.
    conv = row.get("conversations") or {}
    if isinstance(conv, list):
        conv = conv[0] if conv else {}
    return Node(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        agent_type_id=row.get("agent_type_id"),
        system_prompt=template.get("system_prompt", ""),
        # Node override first, template second. Null means inherit.
        model=row.get("model") or template.get("model", ""),
        tool_policy=row.get("tool_policy", "ask"),
        position_x=row.get("position_x") or 0.0,
        position_y=row.get("position_y") or 0.0,
        kind=row.get("kind", "agent"),
        agent_slug=template.get("slug"),
        status=row.get("status") or "ready",
        status_detail=row.get("status_detail"),
        config=row.get("config") or {},
        request_limit=template.get("request_limit"),
        conversation_id=conv.get("id"),
    )
