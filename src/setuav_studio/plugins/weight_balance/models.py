"""Typed weight-and-balance inputs and results."""

from __future__ import annotations

from dataclasses import dataclass, field

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
        # Products of inertia use the conventional negative off-diagonal form.
        return (
            (self.ixx, -self.ixy, -self.ixz),
            (-self.ixy, self.iyy, -self.iyz),
            (-self.ixz, -self.iyz, self.izz),
        )

    @classmethod
    def from_matrix(
        cls,
        matrix: tuple[tuple[float, float, float], ...],
    ) -> "InertiaTensor":
        return cls(
            ixx=matrix[0][0],
            iyy=matrix[1][1],
            izz=matrix[2][2],
            ixy=-matrix[0][1],
            ixz=-matrix[0][2],
            iyz=-matrix[1][2],
        )


@dataclass(frozen=True, slots=True)
class MassProperties:
    mass_kg: float
    cg_body_m: Vector3
    inertia_cg_kg_m2: InertiaTensor


@dataclass(frozen=True, slots=True)
class ComponentMassProperties:
    component_id: str
    component_name: str
    mass_kg: float
    cg_local_m: Vector3
    cg_body_m: Vector3
    inertia_local_kg_m2: InertiaTensor
    source: str
    quality: str
    warnings: tuple[str, ...] = ()


@dataclass(slots=True)
class WeightBalanceResult:
    total: MassProperties
    components: list[ComponentMassProperties] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
