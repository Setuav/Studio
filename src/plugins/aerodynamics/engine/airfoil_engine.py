"""2D NeuralFoil analysis engine with automated caching."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np

from .aerosandbox_module import asb
from .airfoil_cache import AirfoilPolarCache, global_airfoil_cache
from .airfoil_models import AirfoilPolar, AirfoilPolarPoint


class AirfoilAnalysisEngine:
    """Computes 2D airfoil aerodynamic characteristics using NeuralFoil."""

    def __init__(self, cache: AirfoilPolarCache | None = None) -> None:
        self.cache = cache or global_airfoil_cache

    def analyze_airfoil(
        self,
        airfoil: Any,
        reynolds: float,
        alphas: Sequence[float] | np.ndarray,
        mach: float = 0.0,
        n_crit: float = 9.0,
        model_size: str = "large",
        use_cache: bool = True,
    ) -> AirfoilPolar:
        """Run 2D aerodynamic analysis on an airfoil across an angle of attack range.

        Args:
            airfoil: asb.Airfoil carrying the section coordinates.
            reynolds: Reynolds number based on section chord.
            alphas: Angles of attack in degrees.
            mach: Flight Mach number (default 0.0).
            n_crit: NeuralFoil boundary-layer amplification factor.
            model_size: NeuralFoil model size.
            use_cache: Whether to query and populate the polar cache.

        Returns:
            AirfoilPolar instance with full section aerodynamic metrics.
        """
        asb_airfoil, ident = self._resolve_airfoil(airfoil)

        alphas_list = [float(a) for a in alphas]
        if not alphas_list:
            raise ValueError("2D airfoil analysis needs at least one angle of attack.")
        n_crit = float(n_crit)
        model_size = str(model_size).strip().lower()
        if model_size not in {"small", "medium", "large", "xlarge"}:
            raise ValueError(f"Unsupported NeuralFoil model size: {model_size}")

        # Check cache
        if use_cache:
            cached = self.cache.get(
                ident,
                reynolds,
                mach,
                alphas_list,
                n_crit,
                model_size,
            )
            if cached is not None:
                return cached

        polar = self._analyze_neuralfoil(
            asb_airfoil,
            reynolds,
            alphas_list,
            mach,
            n_crit,
            model_size,
        )

        if use_cache and polar is not None:
            self.cache.put(
                polar,
                alphas_list,
                airfoil_identifier=ident,
                model_size=model_size,
            )

        return polar

    def _resolve_airfoil(self, airfoil: Any) -> tuple[Any, tuple[tuple[float, ...], ...]]:
        """Validate an asb.Airfoil and return it with its coordinate cache identifier."""
        if not isinstance(airfoil, asb.Airfoil):
            raise TypeError(
                f"2D airfoil analysis expects an aerosandbox Airfoil, got {type(airfoil).__name__}"
            )
        if airfoil.coordinates is None:
            raise ValueError(f"Airfoil {airfoil.name!r} has no coordinates to analyze.")
        return airfoil, tuple(
            tuple(float(v) for v in point) for point in np.asarray(airfoil.coordinates).tolist()
        )

    def _analyze_neuralfoil(
        self,
        airfoil: Any,
        reynolds: float,
        alphas: list[float],
        mach: float,
        n_crit: float,
        model_size: str,
    ) -> AirfoilPolar:
        """Evaluate 2D section polar using the NeuralFoil deep-learning surrogate model."""
        alpha_arr = np.array(alphas, dtype=float)
        re_val = max(float(reynolds), 1000.0)
        mach_val = max(float(mach), 0.0)

        raw = airfoil.get_aero_from_neuralfoil(
            alpha=alpha_arr,
            Re=re_val,
            mach=mach_val,
            n_crit=n_crit,
            model_size=model_size,
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
            pt = AirfoilPolarPoint(
                alpha=float(a),
                cl=float(cls[i]),
                cd=float(cds[i]),
                cm=float(cms[i]),
                top_transition=native_value("Top_Xtr", i),
                bottom_transition=native_value("Bot_Xtr", i),
                analysis_confidence=native_value("analysis_confidence", i),
                mach_crit=native_value("mach_crit", i),
                mach_dd=native_value("mach_dd", i),
                converged=True,
            )
            points.append(pt)

        return AirfoilPolar(
            airfoil_name=str(airfoil.name),
            reynolds=re_val,
            mach=mach_val,
            n_crit=n_crit,
            model_size=model_size,
            points=points,
            backend_used=f"neuralfoil ({model_size})",
        )
