"""Data models for 2D Airfoil aerodynamic analysis results."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property
from typing import Any

import numpy as np

LINEAR_LIFT_RANGE_DEG = (-4.0, 6.0)
"""Angle-of-attack range the lift slope and zero-lift angle are fitted over."""


@dataclass(frozen=True)
class AirfoilPolarPoint:
    """Individual aerodynamic point for a 2D airfoil at a specific angle of attack."""

    alpha: float  # Angle of attack in degrees
    cl: float  # Section lift coefficient
    cd: float  # Section total drag coefficient
    cm: float  # Section quarter-chord pitching moment coefficient
    cd_profile: float | None = None  # Only when the backend exposes the decomposition
    cd_friction: float | None = None
    top_transition: float | None = None  # X/c transition location, when exposed
    bottom_transition: float | None = None
    analysis_confidence: float | None = None  # NeuralFoil confidence, when exposed
    mach_crit: float | None = None
    mach_dd: float | None = None
    converged: bool = True

    @property
    def cl_over_cd(self) -> float:
        return self.cl / self.cd if abs(self.cd) > 1e-9 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha": self.alpha,
            "cl": self.cl,
            "cd": self.cd,
            "cm": self.cm,
            "cd_profile": self.cd_profile,
            "cd_friction": self.cd_friction,
            "top_transition": self.top_transition,
            "bottom_transition": self.bottom_transition,
            "analysis_confidence": self.analysis_confidence,
            "mach_crit": self.mach_crit,
            "mach_dd": self.mach_dd,
            "converged": self.converged,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AirfoilPolarPoint:
        def optional(key: str) -> float | None:
            value = data[key]
            return None if value is None else float(value)

        return cls(
            alpha=float(data["alpha"]),
            cl=float(data["cl"]),
            cd=float(data["cd"]),
            cm=float(data["cm"]),
            cd_profile=optional("cd_profile"),
            cd_friction=optional("cd_friction"),
            top_transition=optional("top_transition"),
            bottom_transition=optional("bottom_transition"),
            analysis_confidence=optional("analysis_confidence"),
            mach_crit=optional("mach_crit"),
            mach_dd=optional("mach_dd"),
            converged=bool(data["converged"]),
        )


@dataclass(frozen=True)
class AirfoilPolarSummary:
    """Key coefficients of a polar's converged points."""

    cl_max: float
    cl_max_alpha: float
    cl_min: float
    cl_min_alpha: float
    cd_min: float
    cl_at_cd_min: float
    ld_max: float
    ld_max_alpha: float
    cl_alpha_slope: float | None
    """Lift slope in 1/deg; None when the polar has fewer than two points in the
    linear range."""
    alpha_zero_lift: float | None
    """Zero-lift angle in deg; None without a lift slope."""
    cm_zero_lift: float | None
    """Pitching moment at the zero-lift angle; None without that angle."""


def summarize_polar(points: list[AirfoilPolarPoint]) -> AirfoilPolarSummary:
    """Summarize the converged points of a polar."""
    valid = [p for p in points if p.converged]
    if not valid:
        raise ValueError("Airfoil polar has no converged points to summarize.")
    alphas = np.array([p.alpha for p in valid])
    cls = np.array([p.cl for p in valid])
    cds = np.array([p.cd for p in valid])
    cms = np.array([p.cm for p in valid])
    lds = np.divide(cls, cds, out=np.zeros_like(cls, dtype=float), where=np.abs(cds) > 1e-9)

    cl_max_idx = int(np.argmax(cls))
    cl_min_idx = int(np.argmin(cls))
    cd_min_idx = int(np.argmin(cds))
    ld_max_idx = int(np.argmax(lds))

    slope: float | None = None
    alpha_zero: float | None = None
    cm_zero: float | None = None
    low, high = LINEAR_LIFT_RANGE_DEG
    linear = (alphas >= low) & (alphas <= high)
    if np.sum(linear) >= 2:
        fit_slope, fit_intercept = np.polyfit(alphas[linear], cls[linear], 1)
        slope = float(fit_slope)
        if abs(slope) > 1e-4:
            alpha_zero = float(-fit_intercept / fit_slope)
            cm_zero = float(np.interp(alpha_zero, alphas, cms))

    return AirfoilPolarSummary(
        cl_max=float(cls[cl_max_idx]),
        cl_max_alpha=float(alphas[cl_max_idx]),
        cl_min=float(cls[cl_min_idx]),
        cl_min_alpha=float(alphas[cl_min_idx]),
        cd_min=float(cds[cd_min_idx]),
        cl_at_cd_min=float(cls[cd_min_idx]),
        ld_max=float(lds[ld_max_idx]),
        ld_max_alpha=float(alphas[ld_max_idx]),
        cl_alpha_slope=slope,
        alpha_zero_lift=alpha_zero,
        cm_zero_lift=cm_zero,
    )


@dataclass
class AirfoilPolar:
    """Complete 2D airfoil polar dataset across an angle of attack range."""

    airfoil_name: str
    reynolds: float
    mach: float
    n_crit: float
    model_size: str
    points: list[AirfoilPolarPoint]
    backend_used: str

    @cached_property
    def summary(self) -> AirfoilPolarSummary:
        return summarize_polar(self.points)

    def get_point(self, alpha: float, tolerance: float = 1e-3) -> AirfoilPolarPoint | None:
        """Find a polar point by alpha."""
        for pt in self.points:
            if math.isclose(pt.alpha, alpha, abs_tol=tolerance):
                return pt
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "airfoil_name": self.airfoil_name,
            "reynolds": self.reynolds,
            "mach": self.mach,
            "n_crit": self.n_crit,
            "model_size": self.model_size,
            "points": [p.to_dict() for p in self.points],
            "backend_used": self.backend_used,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AirfoilPolar:
        return cls(
            airfoil_name=str(data["airfoil_name"]),
            reynolds=float(data["reynolds"]),
            mach=float(data["mach"]),
            n_crit=float(data["n_crit"]),
            model_size=str(data["model_size"]),
            points=[AirfoilPolarPoint.from_dict(p) for p in data["points"]],
            backend_used=str(data["backend_used"]),
        )
