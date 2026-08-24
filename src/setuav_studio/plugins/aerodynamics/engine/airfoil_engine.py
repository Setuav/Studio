"""2D NeuralFoil analysis engine with automated caching."""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

try:
    import aerosandbox as asb
    HAS_AEROSANDBOX = True
except ImportError:
    HAS_AEROSANDBOX = False

from .airfoil_cache import AirfoilPolarCache, global_airfoil_cache
from .airfoil_models import AirfoilPolar, AirfoilPolarPoint

class AirfoilAnalysisEngine:
    """Computes 2D airfoil aerodynamic characteristics using NeuralFoil."""

    def __init__(self, cache: AirfoilPolarCache | None = None) -> None:
        self.cache = cache or global_airfoil_cache

    def analyze_airfoil(
        self,
        airfoil: str | Sequence[Sequence[float]] | Any,
        reynolds: float,
        alphas: Sequence[float] | np.ndarray,
        mach: float = 0.0,
        use_cache: bool = True,
    ) -> AirfoilPolar:
        """Run 2D aerodynamic analysis on an airfoil across an angle of attack range.

        Args:
            airfoil: Name of airfoil (e.g. 'naca2412', 'clarky'), coordinate array, or asb.Airfoil object.
            reynolds: Reynolds number based on section chord.
            alphas: Angles of attack in degrees.
            mach: Flight Mach number (default 0.0).
            use_cache: Whether to query and populate the polar cache.

        Returns:
            AirfoilPolar instance with full section aerodynamic metrics.
        """
        if not HAS_AEROSANDBOX:
            raise RuntimeError("AeroSandbox is required for 2D airfoil analysis.")

        # Resolve asb.Airfoil instance and identifier
        asb_airfoil, ident = self._resolve_airfoil(airfoil)

        alphas_list = [float(a) for a in alphas]
        if not alphas_list:
            alphas_list = [0.0]

        # Check cache
        if use_cache:
            cached = self.cache.get(ident, reynolds, mach, alphas_list)
            if cached is not None:
                return cached

        polar = self._analyze_neuralfoil(
            asb_airfoil,
            reynolds,
            alphas_list,
            mach,
        )

        if use_cache and polar is not None:
            self.cache.put(polar, alphas_list, airfoil_identifier=ident)

        return polar

    def _resolve_airfoil(self, airfoil: Any) -> tuple[Any, str | Sequence[Sequence[float]]]:
        """Convert input to an asb.Airfoil instance and a hashable identifier string."""
        if hasattr(airfoil, "get_aero_from_neuralfoil"):
            name = getattr(airfoil, "name", "custom_airfoil")
            coordinates = getattr(airfoil, "coordinates", None)
            if coordinates is not None:
                return airfoil, tuple(tuple(float(v) for v in point) for point in np.asarray(coordinates).tolist())
            return airfoil, str(name)

        if isinstance(airfoil, str):
            clean_name = airfoil.strip().lower()
            return asb.Airfoil(clean_name), clean_name

        if isinstance(airfoil, (list, tuple, np.ndarray)):
            coords = np.asarray(airfoil, dtype=float)
            af = asb.Airfoil(name="custom_airfoil", coordinates=coords)
            ident = tuple(tuple(float(v) for v in point) for point in coords.tolist())
            return af, ident

        return asb.Airfoil("naca0012"), "naca0012"

    def _analyze_neuralfoil(
        self,
        airfoil: Any,
        reynolds: float,
        alphas: list[float],
        mach: float,
    ) -> AirfoilPolar:
        """Evaluate 2D section polar using the NeuralFoil deep-learning surrogate model."""
        alpha_arr = np.array(alphas, dtype=float)
        re_val = max(float(reynolds), 1000.0)
        mach_val = max(float(mach), 0.0)

        raw = airfoil.get_aero_from_neuralfoil(
            alpha=alpha_arr,
            Re=re_val,
            mach=mach_val,
        )

        cls = np.ravel(raw["CL"])
        cds = np.ravel(raw["CD"])
        cms = np.ravel(raw["CM"])

        def native_value(key: str, index: int) -> float | None:
            values = raw.get(key)
            if values is None:
                return None
            try:
                value = float(np.ravel(values)[index])
                return value if math.isfinite(value) else None
            except (IndexError, TypeError, ValueError):
                return None

        points: list[AirfoilPolarPoint] = []
        for i, a in enumerate(alphas):
            cl_i = float(cls[i])
            cd_i = max(float(cds[i]), 1e-5)
            cm_i = float(cms[i])
            ld_i = cl_i / cd_i if abs(cd_i) > 1e-7 else 0.0

            pt = AirfoilPolarPoint(
                alpha=float(a),
                cl=cl_i,
                cd=cd_i,
                cm=cm_i,
                cl_over_cd=ld_i,
                top_transition=native_value("Top_Xtr", i),
                bottom_transition=native_value("Bot_Xtr", i),
                analysis_confidence=native_value("analysis_confidence", i),
                mach_crit=native_value("mach_crit", i),
                mach_dd=native_value("mach_dd", i),
                converged=True,
            )
            points.append(pt)

        metrics = self._compute_summary_metrics(points)

        return AirfoilPolar(
            airfoil_name=str(airfoil.name),
            reynolds=re_val,
            mach=mach_val,
            points=points,
            cl_max=metrics["cl_max"],
            cl_max_alpha=metrics["cl_max_alpha"],
            cl_min=metrics["cl_min"],
            cl_min_alpha=metrics["cl_min_alpha"],
            cd_min=metrics["cd_min"],
            cl_at_cd_min=metrics["cl_at_cd_min"],
            ld_max=metrics["ld_max"],
            ld_max_alpha=metrics["ld_max_alpha"],
            cl_alpha_slope=metrics["cl_alpha_slope"],
            alpha_zero_lift=metrics["alpha_zero_lift"],
            cm_zero_lift=metrics["cm_zero_lift"],
            backend_used="neuralfoil",
        )

    def _compute_summary_metrics(self, points: list[AirfoilPolarPoint]) -> dict[str, float]:
        """Compute key aerodynamic coefficients and stability derivatives from polar points."""
        if not points:
            return {
                "cl_max": 0.0, "cl_max_alpha": 0.0,
                "cl_min": 0.0, "cl_min_alpha": 0.0,
                "cd_min": 0.0, "cl_at_cd_min": 0.0,
                "ld_max": 0.0, "ld_max_alpha": 0.0,
                "cl_alpha_slope": 0.1, "alpha_zero_lift": 0.0, "cm_zero_lift": 0.0,
            }

        valid_points = [p for p in points if p.converged]
        if not valid_points:
            return {
                "cl_max": 0.0, "cl_max_alpha": 0.0,
                "cl_min": 0.0, "cl_min_alpha": 0.0,
                "cd_min": 0.0, "cl_at_cd_min": 0.0,
                "ld_max": 0.0, "ld_max_alpha": 0.0,
                "cl_alpha_slope": 0.0, "alpha_zero_lift": 0.0, "cm_zero_lift": 0.0,
            }

        alphas = np.array([p.alpha for p in valid_points])
        cls = np.array([p.cl for p in valid_points])
        cds = np.array([p.cd for p in valid_points])
        cms = np.array([p.cm for p in valid_points])
        lds = np.array([p.cl_over_cd for p in valid_points])

        cl_max_idx = int(np.argmax(cls))
        cl_min_idx = int(np.argmin(cls))
        cd_min_idx = int(np.argmin(cds))
        ld_max_idx = int(np.argmax(lds))

        # Linear lift slope calculation in linear pre-stall region (e.g. -2 to 6 deg)
        mask = (alphas >= -4.0) & (alphas <= 6.0)
        if np.sum(mask) >= 2:
            poly = np.polyfit(alphas[mask], cls[mask], 1)
            cla_slope = float(poly[0])
            a0l = float(-poly[1] / poly[0]) if abs(poly[0]) > 1e-4 else 0.0
        else:
            cla_slope = float((cls[-1] - cls[0]) / (alphas[-1] - alphas[0])) if len(alphas) > 1 else 0.1
            a0l = 0.0

        # Pitching moment at zero lift (interpolate Cm at alpha_zero_lift)
        cm_zero = float(np.interp(a0l, alphas, cms))

        return {
            "cl_max": float(cls[cl_max_idx]),
            "cl_max_alpha": float(alphas[cl_max_idx]),
            "cl_min": float(cls[cl_min_idx]),
            "cl_min_alpha": float(alphas[cl_min_idx]),
            "cd_min": float(cds[cd_min_idx]),
            "cl_at_cd_min": float(cls[cd_min_idx]),
            "ld_max": float(lds[ld_max_idx]),
            "ld_max_alpha": float(alphas[ld_max_idx]),
            "cl_alpha_slope": cla_slope,
            "alpha_zero_lift": a0l,
            "cm_zero_lift": cm_zero,
        }
