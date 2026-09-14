---
owner: liyong
last-verified: 2026-09-13
applies-to: pavoz-extensions 0.1.0+ (pavoz >=0.3,<0.4)
---

# PRD — pavoz-extensions

**状态**: completed (2026-09-13) — 0.1.0 首版已实施, 见 [README](../README.md) 用法与 [CHANGELOG](../CHANGELOG.md)
**读者**: pavoz 维护者 (定范围/验收) + 集成方 (判断该不该用) + 扩展作者 (抄边界)
**实施计划**: pavoz 仓 `docs/design/extension-plan-2026-09-13.md`

**关键词**: 约束级 **必须** / **不得** (违反即功能不成立), 建议级 **应当** (不遵守有副作用), 可选 **可** — 对应 RFC 2119 的 MUST / MUST NOT / SHOULD / MAY。

---

## 1. 背景

pavoz 核心有一条明确的设计立场 (`docs/{cn,en}/architecture.md` 决策 1): **"循环留在业务层"** —— 框架只提供 DAG + per-node retries + checkpoint, 质量收敛循环由 stage 函数内的普通 Python 表达。

这条立场是对的 (Uber Piper 的功能蔓延反面教材), 但留下一个空白: **每个消费方都要自己重写同一个循环**。

| 反复出现的需求 | 现状 |
|---|---|
| stage 产出不达标 → 审 → 改 → 再审, 达标才放行 | 各项目自己写 while + 评分 + 重试, 形态各异, 无事件可观测 |
| 上游 stage 换了数据结构 → 下游神秘失败 | 无契约校验, 错误在 N 步之后才爆 |
| 想按行业惯例给 pavoz 写扩展 | 没有可抄的样例, 只能猜公开 API 的边界 |

2026-09-12 需求方提出把这四项能力 (gate / conditional / schema / cost_cap) 做进 pavoz。2026-09-13 评审定案: **核心零改动** —— 这些能力全部可以做成纯装饰器, 独立成包。

## 2. 定位

**官方扩展包, 跟随核心维护**; 同时是**第三方扩展作者的模板**。

- ✅ 直接可 `pip install` 复用的工具
- ✅ "扩展点够用" 的活证明: 它只用 `pavoz` 顶层公开 API, CI 结构检查强制
- ✅ 核心永不反向依赖扩展 (pavoz 的 `dependencies = []` 不受影响)
- ❌ 不是 pavoz 的一部分, 不随核心发版, 不被核心 import
- ❌ 不承诺"官方扩展"的审批权: 第三方可自由发布自己的 `pavoz-*`, 无需我们同意

## 3. 用户与场景

| 用户 | 场景 | 依赖 |
|---|---|---|
| 应用开发者 (LLM / 数据 pipeline) | stage 质量不达标要重做, 但不想把循环逻辑写散在各处 | `@gate` |
| 应用开发者 (多 stage 数据流) | 想在上游产出时就发现结构错位, 而不是等到末尾 | `@schema` |
| 第三方扩展作者 | 想写 `pavoz-notify` / `pavoz-budget`, 需要一个能抄的真实样例 | 两个模块 |

## 4. 范围

**做**:
- `@gate` — worker → N reviewer → 评分 → 反馈重做 → 收敛; 耗尽可配置
- `@schema` — stage 输入/输出契约校验, 违反即终态失败

**不做 (0.1.0)**:
| 项 | 理由 |
|---|---|
| `@cost_cap` | 记账位置有争议 (只有 caller 知道 token 数); 契约未定不上 PyPI |
| `@conditional` | stage 内一行 `if` 即可; `return {}` 无法与"跑了没产出"区分, 会削弱静态契约 |
| hook 注册表 / `ctx._meta` | 核心已有 `on_event`; 这两项评审已拒, 不在扩展里复活 |
| 中心化插件注册 (entry_points) | pavoz 既有 YAGNI |

## 5. 需求清单

| # | 需求 | 验收标准 |
|---|---|---|
| R1 | `gate(reviewers, revise, threshold, max_iter, aggregate, on_exhaustion)` 装饰器 | 多 lens 评分; `aggregate="min"` 默认 (最严一票否决); 达标返回最佳产物; 耗尽默认抛 `StageError` (终态); `max_iter=1` / 单 lens 可用; `reviewers` 空或 `max_iter<1` 入口报错 |
| R2 | reviewer/revise 是**普通可调用对象**, 不绑定 LLM | 单测用纯函数 reviewer 跑通, 全程无网络 |
| R3 | 分数历史可观测 | 每轮 emit `gate_score` 事件 (stage / iter / 各 lens 分数 / 聚合分) 到 `ctx.on_event` |
| R4 | 成本可预测 | README 写明上界 `1 + max_iter × (\|reviewers\| + 1)` 次 `ctx.call`; 与 `@dag.stage(retries=N)` 的乘法关系写明并给出 `retries=0` 建议; 末轮不调用 `revise` |
| R5 | `schema(input=…, output=…, warn_only=False)` 装饰器 | 接受任意 `Callable[[Any], None]` 校验函数 (pydantic 仅作 extras/文档示例); 违反抛 `StageError` 子类 (终态); `warn_only=True` 只记日志不阻断 |
| R6 | 异常契约与核心一致 | 只用 `pavoz.StageError` / `RetryableError` / `FatalError` 的子类, 不引入新异常根 |
| R7 | 只依赖 pavoz 公开 API | CI 结构检查: 源码只允许 `from pavoz import ...` 顶层导入, 出现 `pavoz.runtime` / `pavoz.types` 等子模块即失败 |
| R8 | 版本兼容可验证 | `pyproject.toml` 声明 `pavoz>=0.5,<0.6`; CI 矩阵跑 (最低支持版本 × 最新版本); import 时 stdlib 校验 `pavoz.__version__`, 不符给出明确报错 |
| R9 | 可直接抄的文档 | README 含: 两个扩展的最小用法、成本上界、并发注意事项、"如何写你自己的 `pavoz-*`"; 公开文档中英同步 |

## 6. 成功指标

1. **他证**: 发布后由第三方 (非本包作者) 只读公开文档写出一个**不在 R1–R5 范围内**的新扩展 (如 webhook 通知), 全程不改本包源码; 卡点回补文档
2. **结构检查零例外**: CI 结构检查长期绿 (它是"扩展点够用"的机器保证)
3. **核心零改动**: 消费方接入扩展不需要动 `pavoz/` (`git diff pavoz/` 为空)

## 7. 约束与依赖

- 运行时依赖: `pavoz>=0.5,<0.6` (PyPI); 可选 `pydantic` (example extras)
- Python ≥ 3.12 (与核心一致)
- 不引入 LLM SDK / HTTP 客户端 / 任何 vendor 绑定
- 发布: PyPI Trusted Publishing (与核心同模式); 发布晚于 `pavoz 0.3.0` 上 PyPI

## 8. 开放问题

| # | 问题 | 现状 |
|---|---|---|
| 1 | **License 不一致**: 本仓为 Apache-2.0 (GitHub 模板默认), pavoz 核心是 MIT | 待维护者决定: 统一 MIT 或保留 Apache-2.0 (生态惯例: 扩展包可用不同 license, 但同项目通常统一) |
| 2 | README 标题拼写 `pavoz-extension` (少 s) | 实施时修正 |
| 3 | 是否需要 `pavoz-extensions` 的 PyPI 项目名保护 (squatting) | 发布时自然解决 |
