"""pavoz-extensions — official extension pack for pavoz.

Two plain decorators over stage functions; pavoz core needs no changes and never
depends on this package:

    @gate      worker → multi-lens review → score → revise loop (quality gate)
    @schema    cross-stage contract validation (input state / output delta)

Importing this package verifies the installed pavoz is within the supported
range (see ``_CORE_RANGE``); everything here uses pavoz's public API only.
"""

from __future__ import annotations

import re

from .gate import GateFailedError, gate
from .schema import SchemaContractError, schema

__version__ = "0.1.0"

#: Supported pavoz core range — keep in sync with pyproject ``dependencies``.
_CORE_RANGE = ">=0.3,<0.4"
_CORE_MIN = (0, 3)
_CORE_MAX = (0, 4)  # exclusive


def _parse(version: str) -> tuple[int, ...]:
    """'0.3.0rc1' → (0, 3, 0). Unparseable → () (checked fail-open)."""
    head = re.split(r"[^0-9.]", version, maxsplit=1)[0]
    parts = [int(p) for p in head.split(".") if p.isdigit()]
    return tuple(parts)


def _check_core_version() -> None:
    import pavoz

    parsed = _parse(getattr(pavoz, "__version__", ""))
    if not parsed:
        return  # 版本串无法解析: 不阻断 (fail-open), 交给运行时报错
    major_minor = parsed[:2]
    if not (_CORE_MIN <= major_minor < _CORE_MAX):
        raise RuntimeError(
            f"pavoz-extensions {__version__} 需要 pavoz{_CORE_RANGE}, "
            f"当前安装的是 pavoz {pavoz.__version__}. "
            f"请 `pip install \"pavoz{_CORE_RANGE}\"` 或升级本包."
        )


_check_core_version()

__all__ = ["GateFailedError", "SchemaContractError", "__version__", "gate", "schema"]
