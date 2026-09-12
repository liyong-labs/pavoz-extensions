"""CI guard: this pack may only use pavoz's public API.

Importing ``pavoz.<submodule>`` directly couples us to internals that are free to
move (only what ``pavoz/__init__.py`` exports is public). Failing here keeps the
"extensions are writable against the public surface" claim honest.

Usage:  python tools/check_public_api.py     (exit 0 = clean)
"""

from __future__ import annotations

import ast
import pathlib
import sys

PACKAGE = "pavoz_extensions"
FORBIDDEN = ("pavoz.runtime", "pavoz.types", "pavoz.state", "pavoz.checkpoint",
             "pavoz.dag", "pavoz.storage", "pavoz.storage_loader", "pavoz.testing",
             "pavoz.cli", "pavoz._id")


def check(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in FORBIDDEN:
            problems.append(f"{path}:{node.lineno} 禁止从 {node.module} 导入 (仅限 pavoz 顶层公开 API)")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN:
                    problems.append(f"{path}:{node.lineno} 禁止 import {alias.name}")
    return problems


def main() -> int:
    problems = [
        message
        for path in sorted(pathlib.Path(PACKAGE).rglob("*.py"))
        for message in check(path)
    ]
    if problems:
        print("\n".join(problems))
        return 1
    print(f"OK: {PACKAGE} 只用 pavoz 顶层公开 API")
    return 0


if __name__ == "__main__":
    sys.exit(main())
