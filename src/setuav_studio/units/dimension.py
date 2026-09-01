"""Physical Dimensions (SI / Buckingham-Pi) and dimensional algebra."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Dimension:
    """Fundamental physical dimensions power vector."""

    length: int = 0
    mass: int = 0
    time: int = 0
    current: int = 0
    temperature: int = 0
    angle: int = 0

    def is_dimensionless(self) -> bool:
        return (
            self.length == 0
            and self.mass == 0
            and self.time == 0
            and self.current == 0
            and self.temperature == 0
            and self.angle == 0
        )

    def __mul__(self, other: Dimension) -> Dimension:
        if not isinstance(other, Dimension):
            return NotImplemented
        return Dimension(
            length=self.length + other.length,
            mass=self.mass + other.mass,
            time=self.time + other.time,
            current=self.current + other.current,
            temperature=self.temperature + other.temperature,
            angle=self.angle + other.angle,
        )

    def __truediv__(self, other: Dimension) -> Dimension:
        if not isinstance(other, Dimension):
            return NotImplemented
        return Dimension(
            length=self.length - other.length,
            mass=self.mass - other.mass,
            time=self.time - other.time,
            current=self.current - other.current,
            temperature=self.temperature - other.temperature,
            angle=self.angle - other.angle,
        )

    def __pow__(self, power: int) -> Dimension:
        if not isinstance(power, int):
            raise TypeError("Dimension powers must be integers")
        return Dimension(
            length=self.length * power,
            mass=self.mass * power,
            time=self.time * power,
            current=self.current * power,
            temperature=self.temperature * power,
            angle=self.angle * power,
        )

    def __repr__(self) -> str:
        if self.is_dimensionless():
            return "Dimension(1)"
        parts = []
        names = [
            ("L", self.length),
            ("M", self.mass),
            ("T", self.time),
            ("I", self.current),
            ("Θ", self.temperature),
            ("A", self.angle),
        ]
        for sym, p in names:
            if p == 1:
                parts.append(sym)
            elif p != 0:
                parts.append(f"{sym}^{p}")
        return f"Dimension({' · '.join(parts)})"


# Base fundamental dimensions
DIMENSIONLESS = Dimension()
LENGTH = Dimension(length=1)
MASS = Dimension(mass=1)
TIME = Dimension(time=1)
CURRENT = Dimension(current=1)
TEMPERATURE = Dimension(temperature=1)
ANGLE = Dimension(angle=1)

# Derived dimensions in aerospace engineering
AREA = LENGTH**2
VOLUME = LENGTH**3
VELOCITY = LENGTH / TIME
ACCELERATION = LENGTH / (TIME**2)
FORCE = MASS * ACCELERATION  # Thrust, Lift, Drag
MOMENT = FORCE * LENGTH  # Torque / Moment
PRESSURE = FORCE / AREA  # Pressure / Dynamic Pressure
DENSITY = MASS / VOLUME  # Air density
WING_LOADING = MASS / AREA  # Wing area loading
ENERGY = FORCE * LENGTH  # Energy (Joules / Watt-hours)
POWER = ENERGY / TIME  # Mechanical / Electrical Power
VOLTAGE = POWER / CURRENT  # Electric Potential
FREQUENCY = DIMENSIONLESS / TIME  # Rotational speed (RPM, Hz)


__all__ = [
    "ACCELERATION",
    "ANGLE",
    "AREA",
    "CURRENT",
    "DENSITY",
    "DIMENSIONLESS",
    "ENERGY",
    "FORCE",
    "FREQUENCY",
    "LENGTH",
    "MASS",
    "MOMENT",
    "POWER",
    "PRESSURE",
    "TEMPERATURE",
    "TIME",
    "VELOCITY",
    "VOLTAGE",
    "VOLUME",
    "WING_LOADING",
    "Dimension",
]
