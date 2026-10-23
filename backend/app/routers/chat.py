"""Chat endpoints. One agent node, one conversation, transcript replayed each turn."""

import asyncio
import json
from contextlib import suppress
from datetime import datetime
from typing import Any
from uuid import UUID

from anyio import to_thread
from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic_ai import DeferredToolRequests

from app.repositories.project_repo import Message
from app.routers.deps import ProjectRepo, TurnRepos
from app.services import recovery, runs
from app.services.turns import ResumeRefused, resume_paused, turn_setup
from app.workflows import (
    attach_events,
    cancel_paused,
    cancel_turn,
    run_turn,
    start_turn,
)

router = APIRouter(prefix="/chat", tags=["chat"])

_BUSY = HTTPException(
    status_code=status.HTTP_409_CONFLICT, detail="Agent is already running a turn"
)

# Bound on waiting for a just-registered turn's row before answering a cancel.
_CANCEL_ROW_WAIT_S = 5.0


class ChatRequest(BaseModel):
    node_id: UUID
    prompt: str = Field(min_length=1, max_length=32_000)
    # Optional idempotency key: a resend with the same token will not duplicate.
    client_token: str | None = Field(default=None, max_length=100)


class ChatMessage(BaseModel):
    id: UUID
    role: str
    content: str
    seq: int
    status: str
    created_at: datetime
    tool_calls: list[dict[str, Any]] = []
    # Agent node that wrote this user row (canvas run_agent). None = the user.
    sender_node_id: UUID | None = None

    @classmethod
    def of(cls, m: Message) -> "ChatMessage":
        return cls(
            id=UUID(m.id),
            role=m.role,
            content=m.content,
            seq=m.seq,
            status=m.status,
            created_at=m.created_at,
            tool_calls=m.tool_calls,
            sender_node_id=m.sender_node_id,
        )


class ChatResponse(BaseModel):
    node_id: UUID
    conversation_id: UUID
    output: str
    user_message: ChatMessage
    assistant_message: ChatMessage


class PendingCall(BaseModel):
    """One tool call awaiting approval."""

    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]


class ApprovalRequiredResponse(BaseModel):
    """A turn paused for tool approval. Switch on ``paused``: ChatResponse never sets it."""

    paused: bool = True
    node_id: UUID
    conversation_id: UUID
    pending_calls: list[PendingCall]


def _pending_calls(pending: DeferredToolRequests) -> list[PendingCall]:
    return [
        PendingCall(
            tool_call_id=part.tool_call_id,
            tool_name=part.tool_name,
            arguments=part.args_as_dict(),
        )
        for part in pending.approvals
    ]


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


async def _events(run):
    """SSE events for a run: start, then chunk/tool/done/error, or approval_required."""
    async for event, payload in attach_events(run):
        if event == "paused":
            yield _sse(
                "approval_required",
                {
                    "conversation_id": run.conversation_id,
                    "pending_calls": [c.model_dump() for c in _pending_calls(payload["pending"])],
                    "assistant_message": payload["assistant_message"],
                },
            )
            return
        yield _sse(event, payload)


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("", response_model=None)
async def chat(
    req: ChatRequest, repo: ProjectRepo, turn_repos: TurnRepos
) -> ChatResponse | ApprovalRequiredResponse:
    node = await to_thread.run_sync(repo.get_agent_node, str(req.node_id))
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    trepo, tool_repo = turn_repos.project, turn_repos.tool
    conversation_id = node.conversation_id or await to_thread.run_sync(
        lambda: trepo.get_or_create_conversation(node.id, node.project_id)
    )

    try:
        turn = await run_turn(
            trepo,
            conversation_id,
            node.system_prompt,
            node.model,
            req.prompt,
            node_id=node.id,
            project_id=node.project_id,
            tool_repo=tool_repo,
            client_token=req.client_token,
            setup=turn_setup(turn_repos, node, conversation_id),
            request_limit=node.request_limit,
        )
    except runs.TurnBusy:
        raise _BUSY from None

    if turn.pending is not None:
        # on_paused already recorded the pending calls and parked the run.
        return ApprovalRequiredResponse(
            node_id=UUID(node.id),
            conversation_id=UUID(conversation_id),
            pending_calls=_pending_calls(turn.pending),
        )

    return ChatResponse(
        node_id=UUID(node.id),
        conversation_id=UUID(turn.conversation_id),
        output=turn.output,
        user_message=ChatMessage.of(turn.user_message),
        assistant_message=ChatMessage.of(turn.assistant_message),
    )


