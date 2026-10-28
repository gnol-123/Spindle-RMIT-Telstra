"""Turn orchestration: runs the agent and persists the user and assistant rows."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import anyio
from pydantic_ai import DeferredToolRequests, DeferredToolResults
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import UsageLimits

from app.config import settings
from app.repositories.project_repo import (
    DEFAULT_HISTORY_LIMIT,
    Edge,
    InboundContext,
    Message,
    ProjectRepository,
)
from app.services import runs
from app.services.agent import (
    get_agent_for,
    on_model_retry,
    summarise_conversation,
    to_model_messages,
)
from app.services.runs import RunningTurn

log = logging.getLogger(__name__)

# Tool args bigger than this are stored truncated: the bubble is a transcript,
# not an archive.
_ARGS_MAX = 2000
# Progressive writes are throttled: each is an HTTP round trip to PostgREST.
_FLUSH_INTERVAL_S = 1.5
# Live-turn heartbeat. runs.stale_after_s (90s) without one reads as dead.
_HEARTBEAT_S = 20


def _checkpoint_hook(send):
    """after_node_run: queue the full history behind the node's own events.

    Same stream as the events, so the driver writes it with the bubble exactly
    at this point. pydantic-ai appends a request when its node starts, so a
    pending one (tool returns, the prompt) rides on ``result``.
    """
    from pydantic_ai import ModelRequestNode, UserPromptNode
    from pydantic_ai.messages import ModelResponse

    async def hook(ctx, *, node, result):
        history = list(ctx.messages)
        # Empty parts: a placeholder for resuming a suspended response, not a request.
        pending = result.request if isinstance(result, ModelRequestNode) else None
        if pending is not None and pending.parts and (not history or history[-1] is not pending):
            history.append(pending)
        last = history[-1] if history else None
        # A final answer: finalise is next, and resuming it would ask the model again.
        if isinstance(last, ModelResponse) and not last.tool_calls:
            return result
        # Past the first node the run has moved on from the calls a resume's approvals answer.
        keep = isinstance(node, UserPromptNode)
        await send.send(("checkpoint", {"history": history, "keep_approvals": keep}))
        return result

    return hook


@dataclass
class AgentTurn:
    """The result of one agent call, before it is saved."""

    output: str
    model: str
    input_tokens: int | None = None
    # Includes reasoning, on every provider. See _reasoning_from.
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    # Model requests behind this turn: >1 when tool calls loop.
    requests: int | None = None
    error: str | None = None
    # Set when the run paused for approval. Output is empty; do not persist it.
    pending: DeferredToolRequests | None = None
    # History at the pause, for parking and resuming. None on a normal turn.
    all_messages: list[ModelMessage] | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None

    @property
    def paused(self) -> bool:
        return self.pending is not None


@dataclass
class ChatTurn:
    """Result of user prompt and LLM reply.

    ``user_message`` is None on a resume: that turn appends to an existing
    bubble rather than starting one. ``assistant_message.status`` may be
    ``complete``, ``failed``, ``cancelled`` or ``awaiting_approval``.
    """

    conversation_id: str
    user_message: Message | None
    assistant_message: Message | None
    output: str
    error: str | None = None
    pending: DeferredToolRequests | None = None
    all_messages: list[ModelMessage] | None = None


def build_context_instructions(context: list[InboundContext]) -> str | None:
    """Format inbound edge summaries as per-call instructions.

    Kept out of the system prompt: that is the ``get_agent_for`` cache key.
    """
    if not context:
        return None
    parts = ["Context from other agents in this project:"]
    for c in context:
        parts.append(f"\n## {c.source_node_name}\n{c.summary}")
    return "\n".join(parts)


def _limits(request_limit: int | None = None) -> UsageLimits:
    """Per-turn cap on model requests. UsageLimitExceeded lands as a failed row."""
    return UsageLimits(request_limit=request_limit or settings.turn_request_limit)


async def refresh_edge(repo: ProjectRepository, edge: Edge) -> Edge | None:
    """Regenerate one context edge's summary from its source conversation."""
    from anyio import to_thread

    conversation_id = await to_thread.run_sync(repo.get_conversation_for_node, edge.source_node_id)
    if conversation_id is None:
        # Nothing to summarise; record it so the edge stops reading as stale.
        return await to_thread.run_sync(lambda: repo.update_edge_summary(edge.id, "", 0))

    history = await to_thread.run_sync(repo.list_messages, conversation_id)
    # The head is the last row actually summarised, not the conversation's
    # live message_count: a `running` row's text was never seen below, and
    # counting it would let the edge read fresh once that turn ends.
    head = max((m.seq for m in history if m.status == "complete"), default=0)
    summary = await summarise_conversation(history, max_words=edge.summary_max_words)
    return await to_thread.run_sync(lambda: repo.update_edge_summary(edge.id, summary, head))


