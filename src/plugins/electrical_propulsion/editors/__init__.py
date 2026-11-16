"""Property editors for electrical propulsion components."""

from __future__ import annotations

from .battery import BatteryEditor
from .propulsor import PropulsorEditor

__all__ = [
    "BatteryEditor",
    "PropulsorEditor",
]