@router.post("/stream")
async def chat_stream(
    req: ChatRequest, repo: ProjectRepo, turn_repos: TurnRepos
) -> StreamingResponse:
    """Stream a turn as SSE.

    Events: ``start``, ``chunk``, ``tool``, ``done``, ``error``, and
    ``approval_required`` when a tool needs approval. That last one ends the
    stream with no ``done``.

    The turn runs detached: a client disconnect stops the events, not the run.
    Busy raises 409 before any headers are sent, since start_turn fails before
    the StreamingResponse is built.
    """
    node = await to_thread.run_sync(repo.get_agent_node, str(req.node_id))
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    trepo, tool_repo = turn_repos.project, turn_repos.tool
    conversation_id = node.conversation_id or await to_thread.run_sync(
        lambda: trepo.get_or_create_conversation(node.id, node.project_id)
    )

    try:
        run = await start_turn(
            trepo,
            conversation_id,
            node.system_prompt,
            node.model,
            req.prompt,
            node_id=node.id,
            project_id=node.project_id,
            tool_repo=tool_repo,
            client_token=req.client_token,
            setup=turn_setup(turn_repos, node, conversation_id),
            request_limit=node.request_limit,
        )
    except runs.TurnBusy:
        raise _BUSY from None

    return StreamingResponse(_events(run), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/attach")
async def chat_attach(node_id: UUID, repo: ProjectRepo) -> Response:
    """Re-join a running turn's stream.

    Same events as /chat/stream; ``start`` carries the assistant row so far
    instead of the user message. 204 when nothing is running.
    """
    node = await to_thread.run_sync(repo.get_agent_node, str(node_id))
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    conversation_id = node.conversation_id or await to_thread.run_sync(
        repo.get_conversation_for_node, node.id
    )
    run = runs.get(conversation_id) if conversation_id else None
    # message is None between register() and the first DB insert: nothing to
    # snapshot yet, so treat it the same as no run.
    if run is None or run.message is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return StreamingResponse(_events(run), media_type="text/event-stream", headers=_SSE_HEADERS)


class CancelRequest(BaseModel):
    node_id: UUID


class CancelResponse(BaseModel):
    node_id: UUID
    conversation_id: UUID
    message_id: UUID


@router.post("/cancel", response_model=CancelResponse, status_code=status.HTTP_202_ACCEPTED)
async def chat_cancel(
    req: CancelRequest, repo: ProjectRepo, turn_repos: TurnRepos
) -> CancelResponse:
    """Stop a running or parked turn. Nothing is deleted; the partial reply stays."""
    node = await to_thread.run_sync(repo.get_agent_node, str(req.node_id))
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    conversation_id = node.conversation_id or await to_thread.run_sync(
        repo.get_conversation_for_node, node.id
    )
    if conversation_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nothing running")
    run = runs.get(conversation_id)
    if run is not None:
        await cancel_turn(run)
        if run.message is None and run.task is not None:
            # Registered before its assistant row was written. Wait, bounded,
            # for the row so the response can name it.
            with suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(run.task), _CANCEL_ROW_WAIT_S)
    if run is not None and run.message is not None:
        return CancelResponse(
            node_id=UUID(node.id),
            conversation_id=UUID(conversation_id),
            message_id=UUID(run.message.id),
        )
    parked = await cancel_paused(turn_repos.project, turn_repos.tool, conversation_id, node.id)
    if parked is None:
        # Left running by a dead backend: stop it before recovery resumes it.
        parked = await to_thread.run_sync(
            lambda: recovery.cancel_orphan(turn_repos, conversation_id, node.id)
        )
    if parked is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nothing running")
    return CancelResponse(
        node_id=UUID(node.id), conversation_id=UUID(conversation_id), message_id=UUID(parked.id)
    )


class ResumeRequest(BaseModel):
    node_id: UUID
    # tool_call_id -> approved
    approvals: dict[str, bool] = Field(min_length=1)


@router.post("/resume")
async def chat_resume(
    req: ResumeRequest, repo: ProjectRepo, turn_repos: TurnRepos
) -> StreamingResponse:
    """Resume a turn that paused for tool approval, streamed as SSE.

    Same events as /chat/stream, so a resume can pause again with
    ``approval_required``. 404/409/422 are raised before any headers are sent.
    """
    node = await to_thread.run_sync(repo.get_agent_node, str(req.node_id))
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    try:
        run = await resume_paused(turn_repos, node, req.approvals)
    except ResumeRefused as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from None
    except runs.TurnBusy:
        raise _BUSY from None
    return StreamingResponse(_events(run), media_type="text/event-stream", headers=_SSE_HEADERS)
