"""Registry of turns in flight, keyed by conversation.

Holds the in-memory partial (text and tool events) and fans events out to any
number of SSE subscribers, so /chat/stream and /chat/attach read one source.

ponytail: in-process. A second replica cannot see or cancel these; switch to a
DB flag polled by the driver if the backend ever scales out.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from app.repositories.project_repo import Message

if TYPE_CHECKING:
    from app.workflows import AgentTurn

log = logging.getLogger(__name__)

SUBSCRIBER_BUFFER = 256


class TurnBusy(Exception):
    """The conversation already has a turn running."""


@dataclass(eq=False)
class RunningTurn:
    """eq=False: identity equality, so a RunningTurn can sit in a set (parent.children)."""

    conversation_id: str
    node_id: str
    project_id: str
    model: str
    task: asyncio.Task | None = None
    user_message: Message | None = None
    message: Message | None = None
    text: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    subscribers: set[MemoryObjectSendStream] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    children: "set[RunningTurn]" = field(default_factory=set)
    cancel_requested: bool = False
    result: "AgentTurn | None" = None
    final: tuple[str, dict] | None = None
    # The turn's ProjectRepository, for the shutdown handoff write.
    repo: Any = None
    # Pending model retry and its monotonic deadline, for an attach mid-countdown.
    retry: tuple[dict, float] | None = None


_RUNS: dict[str, RunningTurn] = {}

# Set at shutdown: a cancelled turn leaves its row running for the next instance.
_handing_off = False

# Heartbeat written on handoff, so the next instance's poll claims at once.
_EPOCH = "1970-01-01T00:00:00+00:00"


def stale_after_s() -> float:
    """At least 3 missed heartbeats, and past the shutdown join window."""
    from app.config import settings

    return max(settings.detached_join_timeout_s + 30, 90)


def _cutoff(stale_s: float) -> str:
    # Z suffix: a "+" would need quoting in or_.
    return (datetime.now(UTC) - timedelta(seconds=stale_s)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def stale_filter() -> str:
    """PostgREST or_ for a running row whose heartbeat (or created_at) is stale."""
    cutoff = _cutoff(stale_after_s())
    return f"heartbeat_at.lt.{cutoff},and(heartbeat_at.is.null,created_at.lt.{cutoff})"


def is_stale(message: Message) -> bool:
    """Same rule as stale_filter, for one row already read."""
    beat = datetime.fromisoformat(message.heartbeat_at or message.created_at)
    return beat < datetime.now(UTC) - timedelta(seconds=stale_after_s())


def handed_off(message: Message) -> bool:
    """Left by a clean shutdown, not a crash."""
    return message.heartbeat_at is not None and datetime.fromisoformat(
        message.heartbeat_at
    ) == datetime.fromisoformat(_EPOCH)


def handing_off() -> bool:
    return _handing_off


# Shielded finalise tasks. Strong refs: asyncio holds only weak ones, and
# nobody awaits a finaliser. Shutdown must not race the last write.
_FINALISERS: set[asyncio.Task] = set()


def track_finaliser(task: asyncio.Task) -> None:
    _FINALISERS.add(task)
    task.add_done_callback(_FINALISERS.discard)


def register(run: RunningTurn) -> None:
    # No await between check and insert: two requests cannot both pass.
    if run.conversation_id in _RUNS:
        raise TurnBusy(run.conversation_id)
    _RUNS[run.conversation_id] = run


def unregister(conversation_id: str) -> None:
    _RUNS.pop(conversation_id, None)


def get(conversation_id: str) -> RunningTurn | None:
    return _RUNS.get(conversation_id)


def conversation_ids() -> list[str]:
    return list(_RUNS)


def running_in_project(project_id: str) -> list[RunningTurn]:
    return [r for r in _RUNS.values() if r.project_id == project_id]


async def subscribe(
    run: RunningTurn,
) -> tuple[str, list[dict], dict | None, MemoryObjectReceiveStream]:
    """Snapshot plus a stream of what follows, taken under one lock so no event
    lands between the two. The retry's delay_s is what is left of it."""
    send, receive = anyio.create_memory_object_stream[tuple[str, dict]](SUBSCRIBER_BUFFER)
    async with run.lock:
        text = "".join(run.text)
        events = list(run.events)
        retry = None
        if run.retry is not None:
            payload, deadline = run.retry
            retry = {**payload, "delay_s": max(0.0, deadline - time.monotonic())}
        if run.final is not None:
            send.send_nowait(run.final)
            send.close()
        else:
            run.subscribers.add(send)
    return text, events, retry, receive


