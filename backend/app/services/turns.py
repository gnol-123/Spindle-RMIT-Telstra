"""One turn's inputs: inbound context, toolsets, and the notes that describe them.

Shared by the chat routes and by the canvas tool's nested runs, so a stage
agent driven by an orchestrator gets exactly what it would get from a user.
Also the approval resume, shared by /chat/resume and a policy flip to auto.
"""

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from functools import partial

from anyio import to_thread
from pydantic_ai import DeferredToolRequests, DeferredToolResults
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse

from app.environments.assembly import assemble_environments, merge_assembled
from app.repositories.project_repo import Node
from app.repositories.tool_repo import ToolRepository
from app.routers.deps import TurnRepositories
from app.services import runs
from app.tools.assembly import AssembledTools, assemble, record_calls, unavailable_note
from app.workflows import (
    ResumeInput,
    TurnSetup,
    build_context_instructions,
    close_dangling_calls,
    start_turn,
)

log = logging.getLogger(__name__)

# A parked run older than this is abandoned rather than resumed.
PENDING_RUN_MAX_AGE = timedelta(hours=1)


@dataclass(frozen=True)
class PreparedTurn:
    instructions: str | None
    # Recording-wrapped, ready for agent.run(toolsets=...).
    toolsets: list
    # Unwrapped assembly, for owner_by_tool on the approval path.
    tools: AssembledTools


async def prepare_turn(
    repos: TurnRepositories, node: Node, conversation_id: str, *, nested: bool = False
) -> PreparedTurn:
    """Build instructions and recording toolsets for one agent turn.

    ``nested`` is a turn started by a canvas tool rather than a request. Canvas
    boxes are reported unavailable there, so no wiring can start an
    orchestration inside an orchestration.
    """
    # Lazy: canvas imports this module.
    from app.tools.canvas import CANVAS_SLUG, assemble_canvas

    repo, tool_repo, env_repo = repos.project, repos.tool, repos.env

    inbound = await to_thread.run_sync(repo.list_inbound, node.id)
    instructions = build_context_instructions(inbound.context)

    async def tools_part() -> AssembledTools:
        tool_nodes = inbound.tool_nodes
        if not tool_nodes:
            return AssembledTools()
        canvas_nodes = [n for n in tool_nodes if n.tool_slug == CANVAS_SLUG]
        other_nodes = [n for n in tool_nodes if n.tool_slug != CANVAS_SLUG]
        # Read per call, so a flip mid-run counts.
        policy = partial(repo.get_tool_policy, node.id)
        tools = await assemble(tool_repo, other_nodes, policy=policy, start=node.tool_policy)
        if canvas_nodes and nested:
            return merge_assembled(
                tools, AssembledTools(unavailable=[n.name for n in canvas_nodes])
            )
        if canvas_nodes:
            return merge_assembled(
                tools,
                await assemble_canvas(
                    repos,
                    node,
                    canvas_nodes,
                    conversation_id,
                    policy=policy,
                    start=node.tool_policy,
                ),
            )
        return tools

    async def envs_part() -> AssembledTools | None:
        if not inbound.env_nodes:
            return None
        return await assemble_environments(
            env_repo,
            inbound.env_nodes,
            agent_node_id=node.id,
            policy_of=repo.get_tool_policy,
            preview_repo=repos.preview,
        )

    tools, envs = await asyncio.gather(tools_part(), envs_part())
    if envs is not None:
        tools = merge_assembled(tools, envs)

    parts = [instructions, *tools.notes, unavailable_note(tools.unavailable)]
    joined = "\n\n".join(p for p in parts if p) or None

    toolsets = record_calls(
        tools,
        repo=tool_repo,
        project_id=node.project_id,
        conversation_id=conversation_id,
        agent_node_id=node.id,
    )
    return PreparedTurn(instructions=joined, toolsets=toolsets, tools=tools)


def _record_pending_calls(
    tool_repo: ToolRepository,
    pending: DeferredToolRequests,
    *,
    project_id: str,
    conversation_id: str,
    agent_node_id: str,
    owner_by_tool: dict[str, str],
) -> None:
    """Backfill pending_approval rows RecordingToolset did not already write.

    Skips a tool with no ``owner_by_tool`` entry rather than guessing
    tool_node_id: endpoints filter on it, so a wrong row beats no row.
    """
    existing = tool_repo.get_calls_by_tool_call_ids(
        conversation_id, [p.tool_call_id for p in pending.approvals]
    )
    for part in pending.approvals:
        if part.tool_call_id in existing:
            continue
        tool_node_id = owner_by_tool.get(part.tool_name)
        if tool_node_id is None:
            continue
        tool_repo.record_call(
            project_id=project_id,
            conversation_id=conversation_id,
            agent_node_id=agent_node_id,
            tool_node_id=tool_node_id,
            tool_call_id=part.tool_call_id,
            tool_name=part.tool_name,
            arguments=part.args_as_dict(),
            status="pending_approval",
        )