async def refresh_outbound(repo: ProjectRepository, node_id: str) -> list[str]:
    """Refresh every context edge leaving a node. Returns the ids that failed.

    One summariser call per distinct summary_max_words: three edges out of one
    scoping agent are the same transcript three times.
    """
    from anyio import to_thread

    edges = await to_thread.run_sync(repo.list_outbound_context_edges, node_id)
    if not edges:
        return []

    conversation_id = await to_thread.run_sync(repo.get_conversation_for_node, node_id)
    history = (
        await to_thread.run_sync(repo.list_messages, conversation_id) if conversation_id else []
    )
    head = max((m.seq for m in history if m.status == "complete"), default=0)

    failed: list[str] = []
    by_words: dict[int, list[Edge]] = {}
    for e in edges:
        by_words.setdefault(e.summary_max_words, []).append(e)

    for max_words, group in by_words.items():
        try:
            summary = await summarise_conversation(history, max_words=max_words) if history else ""
        except Exception:
            log.exception("summary failed for %s (%d words)", node_id, max_words)
            failed.extend(e.id for e in group)
            continue
        for e in group:
            try:
                await to_thread.run_sync(
                    lambda e=e, summary=summary: repo.update_edge_summary(e.id, summary, head)
                )
            except Exception:
                log.exception("summary store failed for edge %s", e.id)
                failed.append(e.id)
    return failed


def _reasoning_from(usage: object) -> int | None:
    """Reasoning tokens, wherever the provider put them.

    pydantic-ai has no typed field for this: each model adapter lifts it into
    ``usage.details`` under its own name (OpenAI/Ollama ``reasoning_tokens``,
    Anthropic ``thinking_tokens``, Google ``thoughts_tokens``). Always a subset
    of ``output_tokens``, never additive, so never sum the two.
    """
    details = getattr(usage, "details", None) or {}
    for key in ("reasoning_tokens", "thinking_tokens", "thoughts_tokens"):
        value = details.get(key)
        if isinstance(value, int):
            return value
    return None


def _turn_from(output: str, model: str, usage: object) -> AgentTurn:
    return AgentTurn(
        output=output,
        model=model,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        reasoning_tokens=_reasoning_from(usage),
        cache_read_tokens=getattr(usage, "cache_read_tokens", None),
        cache_write_tokens=getattr(usage, "cache_write_tokens", None),
        requests=getattr(usage, "requests", None),
    )


