# pavoz-extensions

Official extension pack for [**pavoz**](https://github.com/liyong-labs/pavoz) — the in-process Python DAG workflow engine (stdlib only, zero runtime deps).

Two plain decorators over stage functions. pavoz core needs no changes, and core never depends on this package.

## Install

0.1.0 is not on PyPI yet:

```bash
pip install "pavoz>=0.3,<0.4"
pip install git+https://github.com/liyong-labs/pavoz-extensions
```

## `@gate` — quality convergence loop

```python
from pavoz import DAG
from pavoz_extensions import gate

async def lens_facts(result, ctx):
    reply = await ctx.call("llm", "review", {"lens": "facts", "draft": result["report"]})
    return float(reply["score"]), reply["critique"]

async def revise(result, critique, ctx):
    reply = await ctx.call("llm", "revise", {"draft": result["report"], "critique": critique})
    return {**result, "report": reply["report"]}

dag = DAG("pipeline")

@dag.stage(depends_on=["s_plan"], retries=0)      # retries=0: the gate owns rework
@gate({"facts": lens_facts}, revise, threshold=7.0, max_iter=3)
async def s_draft(ctx):
    ...
```

- the stage function runs **once**; later rounds only call `revise` (no re-billing a worker LLM per round)
- `aggregate="min"` (default) — the strictest lens decides, so a lenient lens cannot average away a strict one; `"mean"` is available
- `on_exhaustion="raise"` (default) raises `GateFailedError` (a `StageError` → terminal, not retried); `"best_effort"` returns the highest-scoring result instead
- every round emits `gate_score` on `ctx.on_event` (observer exceptions are isolated)
- **cost bound** per attempt: `1 + max_iter * (len(reviewers) + 1)` `ctx.call`s
- `concurrency=N` reviews lenses in parallel — your caller must then be concurrency-safe

## `@schema` — cross-stage contracts

```python
from pavoz_extensions import schema

def report_shape(delta):
    if not isinstance(delta.get("report"), str):
        raise ValueError("report 必须是字符串")

@dag.stage(depends_on=["s_plan"])
@schema(input=check_state, output=report_shape)
async def s_draft(ctx):
    ...
```

Any `validate(obj) -> None` callable works — raise anything to violate, return `None` to pass. pydantic is **optional** (`pip install "pavoz-extensions[pydantic]"`); pass `Model.model_validate` directly.

- `input` validates `ctx.state` before the stage runs; `output` validates the returned delta
- violations raise `SchemaContractError` (terminal; original exception preserved in `__cause__`)
- `warn_only=True` logs instead of raising — useful when tightening contracts on a live pipeline

## Docs

- [`docs/PRD.md`](docs/PRD.md) — scope, requirements, success criteria
- [`docs/design.md`](docs/design.md) — contracts, cost bounds, compatibility & CI design

## Requirements

- Python ≥ 3.12
- `pavoz>=0.3,<0.4`

## License

Apache-2.0 (see [LICENSE](LICENSE)).
