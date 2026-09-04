"""Aerodynamic polar and induced drag modeling for preliminary sizing.

References:
- Raymer, D.P., "Aircraft Design: A Conceptual Approach", 7th Ed., Ch. 12.
- Brandt, S.A. et al., "Introduction to Aeronautics: A Design Perspective".
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def calculate_oswald_raymer(aspect_ratio: float, sweep_deg: float = 0.0) -> float:
    """Estimate Oswald span efficiency factor (e) using Raymer's empirical relation.

    For straight or low-sweep wings:
    e = 1.78 * (1.0 - 0.045 * AR^0.68) - 0.64

    For swept wings (>0 deg):
    accounts for cos(sweep) correction.
    """
    ar = max(float(aspect_ratio), 1.0)
    sweep_rad = math.radians(max(0.0, float(sweep_deg)))

    if sweep_deg <= 0.0:
        e = 1.78 * (1.0 - 0.045 * (ar**0.68)) - 0.64
    else:
        e = 4.61 * (1.0 - 0.045 * (ar**0.68)) * (math.cos(sweep_rad) ** 0.15) - 3.1

    # Clamp between physically sensible boundaries for subsonic UAVs
    return max(0.55, min(e, 0.95))


def calculate_induced_drag_factor(aspect_ratio: float, oswald_e: float) -> float:
    """Compute lift-induced drag factor k = 1 / (pi * AR * e)."""
    ar = max(float(aspect_ratio), 1.0)
    e = max(float(oswald_e), 0.1)
    return 1.0 / (math.pi * ar * e)


@dataclass(frozen=True)
class AeroParameters:
    """Aerodynamic properties and polar parameters for sizing."""

    cd0: float = 0.025  # Zero-lift parasite drag coefficient
    aspect_ratio: float = 10.0  # Wing aspect ratio (b^2 / S)
    oswald_e: float = 0.82  # Oswald efficiency factor
    cl_max_clean: float = 1.35  # Clean configuration maximum lift coefficient
    cl_max_takeoff: float = 1.55  # Takeoff configuration maximum lift coefficient
    cl_max_landing: float = 1.75  # Landing configuration maximum lift coefficient

    @classmethod
    def create(
        cls,
        cd0: float = 0.025,
        aspect_ratio: float = 10.0,
        oswald_e: float | None = None,
        cl_max_clean: float = 1.35,
        cl_max_takeoff: float = 1.55,
        cl_max_landing: float = 1.75,
    ) -> AeroParameters:
        """Create AeroParameters with automatic Oswald e estimation if not provided."""
        e = oswald_e if oswald_e is not None else calculate_oswald_raymer(aspect_ratio)
        return cls(
            cd0=float(cd0),
            aspect_ratio=float(aspect_ratio),
            oswald_e=float(e),
            cl_max_clean=float(cl_max_clean),
            cl_max_takeoff=float(cl_max_takeoff),
            cl_max_landing=float(cl_max_landing),
        )

    @property
    def k(self) -> float:
        """Induced drag factor k = 1 / (pi * AR * e)."""
        return calculate_induced_drag_factor(self.aspect_ratio, self.oswald_e)

    @property
    def max_lift_to_drag_ratio(self) -> float:
        """Maximum aerodynamic efficiency (L/D)_max = 1 / (2 * sqrt(CD0 * k))."""
        return 1.0 / (2.0 * math.sqrt(max(self.cd0, 1e-6) * self.k))

    @property
    def cl_at_max_ld(self) -> float:
        """Lift coefficient for maximum L/D: CL_opt = sqrt(CD0 / k)."""
        return math.sqrt(max(self.cd0, 1e-6) / max(self.k, 1e-6))

    def cd(self, cl: float) -> float:
        """Total drag coefficient for a given lift coefficient: CD = CD0 + k * CL^2."""
        return self.cd0 + self.k * (cl**2)


__all__ = [
    "AeroParameters",
    "calculate_induced_drag_factor",
    "calculate_oswald_raymer",
]
