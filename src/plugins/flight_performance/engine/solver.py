"""Flight performance envelope solver with automatic Aerodynamics, Propulsion, and Weight & Balance coupling."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from pythrust.propellers.database import PropellerEntry
from pythrust.propulsion.models.motor import MotorSpec
from pythrust.propulsion.models.propeller import PropellerSpec
from scipy.optimize import root_scalar

from plugins.electrical_propulsion.engine.solver import PropulsionSolverEngine

from .analysis_pipeline import FlightPerformanceAnalysisPipeline
from .models import FlightEnvelopeResult

logger = logging.getLogger(__name__)


class FlightPerformanceSolver:
    """Analytical solver for fixed-wing flight performance envelopes."""

    @staticmethod
    def _resolve_aerobuildup_clmax(
        polar_points: Sequence[Any],
    ) -> tuple[float, float, bool]:
        """Resolve CLmax from an AeroBuildup polar and verify stall evidence.

        AeroBuildup is the only source used for the stall limit.  A peak is
        considered confirmed only when the post-peak polar contains a
        meaningful CL decrease; otherwise the sweep has not reached stall and
        a stall speed must not be presented as a validated result.
        """
        points = [
            point
            for point in polar_points
            if getattr(point, "converged", False)
            and math.isfinite(float(getattr(point, "cl", 0.0)))
            and math.isfinite(float(getattr(point, "alpha", 0.0)))
        ]
        if not points:
            return 0.0, 0.0, False

        peak_index = max(range(len(points)), key=lambda index: float(points[index].cl))
        peak = points[peak_index]
        cl_max = float(peak.cl)
        alpha_max = float(peak.alpha)
        post_peak = [float(point.cl) for point in points[peak_index + 1 :]]
        drop_threshold = max(abs(cl_max) * 0.02, 0.01)
        confirmed = bool(post_peak and min(post_peak) <= cl_max - drop_threshold)
        return cl_max, alpha_max, confirmed

    @staticmethod
    def compute_stall_speed(
        mass_kg: float,
        area_m2: float,
        cl_max: float,
        rho: float = 1.225,
    ) -> float:
        """Compute stall speed in m/s: V_stall = sqrt(2 * W / (rho * S * CL_max))."""
        if mass_kg <= 0 or area_m2 <= 0 or cl_max <= 0 or rho <= 0:
            return 0.0
        weight_n = mass_kg * 9.81
        return float(math.sqrt(2.0 * weight_n / (rho * area_m2 * cl_max)))

    @staticmethod
    def resolve_max_speed(
        velocities: np.ndarray,
        thrust_available: np.ndarray,
        thrust_required: np.ndarray,
        feasible_points: np.ndarray,
    ) -> tuple[float, bool]:
        """Find the thrust-balance speed and whether it is sweep-bounded.

        The maximum level-flight speed is where available thrust falls below
        required thrust. Linear interpolation between adjacent sweep points
        gives a better estimate than returning the last sampled velocity.
        The boolean is false when the requested sweep ends before a crossing.
        """
        if not (
            len(velocities)
            and len(velocities)
            == len(thrust_available)
            == len(thrust_required)
            == len(feasible_points)
        ):
            return 0.0, False

        margin = thrust_available - thrust_required
        valid = np.asarray(feasible_points, dtype=bool) & (margin >= 0.0)
        valid_indices = np.flatnonzero(valid)
        if not len(valid_indices):
            return 0.0, False

        last_valid = int(valid_indices[-1])
        if last_valid >= len(velocities) - 1:
            return float(velocities[last_valid]), False

        # Interpolate the first available-to-required thrust crossing after
        # the last valid operating point.
        next_index = last_valid + 1
        m0 = float(margin[last_valid])
        m1 = float(margin[next_index])
        if m1 >= 0.0:
            return float(velocities[last_valid]), False
        denominator = m0 - m1
        if denominator <= 0.0:
            return float(velocities[last_valid]), True
        fraction = max(0.0, min(1.0, m0 / denominator))
        speed = float(
            velocities[last_valid] + fraction * (velocities[next_index] - velocities[last_valid])
        )
        return speed, True

    @staticmethod
    def fit_parabolic_cd(
        cl_values: Sequence[float],
        cd_values: Sequence[float],
        *,
        alpha_values: Sequence[float] | None = None,
        alpha_max: float | None = None,
    ) -> tuple[float | None, float | None]:
        """Fit the physical pre-stall drag polar ``CD = CD0 + k * CL²``.

        If alpha values are supplied, points after the CLmax angle are
        excluded so post-stall drag cannot bias the fit.  Invalid/negative CD
        samples and non-physical fits are rejected instead of silently
        coercing the induced-drag factor to a positive value.
        """
        if len(cl_values) < 3 or len(cl_values) != len(cd_values):
            return None, None
        if alpha_values is not None and len(alpha_values) != len(cl_values):
            return None, None

        cl_arr = np.array(cl_values, dtype=float)
        cd_arr = np.array(cd_values, dtype=float)
        valid = np.isfinite(cl_arr) & np.isfinite(cd_arr) & (cd_arr > 0.0)
        if alpha_values is not None and alpha_max is not None:
            alpha_arr = np.array(alpha_values, dtype=float)
            valid &= np.isfinite(alpha_arr) & (alpha_arr <= float(alpha_max) + 1e-9)
        cl_arr = cl_arr[valid]
        cd_arr = cd_arr[valid]
        if len(cl_arr) < 3:
            return None, None

        x = cl_arr**2
        y = cd_arr
        if float(np.ptp(x)) <= 1e-12:
            return None, None
        a_mat = np.vstack([np.ones_like(x), x]).T
        try:
            coeffs, _, _, _ = np.linalg.lstsq(a_mat, y, rcond=None)
            cd0 = float(coeffs[0])
            k_ind = float(coeffs[1])
            if not (math.isfinite(cd0) and math.isfinite(k_ind) and cd0 > 0.0 and k_ind > 0.0):
                return None, None

            fitted = a_mat @ coeffs
            residual = float(np.sum((y - fitted) ** 2))
            total = float(np.sum((y - float(np.mean(y))) ** 2))
            if total > 1e-12 and 1.0 - residual / total < 0.80:
                return None, None
            return cd0, k_ind
        except Exception as exc:
            logger.debug("Parabolic CD fit failed: %s", exc)
            return None, None

    @classmethod
    def compute_power_and_drag_required(
        cls,
        velocities: np.ndarray,
        mass_kg: float,
        area_m2: float,
        rho: float,
        polar_cl: np.ndarray | None = None,
        polar_cd: np.ndarray | None = None,
        cd0: float | None = None,
        k_induced: float | None = None,
        default_cd: float = 0.035,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Compute required CL, drag force (N), and aerodynamic power (W) across velocities."""
        weight_n = mass_kg * 9.81
        q_dyn = 0.5 * rho * (velocities**2) * area_m2
        q_dyn_safe = np.maximum(q_dyn, 1e-4)
        cl_required = weight_n / q_dyn_safe

        if cd0 is not None and k_induced is not None:
            cd_estimate = cd0 + k_induced * (cl_required**2)
        elif polar_cl is not None and polar_cd is not None and len(polar_cl) >= 2:
            sort_idx = np.argsort(polar_cl)
            cd_estimate = np.interp(cl_required, polar_cl[sort_idx], polar_cd[sort_idx])
        else:
            cd_estimate = np.full_like(cl_required, default_cd)

        drag_n = q_dyn * cd_estimate
        power_w = drag_n * velocities
        return power_w, drag_n, cl_required

    @classmethod
    def solve_propulsion_for_thrust(
        cls,
        *,
        motor_spec: MotorSpec,
        prop_spec: PropellerSpec,
        prop_entry: PropellerEntry,
        total_voltage: float,
        rho: float,
        v_mps: float,
        thrust_req: float,
    ) -> tuple[float, float, float, bool]:
        """Find throttle and electrical power needed to match thrust_req at v_mps."""
        if thrust_req <= 0.0:
            return 0.0, 0.0, 0.0, True

        # Full throttle can exceed the motor current limit even when the
        # requested thrust is achievable at a lower throttle. Find the
        # highest current-safe throttle first and solve only inside that
        # operating range.
        safe_max_throttle = cls._safe_max_throttle(
            motor_spec=motor_spec,
            prop_spec=prop_spec,
            prop_entry=prop_entry,
            total_voltage=total_voltage,
            rho=rho,
            v_mps=v_mps,
        )
        if safe_max_throttle <= 0.0:
            return 0.0, 0.0, 0.0, False

        pt_limit = PropulsionSolverEngine.solve_point(
            motor_spec=motor_spec,
            prop_spec=prop_spec,
            prop_entry=prop_entry,
            total_voltage=total_voltage,
            rho=rho,
            v_mps=v_mps,
            throttle_val=safe_max_throttle,
            x_val=v_mps,
        )
        if pt_limit.thrust < thrust_req:
            return safe_max_throttle * 100.0, pt_limit.power, pt_limit.current, False

        def f_thr(thr: float) -> float:
            pt = PropulsionSolverEngine.solve_point(
                motor_spec=motor_spec,
                prop_spec=prop_spec,
                prop_entry=prop_entry,
                total_voltage=total_voltage,
                rho=rho,
                v_mps=v_mps,
                throttle_val=thr,
                x_val=v_mps,
            )
            return pt.thrust - thrust_req

        try:
            low_throttle = 0.0
            low_thrust = f_thr(low_throttle)
            if low_thrust >= 0.0:
                thr_solved = low_throttle
            else:
                res_root = root_scalar(
                    f_thr,
                    bracket=[low_throttle, safe_max_throttle],
                    method="brentq",
                )
                thr_solved = float(res_root.root)
            pt_solved = PropulsionSolverEngine.solve_point(
                motor_spec=motor_spec,
                prop_spec=prop_spec,
                prop_entry=prop_entry,
                total_voltage=total_voltage,
                rho=rho,
                v_mps=v_mps,
                throttle_val=thr_solved,
                x_val=v_mps,
            )
            feasible = pt_solved.current <= motor_spec.current_max_a
            return thr_solved * 100.0, pt_solved.power, pt_solved.current, feasible
        except Exception as exc:
            logger.debug("Throttle root solving failed at v=%.1f m/s (%s)", v_mps, exc)
            return safe_max_throttle * 100.0, pt_limit.power, pt_limit.current, False

    @staticmethod
    def _safe_max_throttle(
        *,
        motor_spec: MotorSpec,
        prop_spec: PropellerSpec,
        prop_entry: PropellerEntry,
        total_voltage: float,
        rho: float,
        v_mps: float,
    ) -> float:
        """Return the highest throttle that stays within the motor limit."""
        current_limit = float(motor_spec.current_max_a)
        if current_limit <= 0.0 or total_voltage <= 0.0:
            return 0.0

        def point(throttle: float):
            return PropulsionSolverEngine.solve_point(
                motor_spec=motor_spec,
                prop_spec=prop_spec,
                prop_entry=prop_entry,
                total_voltage=total_voltage,
                rho=rho,
                v_mps=v_mps,
                throttle_val=throttle,
                x_val=v_mps,
            )

        low_point = point(0.0)
        if low_point.current > current_limit:
            return 0.0

        high_point = point(1.0)
        if high_point.current <= current_limit:
            return 1.0

        # Current is monotonic with throttle for the motor model. A bounded
        # bisection avoids relying on a second nested root solver here.
        low, high = 0.0, 1.0
        for _ in range(32):
            mid = (low + high) * 0.5
            if point(mid).current <= current_limit:
                low = mid
            else:
                high = mid
        return low

    @classmethod
    def run_analysis(
        cls,
        context: dict[str, Any],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> FlightEnvelopeResult:
        """Run the staged flight-performance envelope analysis."""
        return FlightPerformanceAnalysisPipeline(cls, context, progress_callback).run()
