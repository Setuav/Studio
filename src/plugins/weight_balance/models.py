"""Typed weight-and-balance inputs and results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from setuav_studio.model import (
    Component,
    ComponentMassProperties,
    InertiaTensor,
    MassProperties,
    Vector3,
)

__all__ = [
    "ComponentMassProperties",
    "InertiaTensor",
    "MassProperties",
    "PointMassModel",
    "Vector3",
    "WeightBalanceResult",
]


@dataclass(slots=True)
class WeightBalanceResult:
    total: MassProperties
    components: list[ComponentMassProperties] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PointMassModel(Component):
    """Domain entity model for Point Mass with live CG coordinates."""

    @property
    def cg_x(self) -> float:
        return self.x

    @property
    def cg_y(self) -> float:
        return self.y

    @property
    def cg_z(self) -> float:
        return self.z

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update(
            {
                "cg_x": self.cg_x,
                "cg_y": self.cg_y,
                "cg_z": self.cg_z,
            }
        )
        return props
