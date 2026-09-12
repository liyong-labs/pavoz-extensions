# 发版流程

**读者**: 有 PyPI / GitHub 权限的维护者
**目标**: 一次发版 = 推一条 tag, 构建与上传由 CI 完成 (与 [pavoz 核心仓](https://github.com/liyong-labs/pavoz/blob/main/RELEASING.md) 同一套模式)

## 一次性前置

| # | 在哪 | 做什么 |
|---|---|---|
| 1 | PyPI → Publishing → Add a pending publisher | 项目名 `pavoz-extensions` / owner `liyong-labs` / 仓库 `pavoz-extensions` / workflow `publish.yml` / environment `pypi` |
| 2 | GitHub 仓库 → Settings → Environments | 新建名为 `pypi` 的 environment |

## 每次发版 (5 步)

1. **同步两处版本号** — `pyproject.toml` 的 `version` 与 `pavoz_extensions/__init__.py` 的 `__version__`
   (`tests/test_version_sync.py` 会拦下不一致)
2. **写 CHANGELOG** — `[Unreleased]` → `[x.y.z] — YYYY-MM-DD`
3. **提交** — `git commit -m "release: vX.Y.Z"`
4. **打 tag 并推送** — `git tag vX.Y.Z && git push origin main && git push origin vX.Y.Z`
5. **验证** — CI 绿; `pip install pavoz-extensions==X.Y.Z` 成功; 导入后 `__version__` 与 tag 一致

## 依赖顺序 (重要)

**pavoz 核心必须先上 PyPI** — 本包声明 `pavoz>=0.3,<0.4`, PyPI 上没有核心包时安装会解析失败。
核心发布流程见 [pavoz RELEASING.md](https://github.com/liyong-labs/pavoz/blob/main/RELEASING.md)。

## 发布后要跟着改的

- README (中英) 安装段: `pip install --no-deps git+...` → `pip install pavoz-extensions`
- `.github/workflows/test.yml` 的安装步骤: 去掉 "PyPI 装不到就回退 git" 的兜底,
  换成真正的版本矩阵 (最低支持 × 最新)
- 版本号怎么定 / yank 规则见核心仓 RELEASING.md (同一套 semver 约定)
