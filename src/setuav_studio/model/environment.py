"""International Standard Atmosphere (ISA) environmental model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from setuav_studio.model.atmosphere import A0, G0, MU0, P0, RHO0, T0


@dataclass
class Environment:
    """Atmospheric and physical environmental state."""

    altitude_m: float = 0.0
    temperature_k: float = T0
    pressure_pa: float = P0
    density_kg_m3: float = RHO0
    speed_of_sound_mps: float = A0
    dynamic_viscosity: float = MU0
    gravity_mps2: float = G0
    wind_vector_mps: tuple[float, float, float] = (0.0, 0.0, 0.0)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def isa(
        cls,
        altitude_m: float = 0.0,
        temperature_offset_k: float = 0.0,
        wind: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> Environment:
        """Compute standard ISA atmospheric conditions for a given altitude."""
        from setuav_studio.model.atmosphere import Atmosphere

        return Atmosphere.isa(
            altitude_m=altitude_m,
            temperature_offset_k=temperature_offset_k,
        ).to_environment(wind_vector_mps=wind)

    def to_dict(self) -> dict[str, Any]:
        """Serialize environment properties to dictionary."""
        return {
            "altitude_m": self.altitude_m,
            "temperature_k": self.temperature_k,
            "pressure_pa": self.pressure_pa,
            "density_kg_m3": self.density_kg_m3,
            "speed_of_sound_mps": self.speed_of_sound_mps,
            "dynamic_viscosity": self.dynamic_viscosity,
            "gravity_mps2": self.gravity_mps2,
            "wind_vector_mps": list(self.wind_vector_mps),
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Environment:
        """Deserialize environment properties from dictionary."""
        wind = data.get("wind_vector_mps", (0.0, 0.0, 0.0))
        wind_vec = (
            (float(wind[0]), float(wind[1]), float(wind[2]))
            if isinstance(wind, (list, tuple)) and len(wind) == 3
            else (0.0, 0.0, 0.0)
        )
        return cls(
            altitude_m=float(data.get("altitude_m", 0.0)),
            temperature_k=float(data.get("temperature_k", T0)),
            pressure_pa=float(data.get("pressure_pa", P0)),
            density_kg_m3=float(data.get("density_kg_m3", RHO0)),
            speed_of_sound_mps=float(data.get("speed_of_sound_mps", A0)),
            dynamic_viscosity=float(data.get("dynamic_viscosity", MU0)),
            gravity_mps2=float(data.get("gravity_mps2", G0)),
            wind_vector_mps=wind_vec,
            extra=dict(data.get("extra", {})),
        )


__all__ = ["Environment"]
