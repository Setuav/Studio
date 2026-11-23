"""AeroSandbox, imported on first use.

Importing AeroSandbox also imports scipy, matplotlib and pandas, which takes
seconds; the plugin only needs it once an analysis runs. The imports are plain
statements so that the desktop bundler finds and packages AeroSandbox.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any


class _ImportedOnFirstUse:
    """Stands in for a module and imports it on the first attribute access."""

    def __init__(self, load: Callable[[], ModuleType]) -> None:
        self._load = load

    def __getattr__(self, attribute: str) -> Any:
        return getattr(self._load(), attribute)


def _aerosandbox() -> ModuleType:
    import aerosandbox

    return aerosandbox


def _aerosandbox_numpy() -> ModuleType:
    import aerosandbox.numpy

    return aerosandbox.numpy


asb: Any = _ImportedOnFirstUse(_aerosandbox)
np: Any = _ImportedOnFirstUse(_aerosandbox_numpy)
