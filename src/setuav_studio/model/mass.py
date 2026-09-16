"""Physical mass, center of gravity, and inertia tensor domain models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Vector3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class InertiaTensor:
    """Symmetric inertia tensor expressed about a stated reference point."""

    ixx: float = 0.0
    iyy: float = 0.0
    izz: float = 0.0
    ixy: float = 0.0
    ixz: float = 0.0
    iyz: float = 0.0

    def as_matrix(self) -> tuple[tuple[float, float, float], ...]:
        """Convert to a 3x3 matrix. Products of inertia use conventional negative off-diagonal."""
        return (
            (self.ixx, -self.ixy, -self.ixz),
            (-self.ixy, self.iyy, -self.iyz),
            (-self.ixz, -self.iyz, self.izz),
        )

    @classmethod
    def from_matrix(
        cls,
        matrix: tuple[tuple[float, float, float], ...] | list[list[float]],
    ) -> InertiaTensor:
        return cls(
            ixx=float(matrix[0][0]),
            iyy=float(matrix[1][1]),
            izz=float(matrix[2][2]),
            ixy=-float(matrix[0][1]),
            ixz=-float(matrix[0][2]),
            iyz=-float(matrix[1][2]),
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "ixx": self.ixx,
            "iyy": self.iyy,
            "izz": self.izz,
            "ixy": self.ixy,
            "ixz": self.ixz,
            "iyz": self.iyz,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> InertiaTensor:
        if not isinstance(data, dict):
            return cls()
        return cls(
            ixx=float(data.get("ixx", 0.0) or 0.0),
            iyy=float(data.get("iyy", 0.0) or 0.0),
            izz=float(data.get("izz", 0.0) or 0.0),
            ixy=float(data.get("ixy", 0.0) or 0.0),
            ixz=float(data.get("ixz", 0.0) or 0.0),
            iyz=float(data.get("iyz", 0.0) or 0.0),
        )


@dataclass(frozen=True, slots=True)
class MassProperties:
    """Aggregate mass properties of a body or aircraft."""

    mass_kg: float
    cg_body_m: Vector3
    inertia_cg_kg_m2: InertiaTensor


@dataclass(frozen=True, slots=True)
class ComponentMassProperties:
    """Resolved mass properties of an individual aircraft component."""

    component_id: str
    component_name: str
    mass_kg: float
    cg_local_m: Vector3
    cg_body_m: Vector3
    inertia_local_kg_m2: InertiaTensor
    source: str
    quality: str
    warnings: tuple[str, ...] = ()
    component_type: str = ""