def _fan_out(run: RunningTurn, item: tuple[str, dict]) -> None:
    for send in list(run.subscribers):
        try:
            send.send_nowait(item)
        except (anyio.WouldBlock, anyio.BrokenResourceError, anyio.ClosedResourceError):
            # A reader that stopped reading, or left. Drop it; it can re-attach.
            run.subscribers.discard(send)
            send.close()


async def emit(run: RunningTurn, event: str, payload: dict) -> None:
    async with run.lock:
        if event == "retry":
            run.retry = (
                None
                if payload.get("recovered")
                else (payload, time.monotonic() + payload["delay_s"])
            )
        else:
            run.retry = None
        if event == "chunk":
            run.text.append(payload["text"])
        elif event == "tool":
            # Where in the text it landed, so a reader can split the bubble there.
            payload = {**payload, "offset": sum(map(len, run.text))}
            run.events.append(payload)
        _fan_out(run, (event, payload))


async def close(run: RunningTurn, event: str, payload: dict) -> None:
    async with run.lock:
        run.final = (event, payload)
        _fan_out(run, (event, payload))
        for send in list(run.subscribers):
            send.close()
        run.subscribers.clear()


def sweep_stale(client, *, min_age_s: float) -> dict[str, int]:
    """Repair tool_calls and nodes a dead process left mid-turn, on backend startup.

    Running messages are not touched: the recovery loop resumes them, so their
    tool calls re-run and their nodes go back to running there.

    ponytail: heartbeat_at is stamped by each backend's own clock; skew between
    replicas eats into the 90s floor. Use a DB-side now() via RPC if it bites.
    """
    # At least 3 missed heartbeats.
    cutoff = _cutoff(max(min_age_s, 90))
    counts = {}
    # Live somewhere, or waiting to be resumed.
    running = (
        client.table("messages")
        .select("conversation_id, conversations(node_id)")
        .eq("status", "running")
        .execute()
        .data
    )
    live = {r["conversation_id"] for r in running}
    live_nodes = {(r.get("conversations") or {}).get("node_id") for r in running} - {None}
    # tool_calls has no message_id: a running call is dead when its
    # conversation has no live running message.
    # ponytail: live ids go in the URL; fine for tens of concurrent turns.
    q = (
        client.table("tool_calls")
        .update({"status": "error", "error": "backend restarted"})
        .eq("status", "running")
        .lt("created_at", cutoff)
    )
    if live:
        q = q.not_.in_("conversation_id", sorted(live))
    counts["tool_calls"] = len(q.execute().data)
    # The heartbeat re-touches its node, so only abandoned ones are this old.
    q = (
        client.table("nodes")
        .update({"status": "ready"})
        .eq("kind", "agent")
        .eq("status", "running")
        .lt("updated_at", cutoff)
    )
    if live_nodes:
        q = q.not_.in_("id", sorted(live_nodes))
    counts["nodes"] = len(q.execute().data)
    return counts


async def hand_off(timeout: float) -> int:
    """Shutdown: stop live turns without finalising, for the next instance to resume.

    Cancelled before the write, so no beat or flush lands after the stale
    heartbeat. A user cancel already in flight still finalises. Returns how
    many were handed off.
    """
    from anyio import to_thread

    global _handing_off
    _handing_off = True
    live = [
        r
        for r in _RUNS.values()
        if r.task is not None and not r.task.done() and not r.cancel_requested
    ]
    if not live:
        return 0
    for r in live:
        r.task.cancel()
    # Shielded tails too: a pause still parking must land before, not after, the stale beat.
    await asyncio.wait(
        [r.task for r in live] + [t for t in _FINALISERS if not t.done()], timeout=timeout
    )

    def release(r: RunningTurn) -> None:
        r.repo.update_message(
            r.message.id, content="".join(r.text), tool_calls=list(r.events), heartbeat_at=_EPOCH
        )

    results = await asyncio.gather(
        *(
            to_thread.run_sync(release, r)
            for r in live
            # final set: its tail finalised the row, nothing to hand off.
            if r.message is not None and r.repo and r.final is None
        ),
        return_exceptions=True,
    )
    for exc in results:
        if isinstance(exc, BaseException):
            log.error("handoff write failed: %r", exc)
    log.info("handed off %d turn(s)", len(live))
    return len(live)


async def join_detached(timeout: float) -> int:
    """Wait for running turns and their finalise writes at shutdown.

    Returns how many are still running.
    """
    pending = [r.task for r in _RUNS.values() if r.task is not None and not r.task.done()]
    pending += [t for t in _FINALISERS if not t.done()]
    if not pending:
        return 0
    await asyncio.wait(pending, timeout=timeout)
    still_running = sum(1 for t in pending if not t.done())
    if still_running:
        log.warning("%d turn(s) still running at shutdown", still_running)
    return still_running
