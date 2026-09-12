"""Cross-stage contract validation — as a decorator.

    def draft_shape(delta):                 # 任意 Callable[[Any], None]
        assert "report" in delta, "缺少 report"

    @dag.stage(depends_on=["s_plan"])
    @schema(input=state_shape, output=draft_shape)
    async def s_draft(ctx): ...

Validators are plain callables: raise anything to signal a violation, return
``None`` to pass. pydantic is *not* required (``pip install
"pavoz-extensions[pydantic]"`` if you want to pass ``Model.model_validate``);
anything with that shape works.

- ``input`` validates ``ctx.state`` before the stage runs
- ``output`` validates the returned delta dict
- violation → :class:`SchemaContractError` (a ``StageError``, terminal — not
  retried), with the original exception as ``__cause__``
- ``warn_only=True`` logs instead of raising (useful when tightening contracts
  on an existing pipeline)
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from pavoz import StageError

__all__ = ["SchemaContractError", "schema"]

Validator = Callable[[Any], None]


class SchemaContractError(StageError):
    """A stage's input or output violated its declared contract (terminal)."""


def schema(
    *,
    input: Validator | None = None,
    output: Validator | None = None,
    warn_only: bool = False,
    label: str = "",
) -> Callable[[Callable], Callable]:
    """Decorate a stage fn with input/output contract validation."""
    if input is None and output is None:
        raise ValueError("schema: 至少需要一个 input / output 校验函数")
    if input is not None and not callable(input):
        raise ValueError("schema: input 必须可调用")
    if output is not None and not callable(output):
        raise ValueError("schema: output 必须可调用")

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(ctx):
            name = label or getattr(ctx, "stage_name", "") or fn.__name__
            if input is not None:
                _validate(input, ctx.state, "input", name, ctx, warn_only)
            delta = await fn(ctx)
            if output is not None:
                _validate(output, delta, "output", name, ctx, warn_only)
            return delta

        return wrapper

    return deco


def _validate(
    validator: Validator, value: Any, side: str, stage: str, ctx: Any, warn_only: bool
) -> None:
    try:
        validator(value)
    except Exception as exc:
        message = f"schema 违反: stage={stage} {side} 校验失败: {type(exc).__name__}: {exc}"
        if warn_only:
            logger = getattr(ctx, "logger", None)
            if logger is not None:
                logger.warning(message)
            return
        raise SchemaContractError(message) from exc
