# Design — pavoz-extensions 0.1.0

**日期**: 2026-09-13
**状态**: 定稿待实施
**关联**: `docs/PRD.md` · pavoz `docs/design/extension-plan-2026-09-13.md`

---

## 1. 总览

```
pavoz_extensions/
├── __init__.py     # 版本 + 兼容性校验 (stdlib, import 时执行)
├── gate.py         # @gate   —— 质量收敛小循环
└── schema.py       # @schema —— 跨 stage 契约校验
```

**设计立场**: 两者都是**纯装饰器**, 包在 stage 函数外, 不触碰 pavoz 运行时, 不新增核心 API。
依据: `pavoz.dag.DAG.stage()` 接收任意 `NodeFn` (`async def(ctx) -> dict`), 装饰器在注册前包一层即可。

**边界规则** (CI 强制, §6):
- 只允许 `from pavoz import ...` 顶层导入
- 不 import `pavoz.runtime` / `pavoz.types` / `pavoz.state` 等子模块
- 不 monkeypatch, 不读写核心私有属性

---

## 2. `@gate` 设计

### 2.1 签名

```python
def gate(
    reviewers: Mapping[str, Callable[[Any, Ctx], Awaitable[tuple[float, str]]]],
    revise: Callable[[Any, str, Ctx], Awaitable[Any]] | None = None,
    *,
    threshold: float = 7.0,
    max_iter: int = 3,
    aggregate: Literal["min", "mean"] = "min",
    on_exhaustion: Literal["raise", "best_effort"] = "raise",
    concurrency: int = 1,
    event: str = "gate_score",
) -> Callable[[NodeFn], NodeFn]
```

| 参数 | 语义 |
|---|---|
| `reviewers` | `{lens 名: 可调用}` — 每个返回 `(score, critique)`; score 与 `threshold` 同尺度 (默认 0–10)。lens 名进事件 payload, 所以用 Mapping 而非裸序列。可为 async 函数, 内部通常 `await ctx.call("llm", ...)` |
| `revise` | 把 critique 喂回, 产出下一版; `None` 时只评分不改 (只用于观测/日志) |
| `threshold` | 达标线; `score >= threshold` 即收敛 |
| `max_iter` | 最大迭代轮数 (含首轮); ≥1 |
| `aggregate` | `min` (默认, 最严一票否决) / `mean` |
| `on_exhaustion` | `raise` (默认, 抛 `GateFailedError(StageError)`) / `best_effort` (返回最高分产物) |
| `concurrency` | `1` = 串行 (默认); `>1` 时同一轮的 reviewer 并发 (`asyncio.Semaphore(N)` + `gather`), 结果按 lens 声明顺序回收 |
| `event` | 事件名 (默认 `gate_score`), 需要区分多个 gate 时可改 |

### 2.2 控制流

```
assert reviewers 非空 and max_iter >= 1
draft = await worker(ctx)                 # 只跑一次
best, best_score = None, -inf
for i in 1..max_iter:
    pairs = await run_reviewers(draft, ctx)          # 串行或按 concurrency 分块 gather
    score = min|mean(s for s, _ in pairs)
    emit gate_score {stage, iter: i, scores: [...], score}   # ctx.on_event
    if score > best_score: best, best_score = draft, score
    if score >= threshold: return best
    if i < max_iter and revise is not None:
        draft = await revise(draft, "\n".join(critiques), ctx)
if on_exhaustion == "best_effort": return best
raise GateFailedError(f"gate 耗尽: best={best_score} < {threshold} ({max_iter} iters)")
```

要点:
- **worker 只跑一次** (`revise` 负责后续迭代), 避免"每轮重跑 worker"的成本失控
- **末轮不调用 `revise`** (产物不会被用到)
- **返回 `best` 而非最后一份**: revise 可能改坏, 返回历史最高分产物; 若 `best` 为空 (worker 首轮即失败) 则由异常路径处理

### 2.3 边界与错误

| 情况 | 行为 |
|---|---|
| `reviewers` 为空 / `max_iter < 1` | 入口 `ValueError` (编程错误, 不是运行时失败) |
| reviewer 抛异常 | 不吞: 直接向上抛 (由 stage 的 `retries`/异常契约接管); `GateFailedError` 只在"评分正常但未达标"时出现 |
| `revise=None` 且未达标 | 直接进入耗尽逻辑 (无可重做) |
| `best_effort` 且 `best is None` | 抛 `GateFailedError` (没有可返回的产物) |
| score 非数值 / NaN | reviewer 契约违反 → 抛 `GateFailedError` (附带 lens 名) |

### 2.4 成本

- 上界: `1 + max_iter × (|reviewers| + 1)` 次 `ctx.call` (worker 1 次; 每轮 |reviewers| + 1 次 revise, 末轮省 1)
- **与 `@dag.stage(retries=N)` 相乘**: gate 耗尽抛 `StageError` (不可重试) 是默认, 断了乘法; 若调用方显式用 `RetryableError` 语义, 成本 = `(N+1) × 上界` —— README 必须写明
- README 推荐: gate stage 用 `retries=0`; 瞬时错误 (429/5xx) 由 caller 层退避重试 (它才是发 HTTP 的那层)

### 2.5 并发

默认串行。`concurrency > 1` 用 `asyncio.gather` 分块; **调用方负责 caller 的并发安全** (token 记账 / 落库)。文档明示, 库不做检测。

