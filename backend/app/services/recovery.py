"""Resume turns a dead or departing backend left running.

Every instance polls. A stale running row is claimed with one compare-and-set
on the heartbeat it read, so exactly one instance resumes it. Nested turns
(canvas run_agent) are left to their parent, whose re-run of the tool call
rejoins them.
"""

import asyncio
import dataclasses
import logging
from datetime import UTC, datetime

from anyio import to_thread
from pydantic_ai import DeferredToolResults
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolReturnPart,
    UserPromptPart,
)

from app.repositories.project_repo import (
    DEFAULT_HISTORY_LIMIT,
    RUN_COLUMNS,
    Message,
    ProjectRepository,
    _to_message,
)
from app.routers.deps import TurnRepositories, service_turn_repositories
from app.services import runs
from app.services.agent import to_model_messages
from app.services.turns import turn_setup
from app.workflows import ResumeInput, close_dangling_calls, start_turn

log = logging.getLogger(__name__)

POLL_S = 15
# Claims per row before it is failed: a run that kills its backend cannot loop.
MAX_RESUMES = 3
# ponytail: rows per poll; the next poll takes the rest.
_BATCH = 20


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def claim(repo: ProjectRepository, row: Message) -> Message | None:
    """Take a stale row. None = another instance took it, or it moved on.

    A clean handoff does not count toward the cap: only crashes do.
    """
    count = row.resume_count + (0 if runs.handed_off(row) else 1)
    return repo.claim_message(row.id, row.heartbeat_at, heartbeat_at=_now_iso(), resume_count=count)


def fail(
    repos: TurnRepositories,
    row: Message,
    conversation_id: str,
    node_id: str | None,
    error: str | None,
    *,
    status: str = "failed",
) -> bool:
    """Finalise a row nobody will resume. False when someone else moved it first.

    ``status`` cancelled: a user stop, tidied like _finalise's cancel.
    """
    cancel = status == "cancelled"
    call_status = "cancelled" if cancel else "error"
    done = repos.project.claim_message(
        row.id,
        row.heartbeat_at,
        status=status,
        error=error,
        tool_calls=close_dangling_calls(row.tool_calls, status=call_status),
    )
    if done is None:
        return False
    # Best effort, like _finalise: the row is the record, these are tidy-up.
    tidy_ups = [
        lambda: repos.tool.cancel_calls(
            conversation_id,
            ["running", "pending_approval"] if cancel else ["running"],
            status=call_status,
        ),
        lambda: repos.project.clear_checkpoint(row.id),
    ]
    if cancel:
        tidy_ups.append(lambda: repos.tool.set_pending_run(conversation_id, None))
    if node_id:
        tidy_ups.append(lambda: repos.project.set_agent_status(node_id, "ready"))
    for tidy in tidy_ups:
        try:
            tidy()
        except Exception:
            log.exception("tidy-up failed for failed turn %s", row.id)
    return True


def cancel_orphan(
    repos: TurnRepositories, conversation_id: str, node_id: str | None
) -> Message | None:
    """User stop of a running row this process does not drive. None = nothing running.

    Stale: cancelled here. Still beating (another backend, or one that just died):
    flagged, and its driver or whoever resumes it cancels it.
    """
    row = repos.project.latest_message_with_status(conversation_id, "running")
    if row is None:
        return None
    if runs.is_stale(row) and fail(repos, row, conversation_id, node_id, None, status="cancelled"):
        return row
    return repos.project.request_cancel(row.id)


def _approvals(history: list, stored: dict[str, bool] | None) -> DeferredToolResults | None:
    """The decisions the dead run resumed with, for its still open calls. None asks again.

    Mirrors pydantic-ai's resume: calls answered in the request after the last
    response are skipped, and every open call needs a decision.
    """
    if not stored:
        return None
    at = next(
        (i for i in reversed(range(len(history))) if isinstance(history[i], ModelResponse)), None
    )
    if at is None:
        return None
    after = history[at + 1].parts if at + 1 < len(history) else []
    answered = {p.tool_call_id for p in after if isinstance(p, ToolReturnPart | RetryPromptPart)}
    open_ids = [c.tool_call_id for c in history[at].tool_calls if c.tool_call_id not in answered]
    if not open_ids or any(i not in stored for i in open_ids):
        return None
    return DeferredToolResults(approvals={i: stored[i] for i in open_ids})


def build_resume(repos: TurnRepositories, row: Message, conversation_id: str) -> ResumeInput:
    """From the checkpoint, the bubble trimmed back to it. Without one, the
    turn from scratch: transcript before the user row, then its prompt.

    Raises LookupError when there is no user row to restart from.
    """
    checkpoint = repos.project.get_checkpoint(row.id)
    if checkpoint is None:
        before = repos.project.list_messages(
            conversation_id, DEFAULT_HISTORY_LIMIT + 1, before_seq=row.seq
        )
        # A retry's failed reply may sit between the user row and this one.
        at = next((i for i in reversed(range(len(before))) if before[i].role == "user"), None)
        if at is None:
            raise LookupError(f"no user row before {row.id}")
        history = [
            *to_model_messages(before[:at]),
            ModelRequest(parts=[UserPromptPart(content=before[at].content)]),
        ]
        return ResumeInput(history, None, dataclasses.replace(row, content="", tool_calls=[]))

    history = ModelMessagesTypeAdapter.validate_python(checkpoint["history"])
    trimmed = dataclasses.replace(
        row,
        content=row.content[: checkpoint["content_len"]],
        tool_calls=row.tool_calls[: checkpoint["events_len"]],
    )
    return ResumeInput(history, _approvals(history, checkpoint.get("approvals")), trimmed)


