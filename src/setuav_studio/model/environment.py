"""International Standard Atmosphere (ISA) environmental model."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from setuav_studio.model.data import Data

# Standard physical constants
_T0 = 288.15  # Sea-level standard temperature (K)
_P0 = 101325.0  # Sea-level standard pressure (Pa)
_RHO0 = 1.225  # Sea-level standard air density (kg/m^3)
_G0 = 9.80665  # Gravitational acceleration (m/s^2)
_R_AIR = 287.05287  # Specific gas constant for dry air (J/(kg*K))
_GAMMA = 1.4  # Specific heat ratio of air
_LAPSE_RATE = 0.0065  # Temperature lapse rate in troposphere (K/m)
_MU0 = 1.789e-5  # Dynamic viscosity at sea level (Pa*s)
_S_SUTHERLAND = 110.4  # Sutherland's empirical constant (K)


@dataclass
class Environment:
    """Atmospheric and physical environmental state."""

    altitude_m: float = 0.0
    temperature_k: float = _T0
    pressure_pa: float = _P0
    density_kg_m3: float = _RHO0
    speed_of_sound_mps: float = 340.29
    dynamic_viscosity: float = _MU0
    gravity_mps2: float = _G0
    wind_vector_mps: tuple[float, float, float] = (0.0, 0.0, 0.0)
    extra: Data = field(default_factory=Data)

    @classmethod
    def isa(
        cls,
        altitude_m: float = 0.0,
        temperature_offset_k: float = 0.0,
        wind: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> Environment:
        """Compute standard ISA atmospheric conditions for a given altitude."""
        h = max(altitude_m, -500.0)
        if h <= 11000.0:
            # Troposphere
            temp = _T0 - _LAPSE_RATE * h + temperature_offset_k
            pressure = _P0 * ((temp - temperature_offset_k) / _T0) ** (_G0 / (_R_AIR * _LAPSE_RATE))
        else:
            # Lower Stratosphere (isothermal region up to 20km)
            temp_tropo = _T0 - _LAPSE_RATE * 11000.0
            p_tropo = _P0 * (temp_tropo / _T0) ** (_G0 / (_R_AIR * _LAPSE_RATE))
            temp = temp_tropo + temperature_offset_k
            pressure = p_tropo * math.exp(-_G0 * (h - 11000.0) / (_R_AIR * temp_tropo))

        density = pressure / (_R_AIR * temp)
        speed_of_sound = math.sqrt(_GAMMA * _R_AIR * temp)

        # Sutherland's law for dynamic viscosity
        mu = _MU0 * ((temp / _T0) ** 1.5) * ((_T0 + _S_SUTHERLAND) / (temp + _S_SUTHERLAND))

        return cls(
            altitude_m=float(altitude_m),
            temperature_k=float(temp),
            pressure_pa=float(pressure),
            density_kg_m3=float(density),
            speed_of_sound_mps=float(speed_of_sound),
            dynamic_viscosity=float(mu),
            gravity_mps2=_G0,
            wind_vector_mps=wind,
        )

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
            "extra": self.extra.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Environment:
        """Deserialize environment properties from dictionary."""
        wind = data.get("wind_vector_mps", (0.0, 0.0, 0.0))
        return cls(
            altitude_m=float(data.get("altitude_m", 0.0)),
            temperature_k=float(data.get("temperature_k", _T0)),
            pressure_pa=float(data.get("pressure_pa", _P0)),
            density_kg_m3=float(data.get("density_kg_m3", _RHO0)),
            speed_of_sound_mps=float(data.get("speed_of_sound_mps", 340.29)),
            dynamic_viscosity=float(data.get("dynamic_viscosity", _MU0)),
            gravity_mps2=float(data.get("gravity_mps2", _G0)),
            wind_vector_mps=tuple(wind) if isinstance(wind, (list, tuple)) else (0.0, 0.0, 0.0),  # type: ignore
            extra=Data.from_dict(data.get("extra", {})),
        )


__all__ = ["Environment"]
