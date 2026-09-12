# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0] — 2026-09-13

首个版本:两个纯装饰器扩展, pavoz 核心零改动。

### Added

- **`@gate`** — worker 产出 → 多 lens 评审打分 → 批评回喂 `revise` → 收敛的质量门
  - 聚合默认 `min` (最严 lens 一票否决), 可切 `mean`
  - 耗尽默认抛 `GateFailedError` (终态不重试), 可切 `best_effort` 返回最高分产物
  - 每轮把 `gate_score` 写进 `ctx.on_event`; observer 异常隔离, 不影响 stage
  - `concurrency=N` 并发评审; 末轮不调 `revise`; worker 全程只跑一次
- **`@schema`** — `input` 校验 `ctx.state`, `output` 校验返回的 delta
  - 校验器是任意 `validate(obj) -> None` 可调用对象 (pydantic 为可选 extra, 非必需)
  - 违反抛 `SchemaContractError` (终态, 原异常保留在 `__cause__`); `warn_only=True` 只记日志
- 两个异常都继承核心 `StageError`, 不引入新异常根
- 导入时用标准库校验 `pavoz` 版本区间 (`>=0.3,<0.4`), 越界给出明确报错

### Notes

- 安装方式见 [README](README.md) (0.1.0 发布时 PyPI 尚未上线 `pavoz`)
- 设计与契约: [`docs/design.md`](docs/design.md); 范围与验收: [`docs/PRD.md`](docs/PRD.md)
