"""Electrical Propulsion Plugin package."""

from __future__ import annotations

from . import editors, models
from .plugin import ElectricalPropulsionPlugin

PLUGIN = ElectricalPropulsionPlugin()

__all__ = [
    "PLUGIN",
    "ElectricalPropulsionPlugin",
    "editors",
    "models",
]
