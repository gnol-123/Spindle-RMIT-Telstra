"""Usage capture: the getattr that was silently swallowing reasoning tokens.

The bug this pins: `_turn_from` read `usage.output_reasoning_tokens`, which
does not exist on pydantic-ai 2.x `RunUsage`. Every new row got NULL. The real
value lives in `usage.details` under a per-provider name.
"""

from dataclasses import dataclass

from pydantic_ai.usage import RunUsage

from app.workflows import _reasoning_from, _turn_from


def test_real_runusage_has_no_typed_reasoning_field():
    # If this ever fails, pydantic-ai added the field and _reasoning_from can
    # prefer it. Until then, details is the only source.
    assert not hasattr(RunUsage(), "output_reasoning_tokens")


def test_reasoning_read_from_details_per_provider():
    for key in ("reasoning_tokens", "thinking_tokens", "thoughts_tokens"):
        assert _reasoning_from(RunUsage(details={key: 452})) == 452


def test_reasoning_none_when_absent():
    assert _reasoning_from(RunUsage()) is None
    assert _reasoning_from(RunUsage(details={"audio_tokens": 12})) is None
    # Non-int values must not land in an integer column.
    assert _reasoning_from(RunUsage(details={"reasoning_tokens": "nope"})) is None


def test_zero_reasoning_is_kept_not_dropped():
    # 0 is a real answer from a non-reasoning model; None means "unknown".
    assert _reasoning_from(RunUsage(details={"reasoning_tokens": 0})) == 0


def test_turn_from_captures_every_field():
    usage = RunUsage(
        input_tokens=100,
        output_tokens=2000,
        cache_read_tokens=80,
        cache_write_tokens=20,
        requests=3,
        details={"reasoning_tokens": 1900},
    )
    turn = _turn_from("hi", "deepseek-v4.1-flash", usage)

    assert turn.input_tokens == 100
    assert turn.output_tokens == 2000
    assert turn.reasoning_tokens == 1900
    assert turn.cache_read_tokens == 80
    assert turn.cache_write_tokens == 20
    assert turn.requests == 3
    # Reasoning is a subset of output, never an addend.
    assert turn.reasoning_tokens < turn.output_tokens


def test_paused_turn_keeps_its_usage():
    """A pause burned tokens. Only `output` is unsafe to carry."""
    from app.workflows import _turn_from_result

    @dataclass
    class FakeResult:
        output: object
        usage_obj: object

        def usage(self):  # pragma: no cover - shape only
            return self.usage_obj

        def all_messages(self):
            return []

    from pydantic_ai import DeferredToolRequests

    usage = RunUsage(input_tokens=50, output_tokens=10, details={"reasoning_tokens": 4})
    result = FakeResult(output=DeferredToolRequests(), usage_obj=usage)
    result.usage = usage  # attribute, matching pydantic-ai's RunResult

    turn = _turn_from_result(result, "deepseek-v4.1-flash")

    assert turn.paused
    assert turn.output == ""
    assert turn.input_tokens == 50
    assert turn.reasoning_tokens == 4
