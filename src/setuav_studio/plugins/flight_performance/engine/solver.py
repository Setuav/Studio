"""Flight performance envelope solver with automatic Aerodynamics, Propulsion, and Weight & Balance coupling."""
from __future__ import annotations

import logging
import math
from typing import Any, Callable, Sequence

import numpy as np
from pythrust.propellers.database import PropellerEntry
from pythrust.propulsion.models.motor import MotorSpec
from pythrust.propulsion.models.propeller import PropellerSpec
from scipy.optimize import root_scalar

from setuav_studio.plugins.aerodynamics.engine.aerosandbox_engine import (
    AeroSandboxEngine,
    AnalysisMethod,
    FlightCondition,
)
from setuav_studio.plugins.electrical_propulsion.engine.solver import PropulsionSolverEngine
from setuav_studio.plugins.weight_balance.engine.solver import WeightBalanceSolver

from .models import (
    CruisePerformance,
    FlightCurves,
    FlightEnvelopeResult,
    OptimalSpeeds,
    PerformanceMetrics,
)

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
            point for point in polar_points
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
        post_peak = [float(point.cl) for point in points[peak_index + 1:]]
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
            and len(velocities) == len(thrust_available) == len(thrust_required)
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
            velocities[last_valid]
            + fraction * (velocities[next_index] - velocities[last_valid])
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
        """Run comprehensive flight performance envelope analysis with auto-solver coupling."""
        # 1. Step 1: Resolve Mass Properties
        project = context.get("project")
        mass_kg = float(context.get("mass_kg", 0.0))
        if mass_kg <= 0.0:
            if project is not None:
                try:
                    wb_res = WeightBalanceSolver().evaluate(project)
                    mass_kg = float(wb_res.total.mass_kg)
                except Exception as exc:
                    logger.debug("WeightBalance evaluate failed; trying component mass sum: %s", exc)
                if mass_kg <= 0.0:
                    comps = project.data.get("components", [])
                    mass_kg = sum(
                        float(c.get("parameters", {}).get("mass", 0.0))
                        for c in comps
                        if isinstance(c, dict)
                    ) / 1000.0
        if mass_kg <= 0.0:
            raise ValueError(
                "Mass properties are unavailable. Define component masses or run Weight Balance before analysis."
            )

        area_m2 = float(context.get("area_m2", 0.0))
        rho = float(context.get("air_density", 1.225))
        cl_max = float(context.get("cl_max", 0.0))
        cd_min = float(context.get("cd_min", 0.0))
        ld_max_aero = float(context.get("ld_max", 0.0))

        v_min_cfg = float(context.get("v_min", 8.0))
        v_max_cfg = float(context.get("v_max", 35.0))
        v_step_cfg = float(context.get("v_step", 0.25))
        stall_margin = float(context.get("stall_margin", 1.15))

        battery_capacity_mah = context.get("battery_capacity_mah")
        battery_capacity_ah = (
            float(battery_capacity_mah) / 1000.0 if battery_capacity_mah is not None else None
        )
        battery_voltage = (
            float(context["battery_voltage"]) if context.get("battery_voltage") is not None else None
        )
        usable_battery_ratio = float(context.get("usable_battery_ratio", 0.85))

        motor_spec: MotorSpec | None = context.get("motor_spec")
        prop_spec: PropellerSpec | None = context.get("prop_spec")
        prop_entry: PropellerEntry | None = context.get("prop_entry")

        polar_cl_list = context.get("polar_cl")
        polar_cd_list = context.get("polar_cd")
        polar_alpha_list = context.get("polar_alpha")
        aero_summary: dict[str, Any] = {}
        aero_stall_confirmed: bool | None = None
        aero_stall_error: str | None = None

        # 2. Step 2: Always use AeroBuildup for the nonlinear stall limit.
        # LLT/VLM polar data may be supplied for other consumers, but they do
        # not determine CLmax or Vstall in this solver.
        components = context.get("components")
        if components and AeroSandboxEngine().is_available():
            if progress_callback:
                progress_callback(10, 100, "Aero Polar")
            try:
                aero_eng = AeroSandboxEngine()
                cond = FlightCondition(
                    velocity=15.0,
                    altitude=float(context.get("altitude", 0.0)),
                    alpha_min=-8.0,
                    alpha_max=25.0,
                    alpha_steps=67,
                    sweep_min=-8.0,
                    sweep_max=25.0,
                    sweep_steps=67,
                )
                aero_res = aero_eng.analyze(
                    components=components,
                    condition=cond,
                    method=AnalysisMethod.AERO_BUILDUP,
                )
                if aero_res.polar_points:
                    # Use the AeroBuildup polar for the performance model as
                    # well; this keeps the drag and stall limits consistent.
                    valid_polar = [p for p in aero_res.polar_points if p.converged]
                    polar_cl_list = [p.cl for p in valid_polar]
                    polar_cd_list = [p.cd for p in valid_polar]
                    polar_alpha_list = [p.alpha for p in valid_polar]
                    cl_max, cl_max_alpha, aero_stall_confirmed = cls._resolve_aerobuildup_clmax(
                        aero_res.polar_points
                    )
                    if aero_res.reference.s_ref > 0:
                        area_m2 = float(aero_res.reference.s_ref)
                    if aero_res.cd_min > 0:
                        cd_min = float(aero_res.cd_min)
                    if aero_res.ld_max > 0:
                        ld_max_aero = float(aero_res.ld_max)
                    aero_summary = {
                        "method": "AeroBuildup",
                        "cl_max": cl_max,
                        "cl_max_alpha": cl_max_alpha,
                        "cl_max_confirmed": aero_stall_confirmed,
                        "cd_min": cd_min,
                        "ld_max": ld_max_aero,
                        "s_ref": area_m2,
                        "points_count": len(polar_cl_list),
                    }
            except Exception as exc:
                aero_stall_error = str(exc)
                logger.warning("Auto AeroSandbox analysis failed: %s", exc)

        elif components:
            aero_stall_error = "AeroSandbox/AeroBuildup is unavailable."

        if area_m2 <= 0.0:
            area_m2 = 0.50
        if cl_max <= 0.0 and not components:
            cl_max = 1.20
        if cd_min <= 0.0:
            cd_min = 0.035
        if ld_max_aero <= 0.0:
            ld_max_aero = 12.0

        polar_cl = np.array(polar_cl_list, dtype=float) if polar_cl_list else None
        polar_cd = np.array(polar_cd_list, dtype=float) if polar_cd_list else None

        cd0 = k_induced = None
        if polar_cl is not None and polar_cd is not None and len(polar_cl) >= 3:
            fit_alpha_max = (
                float(aero_summary["cl_max_alpha"])
                if aero_summary.get("method") == "AeroBuildup"
                else None
            )
            cd0, k_induced = cls.fit_parabolic_cd(
                polar_cl,
                polar_cd,
                alpha_values=polar_alpha_list,
                alpha_max=fit_alpha_max,
            )

        if cd0 is None or k_induced is None:
            cd0 = cd_min
            aspect_ratio = float(context.get("aspect_ratio", 8.0))
            oswald = float(context.get("oswald_efficiency", 0.8))
            k_induced = 1.0 / (math.pi * aspect_ratio * oswald)

        if progress_callback:
            progress_callback(30, 100, "Grid")

        # 3. Stall speed & safe sweep bounds
        # Do not report a validated stall speed unless AeroBuildup produced a
        # post-peak CL decrease for a real project model.  Context-only unit
        # calls (without geometry) retain their explicit CLmax input.
        stall_cl_max = cl_max
        if components and (aero_stall_confirmed is not True or cl_max <= 0.0):
            stall_cl_max = 0.0
        v_stall = cls.compute_stall_speed(mass_kg, area_m2, stall_cl_max, rho)
        v_start = max(v_stall * stall_margin, v_min_cfg)
        v_end = max(v_start + 2.0, v_max_cfg)

        velocities_list: list[float] = []
        curr_v = v_start
        while curr_v <= v_end + 1e-4:
            velocities_list.append(curr_v)
            curr_v += v_step_cfg

        if len(velocities_list) < 5:
            velocities_list = np.linspace(v_start, v_end, 25).tolist()

        velocities = np.array(velocities_list, dtype=float)
        n_points = len(velocities)

        # 4. Aerodynamic power and drag required
        power_req, drag_req, cl_req = cls.compute_power_and_drag_required(
            velocities=velocities,
            mass_kg=mass_kg,
            area_m2=area_m2,
            rho=rho,
            polar_cl=polar_cl,
            polar_cd=polar_cd,
            cd0=cd0,
            k_induced=k_induced,
            default_cd=cd_min,
        )

        has_propulsion = (
            motor_spec is not None
            and prop_spec is not None
            and prop_entry is not None
            and battery_voltage is not None
            and battery_voltage > 0.0
            and motor_spec.kv_rpm_per_v > 0.0
            and motor_spec.current_max_a > 0.0
            and prop_spec.diameter_m > 0.0
            and prop_spec.pitch_m > 0.0
        )

        # Keep aerodynamic curves available even when propulsion inputs are
        # missing, but do not manufacture propulsion/electrical values.
        power_avail = np.zeros(n_points) if has_propulsion else np.array([])
        thrust_avail = np.zeros(n_points) if has_propulsion else np.array([])
        elec_power = np.zeros(n_points) if has_propulsion else np.array([])
        current_draw = np.zeros(n_points) if has_propulsion else np.array([])
        throttle_pct = np.zeros(n_points) if has_propulsion else np.array([])
        feasible_points = np.ones(n_points, dtype=bool)

        propulsion_summary = {
            "has_propulsion": has_propulsion,
            "motor_kv": motor_spec.kv_rpm_per_v if motor_spec else None,
            "motor_max_current": motor_spec.current_max_a if motor_spec else None,
            "prop_diameter_in": (prop_spec.diameter_m / 0.0254) if prop_spec else None,
            "prop_pitch_in": (prop_spec.pitch_m / 0.0254) if prop_spec else None,
            "battery_voltage": battery_voltage,
            "battery_capacity_ah": battery_capacity_ah,
        }

        # 5. Propulsion solving across velocities
        for i, v_val in enumerate(velocities):
            if progress_callback and n_points > 0:
                prog = int(40 + 45 * (i / n_points))
                progress_callback(prog, 100, f"{v_val:.1f} m/s")

            if has_propulsion and motor_spec and prop_spec and prop_entry and battery_voltage:
                # Available thrust/power must use the current-safe throttle,
                # not an over-current 100% throttle point.
                safe_max_throttle = cls._safe_max_throttle(
                    motor_spec=motor_spec,
                    prop_spec=prop_spec,
                    prop_entry=prop_entry,
                    total_voltage=battery_voltage,
                    rho=rho,
                    v_mps=float(v_val),
                )
                if safe_max_throttle > 0.0:
                    pt_max = PropulsionSolverEngine.solve_point(
                        motor_spec=motor_spec,
                        prop_spec=prop_spec,
                        prop_entry=prop_entry,
                        total_voltage=battery_voltage,
                        rho=rho,
                        v_mps=float(v_val),
                        throttle_val=safe_max_throttle,
                        x_val=float(v_val),
                    )
                    thrust_avail[i] = pt_max.thrust
                    power_avail[i] = pt_max.thrust * v_val

                # Equilibrium throttle and electric power for level flight
                thr_req, p_el, i_el, feas = cls.solve_propulsion_for_thrust(
                    motor_spec=motor_spec,
                    prop_spec=prop_spec,
                    prop_entry=prop_entry,
                    total_voltage=battery_voltage,
                    rho=rho,
                    v_mps=float(v_val),
                    thrust_req=float(drag_req[i]),
                )
                throttle_pct[i] = thr_req
                elec_power[i] = p_el
                current_draw[i] = i_el
                feasible_points[i] = (
                    safe_max_throttle > 0.0
                    and feas
                    and (thrust_avail[i] >= drag_req[i])
                )

        if progress_callback:
            progress_callback(90, 100, "Speeds")

        # 6. Rate of climb & climb angle
        weight_n = mass_kg * 9.81
        if has_propulsion:
            excess_power = np.maximum(0.0, power_avail - power_req)
            roc = excess_power / weight_n
            climb_ratio = np.clip(roc / np.maximum(velocities, 0.1), 0.0, 1.0)
            climb_angle_deg = np.degrees(np.arcsin(climb_ratio))
        else:
            roc = np.array([])
            climb_angle_deg = np.array([])

        # 7. Range & endurance curves
        range_km = np.zeros(n_points) if has_propulsion else np.array([])
        endurance_hours = np.zeros(n_points) if has_propulsion else np.array([])

        if has_propulsion and battery_capacity_ah is not None and battery_voltage is not None and battery_voltage > 0:
            usable_energy_wh = battery_voltage * battery_capacity_ah * usable_battery_ratio
            for i in range(n_points):
                if elec_power[i] > 0 and feasible_points[i]:
                    endurance_hours[i] = usable_energy_wh / elec_power[i]
                    range_km[i] = velocities[i] * 3.6 * endurance_hours[i]

        # 8. Optimal speeds identification
        feasible_mask = feasible_points & (elec_power > 0) if has_propulsion else np.zeros(n_points, dtype=bool)
        if has_propulsion and np.any(feasible_mask):
            feas_indices = np.where(feasible_mask)[0]
            idx_be = int(feas_indices[np.argmin(elec_power[feasible_mask])])
            idx_br = int(feas_indices[np.argmax(range_km[feasible_mask])])
            idx_vy = int(feas_indices[np.argmax(roc[feasible_mask])])
            best_endurance_spd = float(velocities[idx_be])
            best_range_spd = float(velocities[idx_br])
            best_climb_spd = float(velocities[idx_vy])
        elif has_propulsion:
            idx_be = int(np.argmin(power_req))
            power_over_v = power_req / np.maximum(velocities, 0.1)
            idx_br = int(np.argmin(power_over_v))
            idx_vy = int(np.argmax(roc))
            best_endurance_spd = float(velocities[idx_be])
            best_range_spd = float(velocities[idx_br])
            best_climb_spd = float(velocities[idx_vy])
        else:
            best_endurance_spd = 0.0
            best_range_spd = 0.0
            best_climb_spd = 0.0

        if has_propulsion:
            v_max, max_speed_bounded = cls.resolve_max_speed(
                velocities,
                thrust_avail,
                drag_req,
                feasible_points,
            )
        else:
            v_max, max_speed_bounded = 0.0, False

        # Best L/D estimation
        if cd0 is not None and k_induced is not None and k_induced > 0:
            cl_opt = math.sqrt(cd0 / k_induced)
            v_ld = float(math.sqrt(2.0 * weight_n / (rho * area_m2 * max(cl_opt, 0.01))))
            max_ld = float(1.0 / (2.0 * math.sqrt(cd0 * k_induced)))
        else:
            v_ld = best_range_spd if has_propulsion else 0.0
            max_ld = ld_max_aero

        max_roc = (
            float(np.max(roc[feasible_points]))
            if has_propulsion and np.any(feasible_points)
            else (float(np.max(roc)) if has_propulsion and len(roc) else 0.0)
        )
        best_gamma = (
            float(np.max(climb_angle_deg[feasible_points]))
            if has_propulsion and np.any(feasible_points)
            else (float(np.max(climb_angle_deg)) if has_propulsion and len(climb_angle_deg) else 0.0)
        )
        min_p_req = float(np.min(power_req))
        max_range = float(np.max(range_km)) if has_propulsion and len(range_km) else 0.0
        max_endurance = float(np.max(endurance_hours)) if has_propulsion and len(endurance_hours) else 0.0

        optimal_speeds = OptimalSpeeds(
            best_endurance=best_endurance_spd,
            best_range=best_range_spd,
            best_climb=best_climb_spd,
            best_ld=v_ld,
        )

        metrics = PerformanceMetrics(
            stall_speed=v_stall,
            max_speed=v_max,
            max_ld_ratio=max_ld,
            glide_ratio=max_ld,
            best_climb_angle_deg=best_gamma,
            min_power_required=min_p_req,
            max_range_km=max_range,
            max_endurance_hours=max_endurance,
            max_rate_of_climb=max_roc,
        )

        if has_propulsion:
            idx_cruise = idx_br
            cruise = CruisePerformance(
                speed=best_range_spd,
                power=float(elec_power[idx_cruise]),
                current=float(current_draw[idx_cruise]),
                throttle=float(throttle_pct[idx_cruise]),
                endurance=float(endurance_hours[idx_cruise]),
                range=float(range_km[idx_cruise]),
                feasible=bool(feasible_points[idx_cruise]),
            )
        else:
            cruise = CruisePerformance(feasible=False)

        curves = FlightCurves(
            velocities=velocities.tolist(),
            power_required=power_req.tolist(),
            power_available=power_avail.tolist(),
            thrust_required=drag_req.tolist(),
            thrust_available=thrust_avail.tolist(),
            rate_of_climb=roc.tolist(),
            climb_angle_deg=climb_angle_deg.tolist(),
            range_km=range_km.tolist(),
            endurance_hours=endurance_hours.tolist(),
            electrical_power=elec_power.tolist(),
            current_draw=current_draw.tolist(),
            throttle_pct=throttle_pct.tolist(),
            feasible=feasible_points.tolist(),
        )

        notes: list[str] = []
        propulsion_feasible: bool | None = None
        if not has_propulsion:
            propulsion_feasible = None
            notes.append("Propulsion data unavailable; aerodynamic-only analysis.")
        elif not np.any(feasible_points):
            propulsion_feasible = False
            notes.append("No feasible level flight operating points found within velocity sweep.")
        else:
            propulsion_feasible = True
        if has_propulsion and v_max <= 0.0:
            notes.append("No feasible level-flight speed found within the sweep.")
        elif has_propulsion and not max_speed_bounded:
            notes.append("Maximum speed is above the sweep limit; increase V_max to bound it.")
        if has_propulsion and v_max > 0.0 and v_stall >= v_max:
            notes.append("Stall speed exceeds maximum level flight speed (insufficient thrust/power).")
        if components and aero_stall_error:
            notes.append(f"AeroBuildup CLmax unavailable; stall speed not calculated: {aero_stall_error}")
        elif components and aero_stall_confirmed is not True:
            notes.append("AeroBuildup CLmax is unconfirmed; extend the alpha sweep before using Vstall.")

        if progress_callback:
            progress_callback(100, 100, "Done")

        return FlightEnvelopeResult(
            mass_kg=mass_kg,
            area_m2=area_m2,
            air_density=rho,
            cl_max=cl_max,
            cd0=cd0,
            k_induced=k_induced,
            battery_capacity_ah=battery_capacity_ah,
            battery_voltage=battery_voltage,
            optimal_speeds=optimal_speeds,
            metrics=metrics,
            cruise=cruise,
            curves=curves,
            propulsion_available=has_propulsion,
            propulsion_feasible=propulsion_feasible,
            feasible=bool(not has_propulsion or np.any(feasible_points)),
            notes=notes,
            aero_summary=aero_summary,
            propulsion_summary=propulsion_summary,
        )
