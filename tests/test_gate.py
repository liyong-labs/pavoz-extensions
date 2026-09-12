"""@gate unit tests — no LLM, no network, plain functions as lenses."""

from __future__ import annotations

import logging

import pytest

from pavoz import StageError

from pavoz_extensions import GateFailedError, gate


class _Ctx:
    """Minimal Ctx stand-in: gate only touches state / stage_name / on_event / logger."""

    def __init__(self, state=None, on_event=None, stage_name="s_test"):
        self.state = state if state is not None else {}
        self.on_event = on_event
        self.stage_name = stage_name
        self.logger = logging.getLogger("pavoz_extensions.test")


def _lens(score, critique="ok"):
    async def reviewer(result, ctx):
        return score, critique
    return reviewer


async def test_passes_first_round_without_revise():
    reviser_calls = []

    async def revise(result, critique, ctx):
        reviser_calls.append(critique)
        return result

    @gate({"a": _lens(9.0)}, revise, threshold=7.0)
    async def stage(ctx):
        return {"value": 1}

    assert await stage(_Ctx()) == {"value": 1}
    assert reviser_calls == []


async def test_converges_after_revise():
    async def reviewer(result, ctx):
        return (9.0 if result.get("fixed") else 3.0), "fix it"

    async def revise(result, critique, ctx):
        assert critique == "[lens] fix it"
        return {**result, "fixed": True}

    @gate({"lens": reviewer}, revise, threshold=7.0, max_iter=3)
    async def stage(ctx):
        return {"fixed": False}

    assert await stage(_Ctx()) == {"fixed": True}


async def test_worker_runs_once_across_iterations():
    worker_calls = {"n": 0}

    async def reviewer(result, ctx):
        return 1.0, "never good enough"

    async def revise(result, critique, ctx):
        return result

    @gate({"a": reviewer}, revise, threshold=7.0, max_iter=3)
    async def stage(ctx):
        worker_calls["n"] += 1
        return {"v": worker_calls["n"]}

    with pytest.raises(GateFailedError):
        await stage(_Ctx())
    assert worker_calls["n"] == 1, "worker 只应跑一次 (revise 负责后续迭代)"


async def test_last_round_does_not_call_revise():
    revise_calls = {"n": 0}

    async def reviewer(result, ctx):
        return 1.0, "nope"

    async def revise(result, critique, ctx):
        revise_calls["n"] += 1
        return result

    @gate({"a": reviewer}, revise, threshold=7.0, max_iter=3)
    async def stage(ctx):
        return {"v": 1}

    with pytest.raises(GateFailedError):
        await stage(_Ctx())
    assert revise_calls["n"] == 2, "max_iter=3 → 末轮不 revise, 共 2 次"


async def test_exhaustion_raises_gate_failed_error_which_is_stage_error():
    @gate({"a": _lens(1.0)}, None, threshold=7.0)
    async def stage(ctx):
        return {"v": 1}

    with pytest.raises(GateFailedError) as excinfo:
        await stage(_Ctx())
    assert isinstance(excinfo.value, StageError), "必须继承核心异常, 不引入新异常根"


async def test_best_effort_returns_highest_scoring_result():
    scores = iter([3.0, 6.0, 1.0])

    async def reviewer(result, ctx):
        return next(scores), "c"

    async def revise(result, critique, ctx):
        return {"round": result["round"] + 1}

    @gate({"a": reviewer}, revise, threshold=7.0, max_iter=3, on_exhaustion="best_effort")
    async def stage(ctx):
        return {"round": 0}

    assert await stage(_Ctx()) == {"round": 1}, "应返回 6.0 那一轮 (第 2 轮) 的产物"


