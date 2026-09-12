# pavoz-extensions

🇬🇧 [English](README.md)

**草稿够好了才放行 —— 不够好就大声失败, 而不是悄悄放过。**

给 [pavoz](https://github.com/liyong-labs/pavoz) 流水线的两个装饰器:

- **`@gate`** —— 你的 stage 只跑一次, 之后 N 个 reviewer 从不同角度打分, 批评回喂给 `revise` 重做, 直到分数过阈值。N 轮还不达标? 直接抛错, 不会把不达标的产物静默发出去。
- **`@schema`** —— 校验 stage 的输入 state 与输出 delta 是否符合契约, 让上游的结构变更**当场**爆, 而不是五个 stage 之后才神秘失败。

两者都是包在 stage 函数外的普通装饰器:pavoz 核心零改动, 核心也永不依赖本包。

```python
@dag.stage(depends_on=["s_draft"], retries=0)
@gate({"facts": lens_facts, "tone": lens_tone}, revise=revise_draft, threshold=7.0)
async def s_reviewed(ctx):
    ...

#  [gate] iter=1 score=3.0 lenses={'facts': 3.0, 'tone': 3.0}   → revise
#  [gate] iter=2 score=8.0 lenses={'facts': 9.0, 'tone': 8.0}   → return
```

## 安装

```bash
pip install "pavoz @ git+https://github.com/liyong-labs/pavoz@main"
pip install --no-deps git+https://github.com/liyong-labs/pavoz-extensions@main
```

<sub>两个包都还没上 PyPI (0.1.0 开发中) —— 发布后一行搞定: `pip install pavoz-extensions`。</sub>

## `@gate` —— 审到够好为止

```python
from pavoz_extensions import gate

async def lens_facts(result, ctx):                    # 任意 async 可调用对象
    reply = await ctx.call("llm", "review", {"lens": "facts", "draft": result["report"]})
    return float(reply["score"]), reply["critique"]   # (分数, 批评)

async def revise(result, critique, ctx):
    reply = await ctx.call("llm", "revise", {"draft": result["report"], "critique": critique})
    return {**result, "report": reply["report"]}

@dag.stage(depends_on=["s_plan"], retries=0)          # retries=0: 返工由 gate 负责
@gate({"facts": lens_facts, "tone": lens_tone}, revise, threshold=7.0, max_iter=3)
async def s_draft(ctx): ...
```

- **你的 stage 只跑一次**。后续轮次只调 `revise` —— 不会每轮重复烧 worker 的 LLM 调用。
- **最严的 lens 说了算**(`aggregate="min"`, 默认)—— 宽松的"结构" lens 不能把严苛的"安全" lens 平均掉。想要平均就传 `"mean"`。
- **耗尽了默认大声失败** —— `GateFailedError`(是 `StageError`, 终态不重试)。想返回最高分那次, 传 `on_exhaustion="best_effort"`。
- **可观测** —— 每轮把 `gate_score` 写进 `ctx.on_event`, 分数历史进你已有的 trace。
- **成本有上界**:每次 attempt `1 + max_iter * (len(reviewers) + 1)` 次 `ctx.call`。
- `concurrency=N` 让各 lens 并发评审 —— 前提是你的 caller 能并发。

reviewer 就是普通可调用对象, 不需要 LLM:普通函数就行 —— 测试就是这么跑的(无网络、无 API key)。

## `@schema` —— stage 之间的契约

```python
from pavoz_extensions import schema

def report_shape(delta):
    if not isinstance(delta.get("report"), str):
        raise ValueError("report 必须是字符串")

@dag.stage(depends_on=["s_plan"])
@schema(input=require_topic, output=report_shape)
async def s_draft(ctx): ...
```

任何 `validate(obj) -> None` 可调用对象都行:抛异常=违反, 返回 `None`=通过。pydantic 是可选的 —— `pip install "pavoz-extensions[pydantic]"` 后直接传 `Model.model_validate`。

- `input` 在 stage 跑**之前**校验 `ctx.state`;`output` 校验返回的 delta
- 违反抛 `SchemaContractError`(终态;原异常保留在 `__cause__`)
- `warn_only=True` 只记日志不阻断 —— 适合在已在跑的流水线上逐步收紧契约

## 依赖

Python ≥ 3.12,`pavoz>=0.3,<0.4`。

## 文档

- [`docs/PRD.md`](docs/PRD.md) —— 范围、需求、成功指标
- [`docs/design.md`](docs/design.md) —— 契约、成本上界、兼容与 CI 设计

Apache-2.0(见 [LICENSE](LICENSE))。