async def _park_pending_run(
    tool_repo: ToolRepository, conversation_id: str, messages: list
) -> None:
    payload = ModelMessagesTypeAdapter.dump_json(messages).decode()
    await to_thread.run_sync(lambda: tool_repo.set_pending_run(conversation_id, payload))


def make_on_paused(
    tool_repo: ToolRepository,
    *,
    project_id: str,
    conversation_id: str,
    agent_node_id: str,
    owner_by_tool: dict[str, str],
):
    """on_paused closure shared by chat, chat_stream, chat_resume and recovery.

    run_turn/start_turn call this inside the task, so pending calls are
    recorded and the run parked before the caller ever sees ``turn.pending``.
    """

    async def on_paused(pending: DeferredToolRequests, all_messages: list) -> None:
        await to_thread.run_sync(
            lambda: _record_pending_calls(
                tool_repo,
                pending,
                project_id=project_id,
                conversation_id=conversation_id,
                agent_node_id=agent_node_id,
                owner_by_tool=owner_by_tool,
            )
        )
        await _park_pending_run(tool_repo, conversation_id, all_messages)

    return on_paused


def turn_setup(turn_repos: TurnRepositories, node: Node, conversation_id: str):
    """Build tools beside the row writes; start_turn awaits it in the task so cancel still works."""

    async def setup() -> TurnSetup:
        prepared = await prepare_turn(turn_repos, node, conversation_id)
        on_paused = make_on_paused(
            turn_repos.tool,
            project_id=node.project_id,
            conversation_id=conversation_id,
            agent_node_id=node.id,
            owner_by_tool=prepared.tools.owner_by_tool,
        )
        return TurnSetup(prepared.instructions, prepared.toolsets, on_paused)

    return setup


