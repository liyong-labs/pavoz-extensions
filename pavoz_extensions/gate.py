"""Quality gate — worker → multi-lens review → score → revise, as a decorator.

    @dag.stage(depends_on=["s_draft"], retries=0)
    @gate(
        reviewers={"method": lens_method, "limits": lens_limits},   # {lens: (result, ctx) -> (score, critique)}
        revise=revise_draft,                                       # (result, critique, ctx) -> result
        threshold=7.0, max_iter=3,
    )
    async def s_reviewed(ctx): ...

Semantics
---------
- The stage function runs **once**; the gate only re-runs ``revise`` on later
  iterations (so a worker that calls an LLM is not re-billed per iteration).
- ``aggregate="min"`` (default): the strictest lens decides — a lenient "structure"
  lens must not average away a strict "safety" lens.
- ``on_exhaustion="raise"`` (default) raises :class:`GateFailedError` (a
  ``StageError``, terminal — not retried). ``"best_effort"`` returns the
  highest-scoring result seen instead.
- Every round emits ``gate_score`` on ``ctx.on_event`` (observer exceptions are
  isolated, like the runtime's own events).
- The last round never calls ``revise`` (its output would be discarded).

Cost bound
----------
Per stage attempt: ``1 + max_iter * (len(reviewers) + 1)`` ``ctx.call``s. Keep
``retries=0`` on the decorated stage — the gate already owns rework, and
``dag.retries`` would multiply this bound.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal

from pavoz import StageError

__all__ = ["GateFailedError", "gate"]

Reviewer = Callable[[Any, Any], Awaitable[tuple[float, str]]]
Reviser = Callable[[Any, str, Any], Awaitable[Any]]


class GateFailedError(StageError):
    """Iteration budget exhausted without reaching the threshold (terminal)."""


def gate(
    reviewers: Mapping[str, Reviewer],
    revise: Reviser | None = None,
    *,
    threshold: float = 7.0,
    max_iter: int = 3,
    aggregate: Literal["min", "mean"] = "min",
    on_exhaustion: Literal["raise", "best_effort"] = "raise",
    concurrency: int = 1,
    event: str = "gate_score",
) -> Callable[[Callable], Callable]:
    """Decorate a stage fn with a review → score → revise convergence loop."""
    if not isinstance(reviewers, Mapping) or not reviewers:
        raise ValueError("gate: reviewers 必须是 {lens 名: 可调用} 且非空")
    if max_iter < 1:
        raise ValueError("gate: max_iter 必须 >= 1")
    if aggregate not in ("min", "mean"):
        raise ValueError(f"gate: aggregate 必须是 'min'/'mean', got {aggregate!r}")
    if on_exhaustion not in ("raise", "best_effort"):
        raise ValueError(f"gate: on_exhaustion 必须是 'raise'/'best_effort', got {on_exhaustion!r}")
    if concurrency < 1:
        raise ValueError("gate: concurrency 必须 >= 1")

    lenses = dict(reviewers)

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)  # stage 名取自 fn.__name__ — 丢了 wraps 会全部重名
        async def wrapper(ctx):
            result = await fn(ctx)
            best, best_score = None, float("-inf")

            for iteration in range(1, max_iter + 1):
                scored = await _run_reviewers(lenses, result, ctx, concurrency)
                score = _aggregate(scored, aggregate)
                _emit(ctx, event, {
                    "stage": _stage_name(ctx),
                    "iter": iteration,
                    "score": score,
                    "aggregate": aggregate,
                    "lenses": {name: s for name, (s, _) in scored.items()},
                })

                if score > best_score:
                    best, best_score = result, score
                if score >= threshold:
                    return best
                if iteration < max_iter and revise is not None:
                    result = await revise(result, _critiques(scored), ctx)

            if on_exhaustion == "best_effort" and best is not None:
                return best
            raise GateFailedError(
                f"gate 耗尽: best={best_score:.2f} < threshold={threshold} "
                f"({max_iter} iters, lenses={list(lenses)})"
            )

        return wrapper

    return deco


async def _run_reviewers(
    lenses: Mapping[str, Reviewer], result: Any, ctx: Any, concurrency: int
) -> dict[str, tuple[float, str]]:
    names = list(lenses)
    if concurrency <= 1 or len(names) == 1:
        return {name: await lenses[name](result, ctx) for name in names}

    # concurrency > 1: 调用方保证自己的 caller 能并发 (token 记账/落库)
    sem = asyncio.Semaphore(concurrency)

    async def one(name: str) -> tuple[str, tuple[float, str]]:
        async with sem:
            return name, await lenses[name](result, ctx)

    return dict(await asyncio.gather(*(one(name) for name in names)))


def _aggregate(scored: Mapping[str, tuple[float, str]], mode: str) -> float:
    for name, (value, _) in scored.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
            raise GateFailedError(f"gate: reviewer '{name}' 返回非法分数 {value!r}")
    scores = [float(value) for value, _ in scored.values()]
    if not scores:
        raise GateFailedError("gate: 没有任何 reviewer 返回分数")
    return min(scores) if mode == "min" else sum(scores) / len(scores)


def _critiques(scored: Mapping[str, tuple[float, str]]) -> str:
    return "\n".join(f"[{name}] {critique}" for name, (_, critique) in scored.items())


def _stage_name(ctx: Any) -> str:
    return getattr(ctx, "stage_name", "?")


def _emit(ctx: Any, event: str, payload: dict) -> None:
    """Observer 异常隔离 — 与 runtime 自身的 _emit 同语义, 观测崩了不影响 stage."""
    on_event = getattr(ctx, "on_event", None)
    if on_event is None:
        return
    try:
        on_event(event, payload)
    except Exception:
        logger = getattr(ctx, "logger", None)
        if logger is not None:
            logger.exception("gate: on_event 回调异常 (忽略) event=%s", event)
