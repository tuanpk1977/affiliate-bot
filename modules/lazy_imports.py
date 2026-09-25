"""Explicit deferred imports for startup-heavy libraries.

Import failures are never swallowed: the normal error is raised on first use.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any


class LazyModule:
    def __init__(self, module_name: str) -> None:
        self.module_name = module_name
        self._module: ModuleType | None = None

    def _load(self) -> ModuleType:
        if self._module is None:
            self._module = importlib.import_module(self.module_name)
        return self._module

    def __getattr__(self, name: str) -> Any:
        return getattr(self._load(), name)

    def __repr__(self) -> str:
        state = "loaded" if self._module is not None else "deferred"
        return f"LazyModule({self.module_name!r}, {state})"


def lazy_module(module_name: str) -> LazyModule:
    return LazyModule(module_name)