async def test_aggregate_min_is_stricter_than_mean():
    async def good(result, ctx):
        return 9.0, "ok"

    async def mediocre(result, ctx):
        return 6.0, "meh"

    @gate({"good": good, "mediocre": mediocre}, None, threshold=7.0, aggregate="min")
    async def strict(ctx):
        return {"v": 1}

    @gate({"good": good, "mediocre": mediocre}, None, threshold=7.0, aggregate="mean")
    async def averaged(ctx):
        return {"v": 1}

    with pytest.raises(GateFailedError):
        await strict(_Ctx())
    assert await averaged(_Ctx()) == {"v": 1}, "mean=(9+6)/2=7.5 ≥ 7 应通过"


async def test_review_is_skipped_when_revise_is_none():
    @gate({"a": _lens(1.0)}, None, threshold=7.0, max_iter=2)
    async def stage(ctx):
        return {"v": 1}

    with pytest.raises(GateFailedError):
        await stage(_Ctx())


async def test_emits_gate_score_events_with_every_lens():
    events = []

    async def reviewer(result, ctx):
        return 5.0, "c"

    @gate({"lens-x": reviewer, "lens-y": _lens(8.0)}, None, threshold=7.0, max_iter=1)
    async def stage(ctx):
        return {"v": 1}

    with pytest.raises(GateFailedError):
        await stage(_Ctx(on_event=lambda e, d: events.append((e, d))))

    assert len(events) == 1
    event, payload = events[0]
    assert event == "gate_score"
    assert payload["stage"] == "s_test"
    assert payload["iter"] == 1
    assert payload["score"] == 5.0  # min
    assert set(payload["lenses"]) == {"lens-x", "lens-y"}


async def test_observer_exception_does_not_break_the_stage():
    def boom(event, data):
        raise RuntimeError("observer is broken")

    @gate({"a": _lens(9.0)}, None, threshold=7.0)
    async def stage(ctx):
        return {"v": 1}

    assert await stage(_Ctx(on_event=boom)) == {"v": 1}


async def test_no_on_event_is_a_noop():
    @gate({"a": _lens(9.0)}, None, threshold=7.0)
    async def stage(ctx):
        return {"v": 1}

    assert await stage(_Ctx(on_event=None)) == {"v": 1}


async def test_concurrent_reviewers_all_run():
    order = []

    def make(name, score):
        async def reviewer(result, ctx):
            order.append(name)
            return score, "c"
        return reviewer

    @gate({"a": make("a", 9.0), "b": make("b", 8.0)}, None, threshold=7.0, concurrency=2)
    async def stage(ctx):
        return {"v": 1}

    assert await stage(_Ctx()) == {"v": 1}
    assert sorted(order) == ["a", "b"]


async def test_decorator_preserves_stage_name():
    @gate({"a": _lens(9.0)}, None, threshold=7.0)
    async def s_my_stage(ctx):
        return {"v": 1}

    assert s_my_stage.__name__ == "s_my_stage", "dag 用 fn.__name__ 当 stage 名"


async def test_reviewer_exception_propagates_unwrapped():
    async def broken(result, ctx):
        raise ValueError("reviewer blew up")

    @gate({"a": broken}, None, threshold=7.0)
    async def stage(ctx):
        return {"v": 1}

    with pytest.raises(ValueError, match="reviewer blew up"):
        await stage(_Ctx())


@pytest.mark.parametrize("bad_score", [None, "high", float("nan")])
async def test_non_numeric_score_fails_loudly(bad_score):
    async def reviewer(result, ctx):
        return bad_score, "c"

    @gate({"a": reviewer}, None, threshold=7.0)
    async def stage(ctx):
        return {"v": 1}

    with pytest.raises(GateFailedError, match="非法分数"):
        await stage(_Ctx())


@pytest.mark.parametrize("kwargs", [
    {"reviewers": {}},
    {"reviewers": {"a": _lens(9.0)}, "max_iter": 0},
    {"reviewers": {"a": _lens(9.0)}, "aggregate": "median"},
    {"reviewers": {"a": _lens(9.0)}, "on_exhaustion": "ignore"},
    {"reviewers": {"a": _lens(9.0)}, "concurrency": 0},
])
def test_invalid_configuration_fails_at_decoration_time(kwargs):
    with pytest.raises(ValueError):
        gate(**kwargs)
