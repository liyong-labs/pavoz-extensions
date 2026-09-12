# pavoz-extensions

Official extension pack for [**pavoz**](https://github.com/liyong-labs/pavoz) — the in-process Python DAG workflow engine (stdlib only, zero runtime deps).

**Status**: 0.1.0 in development — not yet on PyPI. Design docs are ready:

- [`docs/PRD.md`](docs/PRD.md) — product scope, requirements, success criteria
- [`docs/design.md`](docs/design.md) — `@gate` / `@schema` contracts, compat & CI design

## Planned for 0.1.0

| Extension | What it does |
|---|---|
| `@gate` | Quality convergence loop: worker → N reviewers (multi-lens) → score → revise → converge. Threshold gate, `min`/`mean` aggregation, bounded iterations, observable via `on_event`. |
| `@schema` | Contract validation between stages: check `ctx.state` on the way in and the returned delta on the way out. Any `validate(obj) -> None` callable (pydantic is an optional extra, not a dependency). |

Both are **plain decorators** over stage functions — pavoz core needs no changes, and pavoz core never depends on this package.

## Requirements

- Python ≥ 3.12
- `pavoz>=0.3,<0.4`

## License

Apache-2.0 (see [LICENSE](LICENSE)).
