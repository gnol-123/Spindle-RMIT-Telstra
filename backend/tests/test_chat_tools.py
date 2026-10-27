"""Tool nodes wired into a real agent turn, and recorded to tool_calls.

Covers the composition guard from the task brief, plus the recovery path:
a failing tool must not kill the run, and both calls must be recorded.
"""

from dataclasses import dataclass

import pytest
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.toolsets import ApprovalRequiredToolset, FunctionToolset

from app.tools.assembly import RecordingToolset, unavailable_note
from app.workflows import build_context_instructions


def test_context_and_unavailable_note_compose():
    note = unavailable_note(["Brave Search"])
    assert note is not None
    combined = "\n\n".join(p for p in [build_context_instructions([]), note] if p)
    assert "Brave Search" in combined


@dataclass
class _RecordedCall:
    tool_call_id: str
    tool_name: str
    status: str
    result: str | None = None
    error: str | None = None
    duration_ms: int | None = None


class _FakeToolRepo:
    """Records calls in a list. Never touches the database."""

    def __init__(self) -> None:
        self.calls: dict[str, _RecordedCall] = {}
        self._next_id = 0

    def record_call(
        self,
        *,
        project_id: str,
        conversation_id: str,
        agent_node_id: str,
        tool_node_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: dict,
        status: str,
    ) -> str:
        self._next_id += 1
        call_id = str(self._next_id)
        self.calls[call_id] = _RecordedCall(
            tool_call_id=tool_call_id, tool_name=tool_name, status=status
        )
        return call_id

    def finish_call(
        self,
        call_id: str,
        *,
        status: str,
        result: str | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        record = self.calls[call_id]
        record.status = status
        if result is not None:
            record.result = result
        if error is not None:
            record.error = error
        if duration_ms is not None:
            record.duration_ms = duration_ms


def _failing_tool() -> str:
    raise RuntimeError("boom")


def _working_tool() -> str:
    return "worked"


def _recording_toolset(repo: _FakeToolRepo) -> RecordingToolset:
    toolset = FunctionToolset()
    toolset.add_function(_failing_tool, name="failing_tool", retries=1)
    toolset.add_function(_working_tool, name="working_tool")
    return RecordingToolset(
        toolset,
        repo=repo,
        project_id="p1",
        conversation_id="c1",
        agent_node_id="a1",
        tool_node_id="t1",
    )


def _script_calls_then_answers(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Call failing_tool once, then working_tool, then answer.

    Waits for a return (or a retry prompt) on the outstanding call before
    issuing the next one, so a ModelRetry does not get resent forever.
    """
    tool_call_parts = [part for m in messages for part in m.parts if isinstance(part, ToolCallPart)]
    resolved_parts = [
        part
        for m in messages
        for part in m.parts
        if isinstance(part, ToolReturnPart | RetryPromptPart)
    ]
    if not tool_call_parts:
        return ModelResponse(parts=[ToolCallPart(tool_name="failing_tool", args={})])
    if len(resolved_parts) < len(tool_call_parts):
        return ModelResponse(parts=[])
    if len(tool_call_parts) == 1:
        return ModelResponse(parts=[ToolCallPart(tool_name="working_tool", args={})])
    return ModelResponse(parts=[TextPart(content="done")])


def test_failing_tool_recovers_and_records_both_calls():
    repo = _FakeToolRepo()
    toolset = _recording_toolset(repo)
    model = FunctionModel(_script_calls_then_answers)
    agent: Agent[None, str] = Agent(model, toolsets=[toolset])

    result = agent.run_sync("go")

    assert result.output == "done"
    assert len(repo.calls) == 2

    by_name = {c.tool_name: c for c in repo.calls.values()}
    assert by_name["failing_tool"].status == "error"
    assert by_name["failing_tool"].error is not None
    assert by_name["failing_tool"].duration_ms is not None

    assert by_name["working_tool"].status == "ok"
    assert by_name["working_tool"].result == "worked"
    assert by_name["working_tool"].duration_ms is not None


def test_result_is_truncated_before_storage():
    repo = _FakeToolRepo()

    def _huge_tool() -> str:
        return "x" * 10_000

    toolset = FunctionToolset()
    toolset.add_function(_huge_tool, name="huge_tool")
    recording = RecordingToolset(
        toolset,
        repo=repo,
        project_id="p1",
        conversation_id="c1",
        agent_node_id="a1",
        tool_node_id="t1",
    )

    def _call_once(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tool_call_parts = [
            part for m in messages for part in m.parts if isinstance(part, ToolCallPart)
        ]
        if not tool_call_parts:
            return ModelResponse(parts=[ToolCallPart(tool_name="huge_tool", args={})])
        return ModelResponse(parts=[TextPart(content="done")])

    model = FunctionModel(_call_once)
    agent: Agent[None, str] = Agent(model, toolsets=[recording])
    agent.run_sync("go")

    assert len(repo.calls) == 1
    record = next(iter(repo.calls.values()))
    assert record.result is not None
    assert len(record.result) == 8000


def test_approval_required_is_not_recorded_as_a_failure():
    """A tool that requires approval pauses the run; it did not fail.

    Wrapping order matches ``assemble()``: ``ApprovalRequiredToolset`` sits
    inside ``RecordingToolset``, exactly as ``record_calls`` builds it in
    chat.py, so ``super().call_tool`` raises ``ApprovalRequired`` before the
    wrapped tool ever runs.
    """
    repo = _FakeToolRepo()
    toolset = FunctionToolset()
    toolset.add_function(_working_tool, name="working_tool")
    recording = RecordingToolset(
        ApprovalRequiredToolset(toolset),
        repo=repo,
        project_id="p1",
        conversation_id="c1",
        agent_node_id="a1",
        tool_node_id="t1",
    )

    def _call_once(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(tool_name="working_tool", args={})])

    model = FunctionModel(_call_once)
    agent: Agent[None, str] = Agent(model, toolsets=[recording])

    # ApprovalRequired propagates out, never becomes ModelRetry: with no
    # DeferredToolRequests output type wired up (Task 10), pydantic-ai
    # surfaces it as UserError rather than looping the model on a retry.
    with pytest.raises(Exception) as excinfo:
        agent.run_sync("go")
    assert not isinstance(excinfo.value, ModelRetry)

    assert len(repo.calls) == 1
    record = next(iter(repo.calls.values()))
    assert record.status == "pending_approval"
    assert record.duration_ms is None
    assert record.error is None