async def _stream_agent(
    system_prompt: str,
    model: str,
    prompt: str,
    history: list,
    *,
    instructions: str | None = None,
    toolsets: list | None = None,
    resume: "ResumeInput | None" = None,
    request_limit: int | None = None,
    checkpoint: bool = False,
) -> AsyncIterator[tuple[str, dict]]:
    """Run one agent turn, yielding ``chunk`` deltas then one ``done`` or ``paused``.

    ``agent.run()`` with an ``event_stream_handler``. The handler runs
    concurrently with the run, so deltas cross to this generator through a
    memory stream. ``checkpoint`` adds a ``checkpoint`` item after each node.
    """
    from datetime import UTC, datetime

    from pydantic_ai.capabilities import Hooks
    from pydantic_ai.messages import (
        FunctionToolCallEvent,
        FunctionToolResultEvent,
        PartDeltaEvent,
        PartStartEvent,
        RetryPromptPart,
        TextPart,
        TextPartDelta,
    )

    send, receive = anyio.create_memory_object_stream[tuple[str, dict]](64)

    def _now() -> str:
        return datetime.now(UTC).isoformat()

    async def handler(ctx, stream) -> None:
        async for event in stream:
            if isinstance(event, FunctionToolCallEvent):
                args = event.part.args_as_json_str()
                await send.send(
                    (
                        "tool",
                        {
                            "type": "call",
                            "tool_call_id": event.part.tool_call_id,
                            "name": event.part.tool_name,
                            "args": event.part.args_as_dict()
                            if len(args) <= _ARGS_MAX
                            else {"_truncated": args[:_ARGS_MAX]},
                            "at": _now(),
                        },
                    )
                )
                continue
            if isinstance(event, FunctionToolResultEvent):
                # `.part` in the installed pydantic-ai; `.result` in newer ones.
                part = getattr(event, "result", None)
                if part is None:
                    part = event.part
                failed = isinstance(part, RetryPromptPart)
                await send.send(
                    (
                        "tool",
                        {
                            "type": "result",
                            "tool_call_id": getattr(part, "tool_call_id", None),
                            "name": getattr(part, "tool_name", None),
                            "status": "error" if failed else "ok",
                            "result_head": str(getattr(part, "content", ""))[:200],
                            "at": _now(),
                        },
                    )
                )
                continue
            text = None
            if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                text = event.part.content
            elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                text = event.delta.content_delta
            if text:
                await send.send(("chunk", {"text": text}))

    capabilities = [Hooks(after_node_run=_checkpoint_hook(send))] if checkpoint else None

    async def drive() -> AgentTurn:
        # Same stream as the deltas, so a retry lands in order with them.
        on_model_retry.set(lambda payload: send.send(("retry", payload)))
        # The stream closes on any exit, so a failed run cannot hang the reader.
        try:
            if resume is not None:
                return await _resume_agent_direct(
                    system_prompt,
                    model,
                    resume,
                    instructions,
                    toolsets,
                    handler,
                    request_limit,
                    capabilities,
                )
            return await _run_agent_direct(
                system_prompt,
                model,
                prompt,
                history,
                instructions,
                toolsets,
                handler,
                request_limit,
                capabilities,
            )
        finally:
            send.close()

    # A bare task, not a task group: a cancel scope cannot span the ``yield``
    # below, because an async generator may be resumed or closed from a
    # different task than the one that entered it.
    task = asyncio.ensure_future(drive())

    def _reap(t: asyncio.Task) -> None:
        # Nobody awaits this task on the early-exit path below; retrieve its
        # exception here so asyncio does not log it as never retrieved.
        if not t.cancelled() and t.exception() is not None:
            log.debug("abandoned stream task ended with %r", t.exception())

    task.add_done_callback(_reap)
    try:
        async with receive:
            async for item in receive:
                yield item
    finally:
        # Unconditional: the bare task's own finally does not run on every exit.
        if task.done():
            # Surface the run's own failure, not whatever the reader saw.
            result = task.result()
            if result.paused:
                yield "paused", {"pending": result.pending, "all_messages": result.all_messages}
            else:
                yield "done", {"turn": result}
        else:
            # Reader left early; nothing will await the task.
            task.cancel()


async def _run_agent_direct(
    system_prompt,
    model,
    prompt,
    history,
    instructions,
    toolsets,
    handler,
    request_limit=None,
    capabilities=None,
) -> AgentTurn:
    agent = get_agent_for(system_prompt, model)
    result = await agent.run(
        prompt,
        message_history=to_model_messages(history),
        instructions=instructions,
        toolsets=toolsets or None,
        event_stream_handler=handler,
        usage_limits=_limits(request_limit),
        capabilities=capabilities,
    )
    return _turn_from_result(result, model)


async def _resume_agent_direct(
    system_prompt,
    model,
    resume,
    instructions,
    toolsets,
    handler,
    request_limit=None,
    capabilities=None,
) -> AgentTurn:
    agent = get_agent_for(system_prompt, model)
    # Instructions are per run, not replayed from history: pass them again.
    result = await agent.run(
        message_history=resume.history,
        deferred_tool_results=resume.deferred,
        instructions=instructions,
        toolsets=toolsets or None,
        event_stream_handler=handler,
        usage_limits=_limits(request_limit),
        capabilities=capabilities,
    )
    return _turn_from_result(result, model)


def _turn_from_result(result, model: str) -> AgentTurn:
    if isinstance(result.output, DeferredToolRequests):
        # A pause still burned tokens. Carry the usage so the approval path can
        # bill it; only `output` is unsafe to persist here.
        turn = _turn_from("", model, result.usage)
        turn.pending = result.output
        turn.all_messages = result.all_messages()
        return turn
    return _turn_from(result.output, model, result.usage)


@dataclass(frozen=True)
class TurnSetup:
    """What a turn's ``setup`` hands back: awaited inside the task, so it is cancellable."""

    instructions: str | None
    toolsets: list
    on_paused: Callable[[DeferredToolRequests, list[ModelMessage]], Awaitable[None]] | None


@dataclass(frozen=True)
class ResumeInput:
    """A parked or interrupted run to continue, and the bubble it keeps appending to.

    ``deferred`` None: continue from history alone (recovery).
    """

    history: list[ModelMessage]
    deferred: DeferredToolResults | None
    message: Message


def _message_payload(m: Message) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "seq": m.seq,
        "status": m.status,
        "created_at": m.created_at,
        "tool_calls": m.tool_calls,
        "sender_node_id": m.sender_node_id,
    }