class ResumeRefused(Exception):
    """A parked run that cannot resume. ``status`` is what /chat/resume answers."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


async def resume_paused(
    turn_repos: TurnRepositories, node: Node, approvals: dict[str, bool]
) -> runs.RunningTurn:
    """Resume node's turn parked for approval with these decisions, detached.

    Raises ResumeRefused, or runs.TurnBusy before the run writes anything.
    Toolsets are not serialisable, so they are rebuilt from the node.
    """
    trepo, tool_repo = turn_repos.project, turn_repos.tool
    conversation_id = node.conversation_id or await to_thread.run_sync(
        trepo.get_conversation_for_node, node.id
    )
    if conversation_id is None:
        raise ResumeRefused(404, "Conversation not found")

    pending_run = await to_thread.run_sync(tool_repo.get_pending_run, conversation_id)
    if pending_run is None:
        raise ResumeRefused(409, "No pending approval")

    payload, pending_run_at = pending_run
    if datetime.now(UTC) - pending_run_at > PENDING_RUN_MAX_AGE:
        await to_thread.run_sync(lambda: tool_repo.set_pending_run(conversation_id, None))
        awaiting = await to_thread.run_sync(
            lambda: trepo.latest_message_with_status(conversation_id, "awaiting_approval")
        )
        if awaiting is not None:
            await to_thread.run_sync(
                lambda: trepo.update_message(awaiting.id, status="failed", error="approval expired")
            )
        raise ResumeRefused(409, "Pending approval expired")

    calls = await to_thread.run_sync(
        lambda: tool_repo.get_calls_by_tool_call_ids(conversation_id, list(approvals))
    )
    for tool_call_id in approvals:
        existing = calls.get(tool_call_id)
        if existing is None or existing.get("status") != "pending_approval":
            raise ResumeRefused(422, f"No pending approval for tool_call_id {tool_call_id}")

    history = ModelMessagesTypeAdapter.validate_json(payload)
    deferred_results = DeferredToolResults(approvals=approvals)

    awaiting = await to_thread.run_sync(
        lambda: trepo.latest_message_with_status(conversation_id, "awaiting_approval")
    )
    if awaiting is None:
        # Do not clear pending_run here: a resume can land between on_paused's
        # write and the row flip, while a turn is legitimately pausing again.
        raise ResumeRefused(409, "No pending approval")

    # In memory only: start_turn seeds run.events from this row, so the denials
    # ride along and every later write, finalise included, preserves them. Not
    # written here: a TurnBusy below would leave them on a row whose calls are
    # still pending_approval, and a later resume would render an approved call
    # as denied.
    denied = [tid for tid, approved in approvals.items() if not approved]
    if denied:
        events = close_dangling_calls(awaiting.tool_calls, status="denied", only=set(denied))
        awaiting = replace(awaiting, tool_calls=events)

    run = await start_turn(
        trepo,
        conversation_id,
        node.system_prompt,
        node.model,
        None,
        node_id=node.id,
        project_id=node.project_id,
        tool_repo=tool_repo,
        setup=turn_setup(turn_repos, node, conversation_id),
        request_limit=node.request_limit,
        resume=ResumeInput(history=history, deferred=deferred_results, message=awaiting),
    )
    # Past TurnBusy the denials are final. Approved ones move on during the run.
    await to_thread.run_sync(lambda: tool_repo.set_calls_status(conversation_id, denied, "denied"))
    return run


async def resume_if_auto(turn_repos: TurnRepositories, node: Node) -> None:
    """Approve and resume node's parked turn if every pending call is now auto.

    Live policy, as LivePolicyToolset reads it: an environment's call follows
    the environment, every other call the agent.
    """
    trepo, tool_repo = turn_repos.project, turn_repos.tool
    conversation_id = node.conversation_id or await to_thread.run_sync(
        trepo.get_conversation_for_node, node.id
    )
    if conversation_id is None:
        return
    parked = await to_thread.run_sync(tool_repo.get_pending_run, conversation_id)
    if parked is None:
        return
    history = ModelMessagesTypeAdapter.validate_json(parked[0])
    last = next((m for m in reversed(history) if isinstance(m, ModelResponse)), None)
    ids = [c.tool_call_id for c in last.tool_calls] if last is not None else []
    calls = await to_thread.run_sync(
        lambda: tool_repo.get_calls_by_tool_call_ids(conversation_id, ids)
    )
    pending = {i: c for i, c in calls.items() if c.get("status") == "pending_approval"}
    if not pending:
        return
    owners = {c["tool_node_id"] for c in pending.values()}
    policies = await to_thread.run_sync(lambda: trepo.tool_policies([node.id, *owners]))
    agent_policy = policies.get(node.id, ("", ""))[1]

    def live(owner: str) -> str:
        kind, policy = policies.get(owner, ("", ""))
        return policy if kind == "environment" else agent_policy

    if any(live(c["tool_node_id"]) != "auto" for c in pending.values()):
        return
    try:
        await resume_paused(turn_repos, node, dict.fromkeys(pending, True))
    except (ResumeRefused, runs.TurnBusy) as exc:
        # Someone resumed or cancelled it first.
        log.info("auto-approve skipped for %s: %r", conversation_id, exc)


def resume_waiting(
    turn_repos: TurnRepositories, *, agent: Node | None = None, env_id: str | None = None
) -> None:
    """After a flip to auto, resume what it was holding. Detached: the PATCH does not wait.

    ``agent``: its own conversation. ``env_id``: every agent with a call on it
    waiting for approval.
    """

    trepo, tool_repo = turn_repos.project, turn_repos.tool

    async def paused_agents() -> list[Node]:
        agent_ids = await to_thread.run_sync(tool_repo.paused_agents_for_tool_node, env_id)
        # ponytail: one node read per paused agent, few per environment; batch if that grows.
        found = await asyncio.gather(
            *(to_thread.run_sync(trepo.get_agent_node, a) for a in agent_ids)
        )
        return [n for n in found if n is not None]

    async def go() -> None:
        try:
            nodes = [agent] if agent is not None else await paused_agents()
        except Exception:
            log.exception("auto-approve lookup failed for %s", env_id)
            return
        results = await asyncio.gather(
            *(resume_if_auto(turn_repos, n) for n in nodes), return_exceptions=True
        )
        for n, res in zip(nodes, results, strict=True):
            if isinstance(res, BaseException):
                log.error("auto-approve failed for %s", n.id, exc_info=res)

    # Tracked: a strong ref, and shutdown waits on it.
    runs.track_finaliser(asyncio.ensure_future(go()))
