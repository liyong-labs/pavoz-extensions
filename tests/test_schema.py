"""@schema unit tests — validators are plain callables, no pydantic required."""

from __future__ import annotations

import logging

import pytest

from pavoz import StageError

from pavoz_extensions import SchemaContractError, schema


class _Ctx:
    def __init__(self, state=None, stage_name="s_test"):
        self.state = state if state is not None else {}
        self.stage_name = stage_name
        self.logger = logging.getLogger("pavoz_extensions.test")


def _require_report(delta):
    if "report" not in delta:
        raise ValueError("缺少 report")


async def test_output_violation_raises_terminal_contract_error():
    @schema(output=_require_report)
    async def stage(ctx):
        return {"other": 1}

    with pytest.raises(SchemaContractError) as excinfo:
        await stage(_Ctx())
    assert isinstance(excinfo.value, StageError)
    assert isinstance(excinfo.value.__cause__, ValueError), "原始异常保留在 __cause__"
    assert "s_test" in str(excinfo.value)


async def test_input_violation_raises_before_running_the_stage():
    ran = {"n": 0}

    def need_topic(state):
        if not state.get("topic"):
            raise KeyError("topic")

    @schema(input=need_topic)
    async def stage(ctx):
        ran["n"] += 1
        return {"ok": True}

    with pytest.raises(SchemaContractError, match="input"):
        await stage(_Ctx())
    assert ran["n"] == 0, "输入校验失败时 stage 不应执行"


async def test_passing_validators_return_the_delta_untouched():
    delta = {"report": "x", "n": 2}

    @schema(input=lambda state: None, output=_require_report)
    async def stage(ctx):
        return delta

    assert await stage(_Ctx()) is delta


async def test_warn_only_logs_instead_of_raising(caplog):
    @schema(output=_require_report, warn_only=True)
    async def stage(ctx):
        return {"other": 1}

    with caplog.at_level(logging.WARNING, logger="pavoz_extensions.test"):
        assert await stage(_Ctx()) == {"other": 1}
    assert "schema 违反" in caplog.text


def test_at_least_one_validator_is_required():
    with pytest.raises(ValueError, match="至少需要一个"):
        schema()


def test_validators_must_be_callable():
    with pytest.raises(ValueError, match="可调用"):
        schema(input="not-a-function")


async def test_pydantic_style_validator_works_without_pydantic():
    """任何 ``obj -> None`` (违规时抛异常) 都可当校验器, 例如 pydantic 的 model_validate."""

    class FakeModel:
        @staticmethod
        def model_validate(delta):
            if not isinstance(delta.get("n"), int):
                raise ValueError("n must be int")
            return delta

    @schema(output=FakeModel.model_validate)
    async def stage(ctx):
        return {"n": "not-an-int"}

    with pytest.raises(SchemaContractError):
        await stage(_Ctx())


async def test_decorator_preserves_stage_name():
    @schema(output=lambda delta: None)
    async def s_named(ctx):
        return {}

    assert s_named.__name__ == "s_named"


async def test_label_overrides_stage_name_in_message():
    @schema(output=_require_report, label="my-contract")
    async def stage(ctx):
        return {}

    with pytest.raises(SchemaContractError, match="my-contract"):
        await stage(_Ctx())
