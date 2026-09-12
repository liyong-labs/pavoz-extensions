# pavoz-extensions

🇨🇳 [简体中文](README.cn.md)

**Ship a draft only when it's good enough — and fail loudly when it isn't.**

Two decorators for [pavoz](https://github.com/liyong-labs/pavoz) pipelines:

- **`@gate`** — runs your stage once, has N reviewers score the result from different angles, feeds the critiques back for a rewrite, and repeats until the score clears your threshold. Not good enough after N rounds? It raises instead of quietly shipping garbage.
- **`@schema`** — validates a stage's input state and output delta against your contract, so an upstream shape change fails *right there* instead of five stages later.

Both are plain decorators over stage functions. pavoz core needs no changes, and core never depends on this package.

```python
@dag.stage(depends_on=["s_draft"], retries=0)
@gate({"facts": lens_facts, "tone": lens_tone}, revise=revise_draft, threshold=7.0)
async def s_reviewed(ctx):
    ...

#  [gate] iter=1 score=3.0 lenses={'facts': 3.0, 'tone': 3.0}   → revise
#  [gate] iter=2 score=8.0 lenses={'facts': 9.0, 'tone': 8.0}   → return
```

## Install

```bash
pip install "pavoz @ git+https://github.com/liyong-labs/pavoz@main"
pip install --no-deps git+https://github.com/liyong-labs/pavoz-extensions@main
```

<sub>Neither package is on PyPI yet (0.1.0 in development) — once they are, this becomes `pip install pavoz-extensions`.</sub>

## `@gate` — review until it's good

```python
from pavoz_extensions import gate

async def lens_facts(result, ctx):                    # any async callable
    reply = await ctx.call("llm", "review", {"lens": "facts", "draft": result["report"]})
    return float(reply["score"]), reply["critique"]   # (score, critique)

async def revise(result, critique, ctx):
    reply = await ctx.call("llm", "revise", {"draft": result["report"], "critique": critique})
    return {**result, "report": reply["report"]}

@dag.stage(depends_on=["s_plan"], retries=0)          # retries=0: the gate owns rework
@gate({"facts": lens_facts, "tone": lens_tone}, revise, threshold=7.0, max_iter=3)
async def s_draft(ctx): ...
```

- **Your stage runs once.** Later rounds only call `revise` — a worker LLM is not re-billed per round.
- **The strictest lens decides** (`aggregate="min"`, the default) — a lenient "structure" lens can't average away a strict "safety" one. `"mean"` if you prefer.
- **Exhaustion is loud by default** — `GateFailedError`, a `StageError`, terminal and not retried. `on_exhaustion="best_effort"` returns the best-scoring attempt instead.
- **Observable** — every round emits `gate_score` on `ctx.on_event`, so score history lands in your existing trace.
- **Cost is bounded**: `1 + max_iter * (len(reviewers) + 1)` `ctx.call`s per attempt.
- `concurrency=N` reviews lenses in parallel — then your caller must be concurrency-safe.

Reviewers are ordinary callables. No LLM required: a plain function works, which is how the tests run (no network, no API keys).

## `@schema` — contracts between stages

```python
from pavoz_extensions import schema

def report_shape(delta):
    if not isinstance(delta.get("report"), str):
        raise ValueError("report 必须是字符串")

@dag.stage(depends_on=["s_plan"])
@schema(input=require_topic, output=report_shape)
async def s_draft(ctx): ...
```

Any `validate(obj) -> None` callable: raise to violate, return `None` to pass. pydantic is optional — `pip install "pavoz-extensions[pydantic]"` and pass `Model.model_validate` directly.

- `input` checks `ctx.state` *before* the stage runs; `output` checks the returned delta
- a violation raises `SchemaContractError` (terminal; the original exception is preserved in `__cause__`)
- `warn_only=True` logs instead of raising — for tightening contracts on a running pipeline

## Requirements

Python ≥ 3.12 and `pavoz>=0.3,<0.4`.

## Docs

- [`docs/PRD.md`](docs/PRD.md) — scope, requirements, success criteria
- [`docs/design.md`](docs/design.md) — contracts, cost bounds, compatibility & CI design

Apache-2.0 (see [LICENSE](LICENSE)).
