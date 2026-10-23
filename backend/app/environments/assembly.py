"""Environment nodes to toolsets for one agent turn.

Approval is gated per environment on its own tool_policy, where a tool
node's follows the agent's. Both are read per call. Stopping a shell command in someone's
repository and stopping one in a scratch space are different risks.
"""

import re
from collections.abc import Callable
from functools import partial

from anyio import to_thread
from pydantic_ai.toolsets import PrefixedToolset

from app.environments.base import WORKSPACE_ROOT, EnvContext
from app.environments.browser import BROWSER_TOOL_NAMES
from app.environments.lifecycle import ensure_provisioned
from app.environments.registry import get_spec
from app.repositories.environment_repo import EnvNode
from app.services import previews_storage
from app.tools.assembly import AssembledTools, LivePolicyToolset

# The tools every environment exposes. Named here so the approval backfill
# can register their prefixed forms without building a toolset.
ENV_TOOL_NAMES = (
    "run_command",
    "read_file",
    "write_file",
    "list_files",
    "next_free_port",
    "publish_preview",
)

_SAFE = re.compile(r"[^a-z0-9_]+")

# Function name cap
_MAX_STEM = 30


def env_prefix(name: str, node_id: str) -> str:
    """A per node prefix, so two environments cannot collide on tool names."""
    stem = _SAFE.sub("_", name.strip().lower()).strip("_")[:_MAX_STEM].rstrip("_")
    return f"{stem or 'env'}_{node_id[:8]}"


def _status_writer(env_repo, node_id: str):
    """Lets a tool mark its node errored without holding a repository."""

    async def write(status: str, detail: str | None) -> None:
        await to_thread.run_sync(lambda: env_repo.set_status(node_id, status, detail))

    return write


def _preview_recorder(preview_repo, project_id: str, node_id: str):
    """Lets publish_preview write its row without holding a repository."""

    async def record(entry: dict) -> None:
        await to_thread.run_sync(
            lambda: preview_repo.upsert(
                project_id,
                node_id,
                entry["port"],
                entry["path"],
                entry["title"],
                entry.get("agent_node_id"),
            )
        )

    return record


def _thumbnail_saver(preview_repo, project_id: str, node_id: str):
    """Lets a screenshot become the newest preview's thumbnail."""

    async def save(data: bytes) -> None:
        row = await to_thread.run_sync(preview_repo.newest_for_env, node_id)
        if row is None:
            return
        path = await to_thread.run_sync(previews_storage.upload_thumbnail, project_id, row.id, data)
        await to_thread.run_sync(preview_repo.set_thumbnail, row.id, path)

    return save


async def assemble_environments(
    env_repo,
    nodes: list[EnvNode],
    *,
    agent_node_id: str,
    policy_of: Callable[[str], str | None],
    preview_repo=None,
) -> AssembledTools:
    """Build one prefixed toolset per reachable environment.

    Never raises: an environment that cannot be built lands in ``unavailable``
    and the model is told, exactly as a broken tool node is.
    """
    toolsets: list = []
    owner_by_tool: dict[str, str] = {}
    owner_by_toolset: list[str] = []
    unavailable: list[str] = []
    described: list[tuple[EnvNode, str]] = []

    for node in nodes:
        current = node
        if current.status == "pending":
            # First use of a scratch space pays for the sandbox here. Slower
            # than provisioning in the background, but the agent's first
            # attempt works instead of always failing.
            current = await ensure_provisioned(env_repo, current)

        # error is included on purpose: the tools self-heal on a successful
        # connect, so an environment that recovered gets used this turn.
        if current.status not in ("ready", "error") or not current.sandbox_id:
            unavailable.append(current.name)
            continue

        spec = get_spec(current.runtime)
        if spec is None:
            unavailable.append(current.name)
            continue

        ctx = EnvContext(
            node_id=current.id,
            project_id=current.project_id,
            name=current.name,
            config=current.config,
            status=current.status,
            agent_node_id=agent_node_id,
            set_status=_status_writer(env_repo, current.id),
            record_preview=(
                _preview_recorder(preview_repo, current.project_id, current.id)
                if preview_repo is not None
                else None
            ),
            save_thumbnail=(
                _thumbnail_saver(preview_repo, current.project_id, current.id)
                if preview_repo is not None
                else None
            ),
        )
        try:
            built = spec.build(ctx)
        except Exception:
            unavailable.append(current.name)
            continue

        prefix = env_prefix(current.name, current.id)
        toolset = LivePolicyToolset(
            PrefixedToolset(built, prefix),
            policy=partial(policy_of, current.id),
            start=current.tool_policy,
        )

        owner_by_tool[prefix] = current.id
        # pydantic-ai reports the prefixed name, and _record_pending_calls
        # looks the owner up by exactly that.
        names = ENV_TOOL_NAMES
        if current.config.get("mcp"):
            names = (*ENV_TOOL_NAMES, *BROWSER_TOOL_NAMES)
        for base in names:
            owner_by_tool[f"{prefix}_{base}"] = current.id

        toolsets.append(toolset)
        owner_by_toolset.append(current.id)
        described.append((current, prefix))

    note = environment_note(described, agent_node_id)
    return AssembledTools(
        toolsets=toolsets,
        owner_by_tool=owner_by_tool,
        unavailable=unavailable,
        owner_by_toolset=owner_by_toolset,
        notes=[note] if note else [],
    )


def merge_assembled(a: AssembledTools, b: AssembledTools) -> AssembledTools:
    """Combine two assemblies into one turn's toolsets.

    toolsets and owner_by_toolset stay parallel: record_calls zips them with
    strict=True, so a length mismatch would break every turn.
    """
    return AssembledTools(
        toolsets=[*a.toolsets, *b.toolsets],
        owner_by_tool={**a.owner_by_tool, **b.owner_by_tool},
        unavailable=[*a.unavailable, *b.unavailable],
        owner_by_toolset=[*a.owner_by_toolset, *b.owner_by_toolset],
        notes=[*a.notes, *b.notes],
    )


def environment_note(described: list[tuple[EnvNode, str]], agent_node_id: str) -> str | None:
    """Tell the model which environments it has and what each is for."""
    if not described:
        return None

    lines = [
        "You can execute code in these environments. Each exposes run_command, "
        "read_file, write_file, list_files, next_free_port and publish_preview "
        f"under the prefix shown. Relative paths resolve against your own "
        f"directory, {WORKSPACE_ROOT}/{agent_node_id}. Other agents' directories "
        f"under {WORKSPACE_ROOT} are readable. "
        "The user sees these files live in a code preview. To show a running "
        "server, get a port with next_free_port, start it in the background bound "
        "to 0.0.0.0, then call publish_preview with a short title naming what it "
        "shows ('Todo app', not 'port 3000') so it appears beside the chat."
    ]
    for node, prefix in described:
        purpose = node.config.get("description") or (
            "the project's shared scratch space"
            if node.role == "scratch"
            else "an environment the user provisioned"
        )
        lines.append(f'- "{node.name}" (tools: {prefix}_*): {purpose}.')
        if node.config.get("mcp"):
            lines.append(
                f"  It also has a headless browser ({prefix}_browser_*). Reach servers "
                "in this environment at http://172.17.0.1:<port>, never localhost. "
                "Read pages with browser_snapshot; screenshots land in "
                f"{WORKSPACE_ROOT}/{agent_node_id}/screenshots/."
            )
    return "\n".join(lines)