def _snapshot(run: RunningTurn, status: str | None = None) -> dict:
    m = run.message
    return {
        "id": m.id,
        "role": m.role,
        "content": "".join(run.text),
        "seq": m.seq,
        "status": status or m.status,
        "created_at": m.created_at,
        "tool_calls": list(run.events),
    }


class _Flusher:
    """Throttled content/tool_calls writes. Never per chunk: each is an HTTP round trip."""

    def __init__(self, repo: ProjectRepository, run: RunningTurn) -> None:
        from time import monotonic

        self._repo, self._run = repo, run
        # start_turn just wrote the row; the clock starts there, not at zero.
        self._last = monotonic()

    async def maybe(self, *, force: bool = False) -> None:
        from time import monotonic

        from anyio import to_thread

        now = monotonic()
        if not force and now - self._last < _FLUSH_INTERVAL_S:
            return
        self._last = now
        content, events = "".join(self._run.text), list(self._run.events)
        try:
            await to_thread.run_sync(
                lambda: self._repo.update_message(
                    self._run.message.id, content=content, tool_calls=events
                )
            )
        except Exception:
            log.exception("progress write failed for turn %s", self._run.conversation_id)


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


class _Heartbeat:
    """Bumps messages.heartbeat_at and the node's updated_at while a turn lives.

    Its own task, so it beats through silent stretches (a nested run_agent,
    a long tool call). ``stop`` waits out an in-flight beat, so a late
    ``running`` never lands after finalise wrote ``ready``.
    """

    def __init__(self, repo: ProjectRepository, run: RunningTurn) -> None:
        self._repo, self._run = repo, run
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.ensure_future(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            # Waited, not cancelled: a cancel cannot stop a write already in a thread.
            await asyncio.wait([self._task])

    async def _loop(self) -> None:
        from anyio import to_thread

        while True:
            try:
                await asyncio.wait_for(self._stop.wait(), _HEARTBEAT_S)
                return
            except TimeoutError:
                pass
            try:
                row = await to_thread.run_sync(self._beat)
            except Exception:
                log.exception("heartbeat failed for turn %s", self._run.conversation_id)
                continue
            # A stop sent to another backend, or before this one resumed the turn.
            if row.cancel_requested and not self._run.cancel_requested:
                await cancel_turn(self._run)

    def _beat(self) -> Message:
        # ponytail: unfenced; a live instance whose beats fail for 90s+ gets
        # resumed elsewhere too. Fence writes on the claimed heartbeat if that bites.
        row = self._repo.update_message(self._run.message.id, heartbeat_at=_now_iso())
        if not self._stop.is_set():
            self._repo.set_agent_status(self._run.node_id, "running")
        return row


def close_dangling_calls(
    events: list[dict], *, status: str, only: set[str] | None = None
) -> list[dict]:
    """Append a synthetic ``result`` for every ``call`` that never got one.

    Keeps the bubble self-consistent: a frontend reading ``messages.tool_calls``
    would otherwise spin forever on a denied or cancelled call. ``only`` limits
    it to specific tool_call_ids.
    """
    from datetime import UTC, datetime

    done = {e.get("tool_call_id") for e in events if e.get("type") == "result"}
    out = list(events)
    for e in events:
        tool_call_id = e.get("tool_call_id")
        if e.get("type") != "call" or tool_call_id in done:
            continue
        if only is not None and tool_call_id not in only:
            continue
        done.add(tool_call_id)
        out.append(
            {
                "type": "result",
                "tool_call_id": tool_call_id,
                "name": e.get("name"),
                "status": status,
                "result_head": status,
                "at": datetime.now(UTC).isoformat(),
            }
        )
    return out


async def _set_node_status(repo: ProjectRepository, node_id: str, status: str) -> None:
    from anyio import to_thread

    try:
        await to_thread.run_sync(repo.set_agent_status, node_id, status)
    except Exception:
        log.exception("node status write failed for %s", node_id)


async def _finalise(
    repo: ProjectRepository,
    tool_repo,
    run: RunningTurn,
    *,
    status: str,
    turn: AgentTurn | None = None,
    error: str | None = None,
    clear_parked: bool = False,
) -> Message:
    """The last write for a turn. Runs shielded so a late cancel cannot cut it short.

    ``clear_parked``: a resumed turn drops its parked run here, before settle
    publishes, so no reader sees the end with it still set. A handoff never
    finalises, so recovery still finds it.
    """
    from anyio import to_thread

    if status in ("cancelled", "failed", "complete"):
        # A call left open by a cancel or a crash never returns. In place: the
        # snapshot on a failed write, and any late subscriber, read run.events.
        run.events[:] = close_dangling_calls(
            run.events, status="cancelled" if status == "cancelled" else "error"
        )
    fields: dict = {"status": status, "content": "".join(run.text), "tool_calls": list(run.events)}
    if error is not None:
        fields["error"] = error
    if turn is not None:
        fields.update(
            model=turn.model,
            input_tokens=turn.input_tokens,
            output_tokens=turn.output_tokens,
            reasoning_tokens=turn.reasoning_tokens,
            cache_read_tokens=turn.cache_read_tokens,
            cache_write_tokens=turn.cache_write_tokens,
            requests=turn.requests,
        )
        # turn.output is only the text after the last tool call. With tools,
        # keep the streamed text so tool offsets still index into it.
        if status == "complete" and not run.events:
            fields["content"] = turn.output
    fields = {k: v for k, v in fields.items() if v is not None}
    if status != "failed":
        # Explicit null: a wrong restart sweep may have set error, and
        # messages_error_iff_failed rejects it beside any other status.
        fields["error"] = None
    try:
        message = await to_thread.run_sync(lambda: repo.update_message(run.message.id, **fields))
    except Exception:
        # Cascade-deleted conversation, or a dead connection. The sweep repairs it.
        log.exception("finalise failed for turn %s", run.conversation_id)
        message = Message(**{**_snapshot(run, status), "role": run.message.role})
    if status == "cancelled" and tool_repo is not None:
        try:
            await to_thread.run_sync(
                lambda: tool_repo.cancel_calls(run.conversation_id, ["running", "pending_approval"])
            )
        except Exception:
            log.exception("tool call cancel write failed for %s", run.conversation_id)
    if status != "awaiting_approval":
        if clear_parked and tool_repo is not None:
            # Not on a pause: a second pause re-parked through on_paused.
            try:
                await to_thread.run_sync(
                    lambda: tool_repo.set_pending_run(run.conversation_id, None)
                )
            except Exception:
                log.exception("pending run clear failed for %s", run.conversation_id)
        # Kept on a pause: an approved resume that dies restarts from it.
        await _clear_checkpoint(repo, run.message.id)
        await _set_node_status(repo, run.node_id, "ready")
    from app.services import push

    push.kick()
    return message


def _checkpointing() -> bool:
    # turn_checkpoints has no client policies, and recovery needs the key anyway.
    return bool(settings.supabase_service_key)


async def _clear_checkpoint(repo: ProjectRepository, message_id: str) -> None:
    from anyio import to_thread

    if not _checkpointing():
        return
    try:
        await to_thread.run_sync(repo.clear_checkpoint, message_id)
    except Exception:
        log.exception("checkpoint clear failed for %s", message_id)


async def _save_approvals(repo: ProjectRepository, resume: ResumeInput) -> None:
    """Before the run starts: recovery replays exactly these, nothing else."""
    from anyio import to_thread

    if resume.deferred is None or not _checkpointing():
        return
    approvals = dict(resume.deferred.approvals)
    try:
        await to_thread.run_sync(lambda: repo.set_approvals(resume.message.id, approvals))
    except Exception:
        # Fails safe: without them recovery asks again.
        log.exception("approvals write failed for %s", resume.message.id)


async def _shielded(coro):
    # A shielded inner task keeps going if the outer task is cancelled again.
    # Tracked in runs so shutdown waits on it.
    task = asyncio.ensure_future(coro)
    runs.track_finaliser(task)
    return await asyncio.shield(task)


def _drop(task: asyncio.Task) -> None:
    """Cancel a task nobody will await, retrieving any error it already raised."""
    if task.done():
        if not task.cancelled():
            task.exception()
    else:
        task.cancel()


async def start_turn(
    repo: ProjectRepository,
    conversation_id: str,
    system_prompt: str,
    model: str,
    prompt: str | None,
    *,
    node_id: str,
    project_id: str,
    tool_repo=None,
    client_token: str | None = None,
    instructions: str | None = None,
    toolsets: list | None = None,
    on_paused: Callable[[DeferredToolRequests, list[ModelMessage]], Awaitable[None]] | None = None,
    resume: ResumeInput | None = None,
    sender_node_id: str | None = None,
    setup: Callable[[], Awaitable[TurnSetup]] | None = None,
    request_limit: int | None = None,
    parent_message_id: str | None = None,
) -> RunningTurn:
    """Register and start one turn. Raises ``runs.TurnBusy`` before writing anything.

    Detached: the model run and every write live in ``run.task``, which outlives
    any reader. Readers attach through ``attach_events``.

    ``setup``, when given, replaces instructions/toolsets/on_paused. It starts
    once the turn is registered, beside the row writes, and is awaited inside
    the task: cancel works while tools are built. A failed write cancels it.

    ``parent_message_id`` is the orchestrator row a nested turn runs under.
    A resume rewrites it, so a user-driven resume is top level again. Sent
    only when set or clearing one, so it works on a schema without the column.
    """
    from anyio import to_thread
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    run = RunningTurn(
        conversation_id=conversation_id,
        node_id=node_id,
        project_id=project_id,
        model=model,
        repo=repo,
    )
    runs.register(run)
    setup_task = asyncio.ensure_future(setup()) if setup is not None else None
    try:
        if resume is None:
            # One spare row: the read may land after the insert.
            listed, user_message = await asyncio.gather(
                to_thread.run_sync(
                    lambda: repo.list_messages(conversation_id, limit=DEFAULT_HISTORY_LIMIT + 1)
                ),
                to_thread.run_sync(
                    lambda: repo.add_message(
                        conversation_id,
                        "user",
                        prompt,
                        client_token=client_token,
                        sender_node_id=sender_node_id,
                    )
                ),
            )
            # A replayed row may have replies after it; history stops before it either way.
            listed = [m for m in listed if m.seq < user_message.seq]
            history = listed[-DEFAULT_HISTORY_LIMIT:]
            run.user_message = user_message
            run.message, _ = await asyncio.gather(
                to_thread.run_sync(
                    lambda: repo.add_message(
                        conversation_id,
                        "assistant",
                        "",
                        status="running",
                        heartbeat_at=_now_iso(),
                        parent_message_id=parent_message_id,
                    )
                ),
                _set_node_status(repo, node_id, "running"),
            )
        else:
            history = []
            run.text.append(resume.message.content)
            run.events.extend(resume.message.tool_calls)
            # content/tool_calls too: recovery trims the bubble back to its checkpoint.
            fields: dict = {
                "status": "running",
                "heartbeat_at": _now_iso(),
                "content": resume.message.content,
                "tool_calls": resume.message.tool_calls,
            }
            if parent_message_id is not None or resume.message.parent_message_id is not None:
                fields["parent_message_id"] = parent_message_id
            run.message, _, _ = await asyncio.gather(
                to_thread.run_sync(lambda: repo.update_message(resume.message.id, **fields)),
                _set_node_status(repo, node_id, "running"),
                _save_approvals(repo, resume),
            )
    except BaseException:
        runs.unregister(conversation_id)
        if setup_task is not None:
            _drop(setup_task)
        raise

    flusher = _Flusher(repo, run)
    heartbeat = _Heartbeat(repo, run)

    async def save_checkpoint(history: list[ModelMessage], keep_approvals: bool) -> None:
        # Lengths now: every event before this item is already in run.text/events.
        content_len, events_len = sum(map(len, run.text)), len(run.events)

        def write() -> None:
            # ponytail: rewrites the whole history per node, O(n^2) bytes over a
            # long turn; append-only deltas if checkpoint size starts to bite.
            dumped = ModelMessagesTypeAdapter.dump_python(history, mode="json")
            repo.save_checkpoint(
                run.message.id,
                dumped,
                content_len,
                events_len,
                clear_approvals=not keep_approvals,
            )

        try:
            await to_thread.run_sync(write)
        except Exception:
            log.exception("checkpoint write failed for turn %s", conversation_id)

    async def drive() -> None:
        nonlocal instructions, toolsets, on_paused

        async def settle(
            *,
            status: str,
            event: str,
            payload: dict,
            result: AgentTurn,
            turn: AgentTurn | None = None,
            error: str | None = None,
        ) -> None:
            """One terminal tail: finalise, publish, close every subscriber.

            Shielded as a whole, not just the write. A cancel landing between
            the write and ``runs.close`` would otherwise leave every attached
            reader waiting on a stream that never closes.
            """
            run.result = result
            await heartbeat.stop()
            message = await _finalise(
                repo,
                tool_repo,
                run,
                status=status,
                turn=turn,
                error=error,
                clear_parked=resume is not None and resume.deferred is not None,
            )
            run.message = message
            await runs.close(
                run, event, {**payload, "assistant_message": _message_payload(message)}
            )

        turn: AgentTurn | None = None
        try:
            if setup_task is not None:
                built = await setup_task
                instructions, toolsets, on_paused = (
                    built.instructions,
                    built.toolsets,
                    built.on_paused,
                )
            async for event, payload in _stream_agent(
                system_prompt,
                model,
                prompt,
                history,
                instructions=instructions,
                toolsets=toolsets,
                resume=resume,
                request_limit=request_limit,
                checkpoint=_checkpointing(),
            ):
                if event in ("chunk", "tool", "retry"):
                    await runs.emit(run, event, payload)
                    await flusher.maybe(force=event == "tool")
                elif event == "checkpoint":
                    # Bubble first: the checkpoint's lengths must not outrun the row.
                    await flusher.maybe(force=True)
                    await save_checkpoint(payload["history"], payload["keep_approvals"])
                elif event == "paused":

                    async def paused_tail(payload=payload) -> None:
                        # on_paused first: settle publishes the terminal event to
                        # subscribers, so a reader must not see "paused" before
                        # the pending calls are recorded and the run parked.
                        if on_paused is not None:
                            try:
                                await on_paused(payload["pending"], payload["all_messages"])
                            except Exception:
                                log.exception("on_paused failed for turn %s", conversation_id)
                        await settle(
                            status="awaiting_approval",
                            event="paused",
                            payload=payload,
                            result=AgentTurn(
                                output="",
                                model=model,
                                pending=payload["pending"],
                                all_messages=payload["all_messages"],
                            ),
                        )

                    # Unregister after the park, not before: a cancel landing in
                    # between would otherwise find nothing running and nothing
                    # parked, and 409 while the turn parks itself.
                    try:
                        await _shielded(paused_tail())
                    finally:
                        runs.unregister(conversation_id)
                    return
                else:
                    turn = payload["turn"]
        except asyncio.CancelledError:
            runs.unregister(conversation_id)
            user_cancel = run.cancel_requested
            if runs.handing_off() and not user_cancel:
                # Row and node stay running; runs.hand_off marks the heartbeat stale.
                raise
            children = list(run.children)

            async def cancel_tail() -> None:
                # cancel_requested is already set on every child (cancel_turn
                # marks the whole descendant tree before cancelling); asyncio
                # itself already cancelled a child we were suspended on
                # (await run.task makes it our _fut_waiter). Cancel any that
                # somehow weren't reached yet, then wait for all of them.
                for child in children:
                    if child.task is not None and not child.task.done():
                        child.task.cancel()
                if children:
                    await asyncio.gather(*(c.task for c in children), return_exceptions=True)
                await settle(
                    status="cancelled" if user_cancel else "failed",
                    event="done",
                    payload={},
                    result=AgentTurn(
                        output="".join(run.text),
                        model=model,
                        error=None if user_cancel else "cancelled",
                    ),
                    error=None if user_cancel else "backend shutting down",
                )

            await _shielded(cancel_tail())
            raise
        except Exception as exc:
            turn = AgentTurn(output="".join(run.text), model=model, error=str(exc))
            await runs.emit(run, "error", {"error": str(exc)})

        if turn is None:
            # The stream ended without a terminal event: a cancel suppressed it,
            # or the provider closed silently. Never leave the row running.
            turn = AgentTurn(
                output="".join(run.text), model=model, error="run ended without a result"
            )
        runs.unregister(conversation_id)
        await _shielded(
            settle(
                status="failed" if turn.failed else "complete",
                event="done",
                payload={},
                result=turn,
                turn=turn,
                error=turn.error,
            )
        )

    async def guarded() -> None:
        heartbeat.start()
        try:
            await drive()
        except asyncio.CancelledError:
            # Swallowed on purpose: the cancel branch already finalised, and
            # `await run.task` must return rather than raise into the caller.
            pass
        except Exception:
            # Nobody awaits this task, so a failure here would otherwise leave
            # the row running and the node stuck.
            log.exception("turn %s failed outside the model run", conversation_id)
            runs.unregister(conversation_id)
            await heartbeat.stop()
            # Best effort: without it the row sits running until the restart sweep.
            with contextlib.suppress(Exception):
                await _finalise(
                    repo,
                    tool_repo,
                    run,
                    status="failed",
                    error="turn failed",
                    clear_parked=resume is not None and resume.deferred is not None,
                )
            await _set_node_status(repo, node_id, "ready")
        finally:
            # A cancel before drive awaited setup_task leaves it running.
            if setup_task is not None:
                _drop(setup_task)
            # Safety net; every finalise path stopped it already.
            await _shielded(heartbeat.stop())

    run.task = asyncio.ensure_future(guarded())
    # Step it to its first await: a task cancelled before it starts skips every handler.
    await asyncio.sleep(0)
    return run


def _mark_cancel_requested(run: RunningTurn) -> None:
    """Set cancel_requested on a turn and every descendant, recursively.

    Must happen before ``run.task.cancel()``: cancelling a task that is
    suspended on ``await child.task`` (as run_turn's parent wiring does)
    makes asyncio cancel that child task too, as a side effect of cancelling
    whatever the task is currently awaiting. Without marking the child first,
    its own cancel branch reads cancel_requested as False and finalises it as
    a shutdown failure instead of a cascaded user cancel.
    """
    run.cancel_requested = True
    for child in run.children:
        _mark_cancel_requested(child)


async def cancel_turn(run: RunningTurn) -> None:
    """Stop a turn in flight. Returns at once; the row lands when the task unwinds."""
    _mark_cancel_requested(run)
    if run.task is not None:
        run.task.cancel()


async def cancel_for_node(conversation_id: str | None) -> None:
    """Stop a node's running turn before its row is deleted.

    None is a no-op: only agent nodes have conversations.
    """
    run = runs.get(conversation_id) if conversation_id else None
    if run is None:
        return
    await cancel_turn(run)
    if run.task is not None:
        with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(run.task), 5)