async def _resume_top(
    repos: TurnRepositories, row: Message, conversation_id: str, node_id: str | None
) -> bool:
    if row.cancel_requested:
        await to_thread.run_sync(
            lambda: fail(repos, row, conversation_id, node_id, None, status="cancelled")
        )
        return False
    if row.resume_count >= MAX_RESUMES:
        await to_thread.run_sync(
            lambda: fail(repos, row, conversation_id, node_id, "could not resume")
        )
        return False
    claimed = await to_thread.run_sync(lambda: claim(repos.project, row))
    if claimed is None:
        return False
    node = await to_thread.run_sync(repos.project.get_agent_node, node_id) if node_id else None
    try:
        if node is None:
            raise LookupError(f"no agent node for {conversation_id}")
        resume = await to_thread.run_sync(lambda: build_resume(repos, claimed, conversation_id))
    except LookupError:
        log.exception("cannot resume turn %s", row.id)
        await to_thread.run_sync(
            lambda: fail(repos, claimed, conversation_id, node_id, "could not resume")
        )
        return False
    # An approved resume that died left its parked run; replaying its approvals drops it.
    try:
        await start_turn(
            repos.project,
            conversation_id,
            node.system_prompt,
            node.model,
            None,
            node_id=node.id,
            project_id=node.project_id,
            tool_repo=repos.tool,
            setup=turn_setup(repos, node, conversation_id),
            request_limit=node.request_limit,
            resume=resume,
        )
    except runs.TurnBusy:
        # The user started a new turn meanwhile. Its calls and node are not ours to tidy.
        log.info("turn %s superseded before resume", row.id)
        await to_thread.run_sync(lambda: _supersede(repos.project, claimed))
        return False
    log.info("resumed turn %s (claim %d)", row.id, claimed.resume_count)
    return True


def _supersede(repo: ProjectRepository, row: Message) -> None:
    repo.claim_message(
        row.id,
        row.heartbeat_at,
        status="cancelled",
        error=None,
        tool_calls=close_dangling_calls(row.tool_calls, status="cancelled"),
    )
    repo.clear_checkpoint(row.id)


async def _recover(r: dict, parent_status: dict[str, str]) -> bool:
    conversation_id = r["conversation_id"]
    if runs.get(conversation_id) is not None:
        # Live here: its beat is late, not dead.
        return False
    row = _to_message(r)
    node_id = (r.get("conversations") or {}).get("node_id")
    repos = service_turn_repositories(r["owner_id"])
    if row.parent_message_id is None:
        return await _resume_top(repos, row, conversation_id, node_id)
    if parent_status.get(row.parent_message_id) in ("running", "awaiting_approval"):
        # The parent's re-run of run_agent rejoins it, after approval if need be.
        return False
    if parent_status.get(row.parent_message_id) == "cancelled":
        # The user stopped the pipeline; the child stops with it.
        await to_thread.run_sync(
            lambda: fail(repos, row, conversation_id, node_id, None, status="cancelled")
        )
        return False
    await to_thread.run_sync(lambda: fail(repos, row, conversation_id, node_id, "parent run ended"))
    return False


async def recover_once(client) -> int:
    """One poll. Returns how many turns this instance resumed."""

    def stale() -> tuple[list[dict], dict[str, str]]:
        q = (
            client.table("messages")
            .select(f"{RUN_COLUMNS}, conversation_id, owner_id, conversations(node_id)")
            .eq("status", "running")
            .or_(runs.stale_filter())
        )
        live = runs.conversation_ids()
        if live:
            # Late beats, not dead: they would hold batch slots every poll.
            q = q.not_.in_("conversation_id", live)
        # Top level first, so nested rows waiting on their parent never starve it.
        # ponytail: those can still fill the batch for other nested rows; needs a
        # parent-status join (computed relationship) if 20 pile up.
        rows = (
            q.order("parent_message_id", nullsfirst=True)
            .order("created_at")
            .limit(_BATCH)
            .execute()
            .data
        )
        parent_ids = sorted({r["parent_message_id"] for r in rows if r.get("parent_message_id")})
        if not parent_ids:
            return rows, {}
        parents = client.table("messages").select("id, status").in_("id", parent_ids).execute().data
        return rows, {p["id"]: p["status"] for p in parents}

    rows, parent_status = await to_thread.run_sync(stale)
    results = await asyncio.gather(
        *(_recover(r, parent_status) for r in rows), return_exceptions=True
    )
    for r, res in zip(rows, results, strict=True):
        if isinstance(res, BaseException):
            log.error("recovery of turn %s failed", r["id"], exc_info=res)
    return sum(1 for res in results if res is True)


async def recovery_loop() -> None:
    """Poll forever. Cancelled at shutdown."""
    from app.services.supabase import get_service_client

    while True:
        try:
            await recover_once(get_service_client())
        except Exception:
            log.exception("turn recovery poll failed")
        await asyncio.sleep(POLL_S)
