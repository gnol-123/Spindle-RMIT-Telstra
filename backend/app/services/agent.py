"""Agent construction.

Agents are initialised per catalog entry.

Construction stays lazy: building an agent at import time crashes the whole app,
including ``/health``, when the API key is unset.
"""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from contextvars import ContextVar
from functools import lru_cache
from itertools import count

import httpx2
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models import Model, StreamedResponse
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.ollama import OllamaProvider

from app.config import settings
from app.repositories.project_repo import Message

# Consecutive ModelRetry failures one tool may have before the turn fails.
TOOL_RETRIES = 3

# Retries of one failed model request, and the wait before each.
MODEL_RETRIES = 5
MODEL_RETRY_DELAY_S = 10.0

# Set per turn: awaited with each retry's payload, so the UI can count down.
on_model_retry: ContextVar[Callable[[dict], Awaitable[None]] | None] = ContextVar(
    "on_model_retry", default=None
)


def _transient(exc: Exception) -> bool:
    """Rate limits, timeouts, 5xx and connection drops. Other 4xx fail the same way again."""
    if isinstance(exc, ModelHTTPError):
        return exc.status_code in (408, 429) or exc.status_code >= 500
    return isinstance(exc, ModelAPIError)


async def _notify(payload: dict) -> None:
    hook = on_model_retry.get()
    if hook is not None:
        await hook(payload)


async def _wait(attempt: int, exc: Exception) -> None:
    await _notify(
        {
            "attempt": attempt,
            "max": MODEL_RETRIES,
            "delay_s": MODEL_RETRY_DELAY_S,
            "error": str(exc)[:300],
        }
    )
    await asyncio.sleep(MODEL_RETRY_DELAY_S)


class RetryingModel(WrapperModel):
    """Retries a request that fails before any output. Mid-stream failures still
    fail the turn: retrying those would repeat text already sent."""

    async def request(self, *args, **kwargs):
        for attempt in count(1):
            try:
                response = await super().request(*args, **kwargs)
            except Exception as exc:
                if attempt > MODEL_RETRIES or not _transient(exc):
                    raise
                await _wait(attempt, exc)
                continue
            if attempt > 1:
                await _notify({"recovered": True})
            return response

    @asynccontextmanager
    async def request_stream(self, *args, **kwargs) -> AsyncGenerator[StreamedResponse]:
        stack = AsyncExitStack()
        for attempt in count(1):
            try:
                stream = await stack.enter_async_context(super().request_stream(*args, **kwargs))
            except Exception as exc:
                if attempt > MODEL_RETRIES or not _transient(exc):
                    raise
                await _wait(attempt, exc)
                continue
            if attempt > 1:
                await _notify({"recovered": True})
            break
        async with stack:
            yield stream


def _model(name: str) -> Model:
    """Build a model for one name, for user defined model name defaulted to: deepseek v4.1 flash"""
    if settings.llm_provider == "ollama":
        http = httpx2.AsyncClient(
            timeout=httpx2.Timeout(settings.llm_read_timeout_s, connect=10.0),
        )
        return OllamaModel(
            name,
            provider=OllamaProvider(
                base_url=settings.ollama_base_url,
                api_key=settings.ollama_api_key,
                http_client=http,
            ),
        )
    return GoogleModel(name, provider=GoogleProvider(api_key=settings.gemini_api_key))


@lru_cache(maxsize=256)
def get_agent_for(system_prompt: str, model: str) -> Agent[None, str | DeferredToolRequests]:
    """Return an agent for one catalog entry.

    Conversation history is passed per call via ``Agent.run(message_history=...)``
    Tools also passed per call via ``Agent.run(toolsets=...)``.

    ``output_type`` includes ``DeferredToolRequests`` so a run pauses for tool
    approval instead of raising: without it, a deferred tool call makes
    pydantic-ai raise UserError rather than returning it as output. This is a
    constant added to every agent, so it does not change the cache key.
    """
    return Agent(
        RetryingModel(_model(model)),
        system_prompt=system_prompt,
        output_type=[str, DeferredToolRequests],
        # Default 1: a second bad-args call or MCP error on one tool ends the turn.
        retries={"tools": TOOL_RETRIES},
    )


def to_model_messages(history: list[Message]) -> list[ModelMessage]:
    """Map stored message rows onto Pydantic AI's history format.

    Rows with ``status='failed'`` are skipped: replaying a turn the model never
    completed just degrades the next answer. ``system`` rows are skipped.
    """
    messages: list[ModelMessage] = []
    for m in history:
        if m.status != "complete":
            continue
        if m.role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=m.content)]))
        elif m.role == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=m.content)]))
    return messages


# Fallback when a caller has no edge to read the limit from. The
# edges.summary_max_words column carries the real per-edge value.
DEFAULT_SUMMARY_MAX_WORDS = 200

_SUMMARY_PROMPT = (
    "You summarise one agent's conversation so a different agent can pick up "
    "the thread. Report the facts, decisions and constraints that were "
    "established, not the fact that a conversation happened. Write plain "
    "statements: 'The target market is SMB fintech', never 'They discussed the "
    "target market'. Omit pleasantries, meta-commentary and anything the user "
    "did not actually settle. If nothing of substance was decided, say so in "
    "one line. Keep it under {max_words} words."
)


@lru_cache(maxsize=8)
def _summary_agent(max_words: int) -> Agent[None, str]:
    return Agent(
        _model(settings.summary_model),
        system_prompt=_SUMMARY_PROMPT.format(max_words=max_words),
    )


def _transcript(history: list[Message]) -> str:
    """Flatten a transcript for summarising."""
    lines = []
    for m in history:
        if m.status != "complete" or m.role not in ("user", "assistant"):
            continue
        lines.append(f"{m.role}: {m.content}")
    return "\n\n".join(lines)


async def summarise_conversation(
    history: list[Message], max_words: int = DEFAULT_SUMMARY_MAX_WORDS
) -> str:
    """Condense a conversation into context for a downstream agent.

    ``max_words`` comes from the edge, so a feeder with a long history can
    be given more room than a brief one.

    Returns an empty string for an empty transcript, without calling the
    model, so a freshly created node costs nothing to summarise.
    """
    transcript = _transcript(history)
    if not transcript.strip():
        return ""

    result = await _summary_agent(max_words).run(
        f"Summarise this conversation in at most {max_words} words:\n\n{transcript}"
    )
    return result.output.strip()