async def cancel_for_project(project_id: str) -> None:
    """Stop every running turn in a project before it is deleted."""
    # Concurrent: sequential awaits would cost one 5s timeout per stuck turn.
    await asyncio.gather(
        *(cancel_for_node(r.conversation_id) for r in runs.running_in_project(project_id)),
        return_exceptions=True,
    )


async def cancel_paused(
    repo: ProjectRepository, tool_repo, conversation_id: str, node_id: str
) -> Message | None:
    """Abandon a turn parked for approval. None when nothing was parked."""
    from anyio import to_thread

    # Unguarded: without the row there is nothing to cancel, so a failure here
    # must reach the caller rather than report a cancel that never happened.
    message = await to_thread.run_sync(
        lambda: repo.latest_message_with_status(conversation_id, "awaiting_approval")
    )
    if message is None:
        return None
    # Log and continue: the row and the node still reach their final state below.
    try:
        await to_thread.run_sync(lambda: tool_repo.set_pending_run(conversation_id, None))
    except Exception:
        log.exception("pending run clear failed for %s", conversation_id)
    try:
        await to_thread.run_sync(
            lambda: tool_repo.cancel_calls(conversation_id, ["running", "pending_approval"])
        )
    except Exception:
        log.exception("tool call cancel write failed for %s", conversation_id)
    try:
        events = close_dangling_calls(message.tool_calls, status="cancelled")
        final = await to_thread.run_sync(
            lambda: repo.update_message(message.id, status="cancelled", tool_calls=events)
        )
    except Exception:
        log.exception("cancel write failed for parked turn %s", conversation_id)
        final = message
    await _clear_checkpoint(repo, message.id)
    await _set_node_status(repo, node_id, "ready")
    return final


