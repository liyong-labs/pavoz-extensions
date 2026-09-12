"""The public-API guard must actually catch violations (and pass on this package)."""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_public_api", _ROOT / "tools" / "check_public_api.py")
check_public_api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_public_api)


def _write(tmp_path, source: str) -> pathlib.Path:
    path = tmp_path / "sample.py"
    path.write_text(source, encoding="utf-8")
    return path


def test_flags_from_submodule_import(tmp_path):
    problems = check_public_api.check(_write(tmp_path, "from pavoz.types import StageError\n"))
    assert problems and "pavoz.types" in problems[0]


def test_flags_plain_submodule_import(tmp_path):
    problems = check_public_api.check(_write(tmp_path, "import pavoz.runtime\n"))
    assert problems and "pavoz.runtime" in problems[0]


def test_allows_top_level_import(tmp_path):
    assert check_public_api.check(_write(tmp_path, "from pavoz import DAG, StageError\n")) == []


@pytest.mark.parametrize("path", sorted((_ROOT / "pavoz_extensions").rglob("*.py")))
def test_package_itself_only_uses_public_api(path):
    assert check_public_api.check(path) == []
