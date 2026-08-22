"""Aerodynamics Plugin Package for Setuav Studio."""
from __future__ import annotations

from .plugin import AerodynamicsPlugin

PLUGIN = AerodynamicsPlugin()

__all__ = ["AerodynamicsPlugin", "PLUGIN"]
