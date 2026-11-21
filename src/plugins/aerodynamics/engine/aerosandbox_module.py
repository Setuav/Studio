"""AeroSandbox, imported on first use.

Importing AeroSandbox also imports scipy, matplotlib and pandas, which takes
seconds; the plugin only needs it once an analysis runs.
"""

from __future__ import annotations

import importlib
from typing import Any


class _ImportedOnFirstUse:
    """Stands in for a module and imports it on the first attribute access."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, attribute: str) -> Any:
        return getattr(importlib.import_module(self._name), attribute)


asb: Any = _ImportedOnFirstUse("aerosandbox")
np: Any = _ImportedOnFirstUse("aerosandbox.numpy")
