"""International Standard Atmosphere (ISA) and Airspeed Conversion Engine.

Independent pure-Python implementation of the U.S. Standard Atmosphere 1976 /
ICAO Standard Atmosphere / ESDU 77022 without external solver dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from setuav_studio.model.environment import Environment

# Standard Sea-Level Constants (ISA / US 1976)
T0: float = 288.15  # Sea-level standard temperature (K)
P0: float = 101325.0  # Sea-level standard pressure (Pa)
RHO0: float = 1.225  # Sea-level standard air density (kg/m^3)
G0: float = 9.80665  # Standard gravitational acceleration (m/s^2)
R_AIR: float = 287.05287  # Specific gas constant for dry air (J/(kg*K))
GAMMA: float = 1.4  # Ratio of specific heats (adiabatic index)
A0: float = 340.294  # Sea-level speed of sound (m/s)

# Troposphere & Stratosphere Layer Boundaries (Geopotential Altitude)
H_TROPO: float = 11000.0  # Troposphere upper boundary (m)
H_STRATO1: float = 20000.0  # Lower stratosphere upper boundary (m)
H_STRATO2: float = 32000.0  # Middle stratosphere upper boundary (m)

# Temperature Lapse Rates (K/m)
LAPSE_TROPO: float = -0.0065  # Troposphere lapse rate (-6.5 K/km)
LAPSE_STRATO1: float = 0.0  # Lower stratosphere (isothermal)
LAPSE_STRATO2: float = 0.0010  # Middle stratosphere (+1.0 K/km)

# Viscosity Constants (Sutherland's Law)
MU0: float = 1.789e-5  # Dynamic viscosity at sea level (Pa*s)
S_SUTHERLAND: float = 110.4  # Sutherland's temperature constant (K)


@dataclass(frozen=True)
class Atmosphere:
    """Independent ISA atmosphere model with flight condition calculations.

    Provides exact analytical solutions for atmospheric properties from sea level
    (or below) up to 32 km, including arbitrary ISA temperature deviations (delta ISA).
    Includes methods for dynamic pressure, Reynolds number, Mach number, and
    compressible/incompressible airspeed conversions (TAS, EAS, CAS).
    """

    altitude_m: float = 0.0
    temperature_offset_k: float = 0.0
    temperature_k: float = T0
    pressure_pa: float = P0
    density_kg_m3: float = RHO0
    speed_of_sound_mps: float = A0
    dynamic_viscosity_pa_s: float = MU0
    kinematic_viscosity_m2_s: float = MU0 / RHO0
    gravity_mps2: float = G0

    @classmethod
    def isa(
        cls,
        altitude_m: float = 0.0,
        temperature_offset_k: float = 0.0,
    ) -> Atmosphere:
        """Compute ISA atmospheric state at a given altitude and temperature offset."""
        alt = float(altitude_m)
        dt = float(temperature_offset_k)

        # Standard conditions at boundary 11 km
        t11_std = T0 + LAPSE_TROPO * H_TROPO  # 216.65 K
        p11_std = P0 * (t11_std / T0) ** (-G0 / (R_AIR * LAPSE_TROPO))  # ~22632 Pa

        # Standard conditions at boundary 20 km
        t20_std = t11_std  # 216.65 K
        p20_std = p11_std * math.exp(-G0 * (H_STRATO1 - H_TROPO) / (R_AIR * t11_std))  # ~5474.9 Pa

        if alt <= H_TROPO:
            # Troposphere (and smooth extrapolation below sea level)
            t_std = T0 + LAPSE_TROPO * alt
            t_actual = t_std + dt
            pressure = P0 * (t_std / T0) ** (-G0 / (R_AIR * LAPSE_TROPO))
        elif alt <= H_STRATO1:
            # Lower Stratosphere (isothermal)
            t_std = t11_std
            t_actual = t_std + dt
            pressure = p11_std * math.exp(-G0 * (alt - H_TROPO) / (R_AIR * t11_std))
        elif alt <= H_STRATO2:
            # Middle Stratosphere (temperature inversion)
            t_std = t20_std + LAPSE_STRATO2 * (alt - H_STRATO1)
            t_actual = t_std + dt
            pressure = p20_std * (t_std / t20_std) ** (-G0 / (R_AIR * LAPSE_STRATO2))
        else:
            # High Stratosphere extrapolation
            t_std = t20_std + LAPSE_STRATO2 * (H_STRATO2 - H_STRATO1)
            t_actual = t_std + dt
            p32_std = p20_std * (t_std / t20_std) ** (-G0 / (R_AIR * LAPSE_STRATO2))
            pressure = p32_std * math.exp(-G0 * (alt - H_STRATO2) / (R_AIR * t_std))

        # Gas law
        density = pressure / (R_AIR * max(t_actual, 1.0))
        speed_of_sound = math.sqrt(GAMMA * R_AIR * max(t_actual, 1.0))

        # Sutherland's law for dynamic viscosity
        mu = (
            MU0
            * ((max(t_actual, 1.0) / T0) ** 1.5)
            * ((T0 + S_SUTHERLAND) / (max(t_actual, 1.0) + S_SUTHERLAND))
        )
        nu = mu / max(density, 1e-6)

        return cls(
            altitude_m=alt,
            temperature_offset_k=dt,
            temperature_k=t_actual,
            pressure_pa=pressure,
            density_kg_m3=density,
            speed_of_sound_mps=speed_of_sound,
            dynamic_viscosity_pa_s=mu,
            kinematic_viscosity_m2_s=nu,
            gravity_mps2=G0,
        )

    # -------------------------------------------------------------------------
    # Dimensionless Ratios
    # -------------------------------------------------------------------------

    @property
    def temperature_c(self) -> float:
        """Atmospheric temperature in Celsius."""
        return self.temperature_k - 273.15

    @property
    def density_ratio_sigma(self) -> float:
        """Density ratio relative to sea-level standard: sigma = rho / rho0."""
        return self.density_kg_m3 / RHO0

    @property
    def pressure_ratio_delta(self) -> float:
        """Pressure ratio relative to sea-level standard: delta = P / P0."""
        return self.pressure_pa / P0

    @property
    def temperature_ratio_theta(self) -> float:
        """Temperature ratio relative to sea-level standard: theta = T / T0."""
        return self.temperature_k / T0

    # -------------------------------------------------------------------------
    # Flight Performance Helpers
    # -------------------------------------------------------------------------

    def dynamic_pressure(self, speed_mps: float) -> float:
        """Compute dynamic pressure q = 0.5 * rho * V^2 (Pa)."""
        return 0.5 * self.density_kg_m3 * (speed_mps**2)

    def mach_number(self, speed_mps: float) -> float:
        """Compute flight Mach number M = V / a."""
        return speed_mps / max(self.speed_of_sound_mps, 1.0)

    def reynolds_number(self, speed_mps: float, length_m: float) -> float:
        """Compute characteristic Reynolds number Re = rho * V * L / mu."""
        return (self.density_kg_m3 * abs(speed_mps) * max(length_m, 0.0)) / max(
            self.dynamic_viscosity_pa_s, 1e-9
        )

    # -------------------------------------------------------------------------
    # Airspeed Conversions (TAS, EAS, CAS)
    # -------------------------------------------------------------------------

    def tas_to_eas(self, tas_mps: float) -> float:
        """Convert True Airspeed (TAS) to Equivalent Airspeed (EAS): EAS = TAS * sqrt(sigma)."""
        return tas_mps * math.sqrt(max(self.density_ratio_sigma, 1e-9))

    def eas_to_tas(self, eas_mps: float) -> float:
        """Convert Equivalent Airspeed (EAS) to True Airspeed (TAS): TAS = EAS / sqrt(sigma)."""
        return eas_mps / math.sqrt(max(self.density_ratio_sigma, 1e-9))

    def tas_to_cas(self, tas_mps: float) -> float:
        """Convert True Airspeed (TAS) to Calibrated Airspeed (CAS) via compressible isentropic flow.

        Follows standard subsonic compressible pitot formulation (Raymer Ch. 5 / ESDU).
        """
        if tas_mps <= 0.0:
            return 0.0

        mach = self.mach_number(tas_mps)
        # Impact dynamic pressure (compressible pitot-static equation for subsonic flow)
        gamma_fac = (GAMMA - 1.0) / 2.0
        qc = self.pressure_pa * ((1.0 + gamma_fac * (mach**2)) ** (GAMMA / (GAMMA - 1.0)) - 1.0)

        # Standard sea-level CAS equation
        cas_squared = (2.0 * (A0**2) / (GAMMA - 1.0)) * (
            (1.0 + qc / P0) ** ((GAMMA - 1.0) / GAMMA) - 1.0
        )
        return math.sqrt(max(cas_squared, 0.0))

    def cas_to_tas(self, cas_mps: float) -> float:
        """Convert Calibrated Airspeed (CAS) to True Airspeed (TAS) via compressible isentropic flow."""
        if cas_mps <= 0.0:
            return 0.0

        gamma_fac = (GAMMA - 1.0) / 2.0
        qc = P0 * ((1.0 + gamma_fac * ((cas_mps / A0) ** 2)) ** (GAMMA / (GAMMA - 1.0)) - 1.0)

        mach_squared = (2.0 / (GAMMA - 1.0)) * (
            (1.0 + qc / self.pressure_pa) ** ((GAMMA - 1.0) / GAMMA) - 1.0
        )
        mach = math.sqrt(max(mach_squared, 0.0))
        return mach * self.speed_of_sound_mps

    # -------------------------------------------------------------------------
    # Interoperability
    # -------------------------------------------------------------------------

    def to_environment(self, wind_vector_mps: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> Environment:
        """Convert atmosphere state to core Environment dataclass instance."""
        from setuav_studio.model.environment import Environment

        return Environment(
            altitude_m=self.altitude_m,
            temperature_k=self.temperature_k,
            pressure_pa=self.pressure_pa,
            density_kg_m3=self.density_kg_m3,
            speed_of_sound_mps=self.speed_of_sound_mps,
            dynamic_viscosity=self.dynamic_viscosity_pa_s,
            gravity_mps2=self.gravity_mps2,
            wind_vector_mps=wind_vector_mps,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize atmosphere state to dictionary."""
        return {
            "altitude_m": self.altitude_m,
            "temperature_offset_k": self.temperature_offset_k,
            "temperature_k": self.temperature_k,
            "pressure_pa": self.pressure_pa,
            "density_kg_m3": self.density_kg_m3,
            "speed_of_sound_mps": self.speed_of_sound_mps,
            "dynamic_viscosity_pa_s": self.dynamic_viscosity_pa_s,
            "kinematic_viscosity_m2_s": self.kinematic_viscosity_m2_s,
            "gravity_mps2": self.gravity_mps2,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Atmosphere:
        """Deserialize atmosphere state from dictionary or create from altitude."""
        if "density_kg_m3" in data and "temperature_k" in data and "pressure_pa" in data:
            return cls(
                altitude_m=float(data.get("altitude_m", 0.0)),
                temperature_offset_k=float(data.get("temperature_offset_k", 0.0)),
                temperature_k=float(data["temperature_k"]),
                pressure_pa=float(data["pressure_pa"]),
                density_kg_m3=float(data["density_kg_m3"]),
                speed_of_sound_mps=float(data.get("speed_of_sound_mps", A0)),
                dynamic_viscosity_pa_s=float(data.get("dynamic_viscosity_pa_s", MU0)),
                kinematic_viscosity_m2_s=float(
                    data.get("kinematic_viscosity_m2_s", MU0 / RHO0)
                ),
                gravity_mps2=float(data.get("gravity_mps2", G0)),
            )
        return cls.isa(
            altitude_m=float(data.get("altitude_m", 0.0)),
            temperature_offset_k=float(data.get("temperature_offset_k", 0.0)),
        )


__all__ = [
    "A0",
    "G0",
    "GAMMA",
    "MU0",
    "P0",
    "RHO0",
    "R_AIR",
    "S_SUTHERLAND",
    "T0",
    "Atmosphere",
]
