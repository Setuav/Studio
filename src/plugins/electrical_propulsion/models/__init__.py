"""Electrical propulsion component domain models."""

from __future__ import annotations

from .battery import BatteryModel
from .propulsor import PropulsorModel

__all__ = [
    "BatteryModel",
    "PropulsorModel",
]
