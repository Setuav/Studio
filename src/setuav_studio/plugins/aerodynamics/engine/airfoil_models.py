"""Data models for 2D Airfoil aerodynamic analysis results."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AirfoilPolarPoint:
    """Individual aerodynamic point for a 2D airfoil at a specific angle of attack."""
    alpha: float  # Angle of attack in degrees
    cl: float  # Section lift coefficient
    cd: float  # Section total drag coefficient
    cm: float  # Section quarter-chord pitching moment coefficient
    cd_profile: float = 0.0  # Section pressure/form drag
    cd_friction: float = 0.0  # Section skin friction drag
    top_separation: float = 0.0  # Boundary layer separation location (0=leading edge, 1=trailing edge)
    bottom_separation: float = 0.0
    cl_over_cd: float = 0.0
    converged: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha": self.alpha,
            "cl": self.cl,
            "cd": self.cd,
            "cm": self.cm,
            "cd_profile": self.cd_profile,
            "cd_friction": self.cd_friction,
            "top_separation": self.top_separation,
            "bottom_separation": self.bottom_separation,
            "cl_over_cd": self.cl_over_cd,
            "converged": self.converged,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AirfoilPolarPoint:
        return cls(
            alpha=float(data.get("alpha", 0.0)),
            cl=float(data.get("cl", 0.0)),
            cd=float(data.get("cd", 0.0)),
            cm=float(data.get("cm", 0.0)),
            cd_profile=float(data.get("cd_profile", 0.0)),
            cd_friction=float(data.get("cd_friction", 0.0)),
            top_separation=float(data.get("top_separation", 0.0)),
            bottom_separation=float(data.get("bottom_separation", 0.0)),
            cl_over_cd=float(data.get("cl_over_cd", 0.0)),
            converged=bool(data.get("converged", True)),
        )


@dataclass
class AirfoilPolar:
    """Complete 2D airfoil polar dataset across an angle of attack range."""
    airfoil_name: str
    reynolds: float
    mach: float = 0.0
    n_crit: float = 9.0
    points: list[AirfoilPolarPoint] = field(default_factory=list)
    # Summary metrics
    cl_max: float = 0.0
    cl_max_alpha: float = 0.0
    cl_min: float = 0.0
    cl_min_alpha: float = 0.0
    cd_min: float = 0.0
    cl_at_cd_min: float = 0.0
    ld_max: float = 0.0
    ld_max_alpha: float = 0.0
    cl_alpha_slope: float = 0.0  # dCl/d_alpha in 1/deg
    alpha_zero_lift: float = 0.0  # Angle of attack where Cl = 0 in deg
    cm_zero_lift: float = 0.0  # Pitching moment at zero lift
    backend_used: str = "neuralfoil"

    def get_point(self, alpha: float, tolerance: float = 1e-3) -> AirfoilPolarPoint | None:
        """Find a polar point by alpha."""
        for pt in self.points:
            if math.isclose(pt.alpha, alpha, abs_tol=tolerance):
                return pt
        return None

    def interpolate(self, alpha: float) -> tuple[float, float, float]:
        """Interpolate (Cl, Cd, Cm) at an arbitrary angle of attack."""
        if not self.points:
            return (0.0, 0.0, 0.0)
        alphas = [p.alpha for p in self.points]
        if alpha <= alphas[0]:
            p0 = self.points[0]
            return (p0.cl, p0.cd, p0.cm)
        if alpha >= alphas[-1]:
            p_last = self.points[-1]
            return (p_last.cl, p_last.cd, p_last.cm)

        # Linear interpolation between adjacent points
        for i in range(len(alphas) - 1):
            if alphas[i] <= alpha <= alphas[i + 1]:
                t = (alpha - alphas[i]) / (alphas[i + 1] - alphas[i])
                p1, p2 = self.points[i], self.points[i + 1]
                cl = (1 - t) * p1.cl + t * p2.cl
                cd = (1 - t) * p1.cd + t * p2.cd
                cm = (1 - t) * p1.cm + t * p2.cm
                return (cl, cd, cm)
        return (0.0, 0.0, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "airfoil_name": self.airfoil_name,
            "reynolds": self.reynolds,
            "mach": self.mach,
            "n_crit": self.n_crit,
            "points": [p.to_dict() for p in self.points],
            "cl_max": self.cl_max,
            "cl_max_alpha": self.cl_max_alpha,
            "cl_min": self.cl_min,
            "cl_min_alpha": self.cl_min_alpha,
            "cd_min": self.cd_min,
            "cl_at_cd_min": self.cl_at_cd_min,
            "ld_max": self.ld_max,
            "ld_max_alpha": self.ld_max_alpha,
            "cl_alpha_slope": self.cl_alpha_slope,
            "alpha_zero_lift": self.alpha_zero_lift,
            "cm_zero_lift": self.cm_zero_lift,
            "backend_used": self.backend_used,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AirfoilPolar:
        pts = [AirfoilPolarPoint.from_dict(p) for p in data.get("points", []) if isinstance(p, dict)]
        return cls(
            airfoil_name=str(data.get("airfoil_name", "")),
            reynolds=float(data.get("reynolds", 0.0)),
            mach=float(data.get("mach", 0.0)),
            n_crit=float(data.get("n_crit", 9.0)),
            points=pts,
            cl_max=float(data.get("cl_max", 0.0)),
            cl_max_alpha=float(data.get("cl_max_alpha", 0.0)),
            cl_min=float(data.get("cl_min", 0.0)),
            cl_min_alpha=float(data.get("cl_min_alpha", 0.0)),
            cd_min=float(data.get("cd_min", 0.0)),
            cl_at_cd_min=float(data.get("cl_at_cd_min", 0.0)),
            ld_max=float(data.get("ld_max", 0.0)),
            ld_max_alpha=float(data.get("ld_max_alpha", 0.0)),
            cl_alpha_slope=float(data.get("cl_alpha_slope", 0.0)),
            alpha_zero_lift=float(data.get("alpha_zero_lift", 0.0)),
            cm_zero_lift=float(data.get("cm_zero_lift", 0.0)),
            backend_used=str(data.get("backend_used", "neuralfoil")),
        )
