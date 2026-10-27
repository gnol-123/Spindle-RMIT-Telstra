"""Per-user and per-project usage reads.

The per-user path re-aggregates by model across projects. Rows are keyed
(project_id, owner_id, model), so the same model appears once per project and
must be summed, not overwritten: that is what a cap reads.
"""

from unittest.mock import MagicMock

from app.repositories.project_repo import ProjectRepository, UsageTotal


def _row(model, inp, out, reasoning=0, cache_r=0, cache_w=0, requests=1, messages=1):
    return {
        "model": model,
        "input_tokens": inp,
        "output_tokens": out,
        "reasoning_tokens": reasoning,
        "cache_read_tokens": cache_r,
        "cache_write_tokens": cache_w,
        "requests": requests,
        "message_count": messages,
    }


def _repo_returning(rows):
    client = MagicMock()
    chain = client.table.return_value
    for method in ("select", "eq", "order", "limit"):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = MagicMock(data=rows)
    return ProjectRepository(client, "user-1")


def test_user_usage_sums_same_model_across_projects():
    repo = _repo_returning(
        [
            _row("deepseek-v4.1-flash", 100, 200, reasoning=50, requests=1, messages=2),
            _row("deepseek-v4.1-flash", 10, 20, reasoning=5, requests=3, messages=1),
        ]
    )
    (total,) = repo.get_user_usage()

    assert total == UsageTotal(
        model="deepseek-v4.1-flash",
        input_tokens=110,
        output_tokens=220,
        reasoning_tokens=55,
        cache_read_tokens=0,
        cache_write_tokens=0,
        requests=4,
        message_count=3,
    )


def test_user_usage_keeps_models_separate():
    repo = _repo_returning([_row("a", 1, 2), _row("b", 4, 8)])
    got = {t.model: t for t in repo.get_user_usage()}

    assert set(got) == {"a", "b"}
    assert got["a"].input_tokens == 1
    assert got["b"].input_tokens == 4


def test_user_usage_does_not_mutate_source_rows():
    # setdefault(dict(r)) copies; a shared reference would double-count the
    # first row into itself on the next match.
    rows = [_row("m", 5, 6), _row("m", 5, 6)]
    repo = _repo_returning(rows)
    (total,) = repo.get_user_usage()

    assert total.input_tokens == 10
    assert rows[0]["input_tokens"] == 5, "source row mutated"


def test_user_usage_sorted_by_output_desc():
    repo = _repo_returning([_row("small", 1, 5), _row("big", 1, 500), _row("mid", 1, 50)])
    assert [t.model for t in repo.get_user_usage()] == ["big", "mid", "small"]


def test_user_usage_empty():
    assert _repo_returning([]).get_user_usage() == []


def test_project_usage_scoped_to_caller_and_project():
    repo = _repo_returning([_row("m", 1, 2)])
    repo.get_usage("proj-1")

    chain = repo._db.table.return_value
    eq_args = dict(c.args for c in chain.eq.call_args_list)
    assert eq_args["owner_id"] == "user-1", "not scoped to caller"
    assert eq_args["project_id"] == "proj-1"


def test_user_usage_scoped_to_caller_not_project():
    repo = _repo_returning([_row("m", 1, 2)])
    repo.get_user_usage()

    chain = repo._db.table.return_value
    eq_args = dict(c.args for c in chain.eq.call_args_list)
    assert eq_args == {"owner_id": "user-1"}, "per-user read must span projects"
