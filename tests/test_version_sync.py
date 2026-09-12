"""发版最容易错的一环: 两处版本号必须一致 (pyproject 与 __init__)."""
from __future__ import annotations

import pathlib
import tomllib

import pavoz_extensions

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_version_matches_pyproject() -> None:
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pavoz_extensions.__version__ == pyproject["project"]["version"], (
        "pavoz_extensions/__init__.py 的 __version__ 与 pyproject.toml 的 version 不一致 — "
        "发版前必须同步 (见 RELEASING.md)"
    )
