"""Unit definitions and conversion factors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from setuav_studio.units.dimension import DIMENSIONLESS, Dimension


@dataclass(frozen=True)
class UnitDefinition:
    """Definition of a single physical measurement unit."""

    id: str
    symbol: str
    name: str
    to_base: float | Callable[[float], float]
    from_base: float | Callable[[float], float]
    decimals: int = 2
    dimension: Dimension = DIMENSIONLESS

    def to_base_value(self, value: float) -> float:
        """Convert value from this unit to base storage unit."""
        if callable(self.to_base):
            return float(self.to_base(value))
        return float(value * self.to_base)

    def from_base_value(self, base_value: float) -> float:
        """Convert value from base storage unit to this unit."""
        if callable(self.from_base):
            return float(self.from_base(base_value))
        return float(base_value * self.from_base)


__all__ = ["UnitDefinition"]
