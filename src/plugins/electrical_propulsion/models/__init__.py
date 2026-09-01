"""Electrical Propulsion domain entity models."""

from .battery import BatteryModel
from .esc import ESCModel
from .motor import MotorModel
from .propeller import PropellerModel

__all__ = [
    "BatteryModel",
    "ESCModel",
    "MotorModel",
    "PropellerModel",
]