async def attach_events(run: RunningTurn) -> AsyncIterator[tuple[str, dict]]:
    """Snapshot, then live events until the terminal one.

    Safe from any number of readers; a reader leaving does not touch the run.
    """
    text, events, retry, receive = await runs.subscribe(run)
    start: dict = {
        "conversation_id": run.conversation_id,
        "assistant_message": {**_snapshot(run), "content": text, "tool_calls": events},
    }
    if run.user_message is not None:
        start["user_message"] = _message_payload(run.user_message)
    if retry is not None:
        start["retry"] = retry
    yield "start", start
    async with receive:
        async for item in receive:
            yield item


async def stream_turn(*args, **kwargs) -> AsyncIterator[tuple[str, dict]]:
    """Start a turn and stream it. The turn outlives a reader that leaves."""
    run = await start_turn(*args, **kwargs)
    async for item in attach_events(run):
        yield item


async def run_turn(*args, parent: RunningTurn | None = None, **kwargs) -> ChatTurn:
    """Start a turn and wait for it. Shared by /chat and canvas run_agent.

    With ``parent`` the turn is a child: cancelling the parent cancels it, and
    cancelling only the child returns a cancelled ChatTurn rather than raising.
    """
    if parent is not None and parent.message is not None:
        kwargs.setdefault("parent_message_id", parent.message.id)
    run = await start_turn(*args, **kwargs)
    return await await_turn(run, parent=parent)


async def await_turn(run: RunningTurn, *, parent: RunningTurn | None = None) -> ChatTurn:
    """Wait for a started turn, as run_turn does. Also joins one already running."""
    if parent is not None:
        parent.children.add(run)
        run.task.add_done_callback(lambda _t: parent.children.discard(run))
    try:
        await run.task
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            raise
        # Only the child was cancelled; its row is already finalised.
    turn = run.result
    return ChatTurn(
        conversation_id=run.conversation_id,
        user_message=run.user_message,
        assistant_message=run.message,
        output=turn.output if turn else "",
        error=turn.error if turn else None,
        pending=turn.pending if turn else None,
        all_messages=turn.all_messages if turn else None,
    )
