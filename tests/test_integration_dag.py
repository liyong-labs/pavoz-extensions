"""Integration: both decorators on real pavoz DAGs, via the real Runtime.

No network, no LLM — the "reviewers" are plain functions, which is the point:
the extensions do not know what an LLM is.
"""

from __future__ import annotations

from pavoz import DAG, CheckpointStore, FileStorage, Runtime

from pavoz_extensions import gate, schema

dag = DAG("extensions-integration")


def _require_report(delta):
    if not isinstance(delta.get("report"), str) or not delta["report"]:
        raise ValueError("report 必须是非空字符串")


async def _lens_mentions(result, ctx):
    ok = "convergence" in result["report"].lower()
    return (8.0 if ok else 3.0), ("mentions-topic: ok" if ok else "mentions-topic: missing")


async def _lens_signoff(result, ctx):
    ok = result["report"].rstrip().endswith("SIGNED-OFF")
    return (8.0 if ok else 3.0), ("signoff: ok" if ok else "signoff: missing")


async def _revise(result, critique, ctx):
    fixes = []
    if "mentions-topic" in critique:
        fixes.append("Section: convergence.")
    if "signoff" in critique:
        fixes.append("SIGNED-OFF")
    return {**result, "report": result["report"] + " " + " ".join(fixes)}


@dag.stage()
async def s_plan(ctx):
    return {"topic": "durable agents"}


@dag.stage(depends_on=["s_plan"], retries=0)  # retries=0: the gate owns rework
@gate({"topic": _lens_mentions, "signoff": _lens_signoff}, _revise, threshold=7.0, max_iter=3)
@schema(output=_require_report)               # 最内层: gate 的 worker 产出先过契约
async def s_draft(ctx):
    return {"report": f"Notes on {ctx.state['topic']}."}


@dag.stage(depends_on=["s_draft"])
async def s_publish(ctx):
    return {"published": ctx.state["report"]}


async def test_gate_and_schema_on_a_real_run():
    events: list[tuple[str, dict]] = []
    rt = Runtime(on_event=lambda e, d: events.append((e, d)))

    result = await rt.run(dag, task_id="ext-1")

    assert result.status == "done"
    assert result.state["published"].endswith("SIGNED-OFF")

    scores = [payload for event, payload in events if event == "gate_score"]
    assert [p["iter"] for p in scores] == [1, 2], "第一轮不达标 → revise → 第二轮达标"
    assert scores[0]["score"] < scores[1]["score"]


async def test_single_stage_replay_still_works_with_decorators(tmp_path):
    rt = Runtime(checkpoint_store=CheckpointStore(FileStorage(str(tmp_path))))
    assert (await rt.run(dag, task_id="ext-2")).status == "done"

    replayed = await rt.run_stage(dag, "ext-2", "s_draft")

    assert replayed.status == "done", "装饰器不破坏 run_stage 重放"


async def test_schema_violation_fails_the_run_not_retries():
    bad = DAG("extensions-bad")

    @bad.stage()
    async def s_src(ctx):
        return {"n": 1}

    @bad.stage(depends_on=["s_src"], retries=2)
    @schema(output=_require_report)
    async def s_sink(ctx):
        return {"other": 2}

    result = await Runtime().run(bad, task_id="ext-bad")

    assert result.status == "failed"
    assert "schema 违反" in (result.error or "")
    assert result.error_class in ("SchemaContractError", "StageError")
