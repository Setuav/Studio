"""Debug Plugin Package for Setuav Studio."""

from __future__ import annotations

from .plugin import DebugPlugin

PLUGIN = DebugPlugin()

__all__ = ["PLUGIN", "DebugPlugin"]