---

## 3. `@schema` 设计

```python
def schema(
    input: Callable[[Mapping[str, Any]], None] | None = None,
    output: Callable[[Any], None] | None = None,
    warn_only: bool = False,
) -> Callable[[NodeFn], NodeFn]
```

| 参数 | 语义 |
|---|---|
| `input` | 跑 stage 前校验 `ctx.state` (只读视图); 传 `None` 跳过 |
| `output` | 跑完校验返回的 delta dict |
| `warn_only` | `True` = 违规只记 logger.warning, 不阻断 (渐进收紧用) |

- **校验函数协议**: 接受一个对象, 违规时抛任意异常 (`ValueError` / pydantic `ValidationError` 均可), 返回 `None` 表示通过。**不绑定 pydantic** —— pydantic 仅作 `[pydantic]` extra 与文档示例。
- **异常**: 违规 → `SchemaContractError(StageError)` (终态, 不重试), `__cause__` 指向原始校验异常。
- **放置**: 与 `@dag.stage()` 的装饰顺序无关 (内外皆可), 但**推荐 `@schema` 紧贴函数** (最内层), 便于单测直接调用。

---

## 4. 异常契约 (与核心一致)

| 异常 | 基类 | 语义 |
|---|---|---|
| `GateFailedError` | `pavoz.StageError` | 评分轮耗尽仍未达标 → 终态, 不重试 |
| `SchemaContractError` | `pavoz.StageError` | 契约违反 → 终态 |

两者都可由调用方捕获降级 (如 `try/except StageError` 走人工兜底)。**不引入新异常根**。

---

## 5. 兼容与版本

- `pyproject.toml`: `dependencies = ["pavoz>=0.3,<0.4"]`
- `pavoz_extensions/__init__.py` import 时用 stdlib 解析 `pavoz.__version__`, 越界给出明确 `RuntimeError` (含建议命令), 而不是等深层 `AttributeError`
- **不加 `__pavoz_api_version__` 常量** (pavoz 侧决议 ②): 单一版本源, 避免第二个漂移点
- CI 矩阵: `pavoz` 最低支持版本 (0.3.0) × 最新版本

---

## 6. CI 设计

两个 job:

**① 版本矩阵** — `pytest` 在两个 pavoz 版本下各跑一遍 (最低支持 × 最新)。

**② 结构检查** — 强制"只用公开 API"。草案 (stdlib `ast`, ~20 行):

```python
# tools/check_public_api.py
import ast, pathlib, sys

FORBIDDEN = ("pavoz.runtime", "pavoz.types", "pavoz.state", "pavoz.checkpoint", "pavoz.dag")

def check(path: pathlib.Path) -> list[str]:
    bad = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module in FORBIDDEN:
            bad.append(f"{path}:{node.lineno} 禁止 import {node.module}")
    return bad

bad = [m for p in pathlib.Path("pavoz_extensions").rglob("*.py") for m in check(p)]
print("\n".join(bad) or "OK: 只用公开 API")
sys.exit(1 if bad else 0)
```

启动即抓到的实例: 早期 handoff 示例写 `from pavoz.types import StageError` —— 应改 `from pavoz import StageError`。

---

## 7. 测试策略

| 层 | 覆盖 |
|---|---|
| 单测 (`tests/test_gate.py`) | 一次达标直接返回 / 多轮收敛 / 耗尽 raise / 耗尽 best_effort / `aggregate=min` 与 `mean` 差异 / `revise=None` / 末轮不调 revise (用计数器断言) / 入口参数校验 / reviewer 抛异常透传 / 事件 payload |
| 单测 (`tests/test_schema.py`) | input 违规 / output 违规 / warn_only 不阻断 / 自定义校验函数 (非 pydantic) / `__cause__` 保留 |
| 集成 (`tests/test_integration_dag.py`) | 真实 `DAG` + `Runtime` 跑一个 3-stage 图, gate 收敛后下游拿到正确 state; `run_stage` 重放单 stage |
| 结构检查 | `tools/check_public_api.py` 在 CI 跑, 且自身有测试 (构造违规样例必须被抓) |

全部测试**无网络、无 LLM、无 pydantic 硬依赖**。

---

## 8. 打包与发布

- `pyproject.toml` (hatchling, 与核心一致): name `pavoz-extensions`, import `pavoz_extensions`, extras `[pydantic]` 与 `[dev]`
- `.github/workflows/test.yml` (矩阵 + 结构检查) / `publish.yml` (tag `v*` → Trusted Publishing)
- **发布顺序**: 晚于 `pavoz 0.3.0` 上 PyPI

---

## 9. 决策记录 (与扩展直接相关的 grill 决议)

| 决议 | 内容 |
|---|---|
| ④ | 0.1.0 只发 gate + schema; cost_cap/conditional 延后 |
| ⑦ | 扩展点验证 = CI 结构检查 + 发布后他证 |
| ⑨ | 聚合默认 `min` |
| ⑩ | reviewer 默认串行, `concurrency` 可选 |
| ⑪ | 官方包 + 跟随核心; 核心永不反向依赖 |

## 10. 开放问题

1. License: 本仓 Apache-2.0 vs 核心 MIT —— 待维护者定 (PRD §8)
2. ~~`concurrency>1` 时 lens 完成顺序不稳定~~ —— 已解决: 结果按 lens 声明顺序回收, 事件 payload 顺序确定
