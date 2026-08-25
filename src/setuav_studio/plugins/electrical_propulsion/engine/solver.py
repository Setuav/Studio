"""Analytical solver for electric propulsion system equilibrium and performance sweeps."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from typing import Any

from pythrust.propellers.database import PropellerDataPoint, PropellerEntry, PropellerMetadata
from pythrust.propulsion.models.motor import MotorSpec
from pythrust.propulsion.models.propeller import PropellerSpec
from scipy.optimize import root_scalar

from .base import PropulsionPoint

logger = logging.getLogger(__name__)


class PropulsionSolverEngine:
    """Analytical solver for electric propulsion system equilibrium and performance sweeps."""

    @staticmethod
    def fallback_propeller(diameter_in: float, pitch_in: float, blades: int = 2) -> PropellerEntry:
        """Construct synthetic analytical propeller polar when no database match exists."""
        prop_meta = PropellerMetadata(
            id=f"prop_{diameter_in:.1f}x{pitch_in:.1f}",
            manufacturer="APC",
            model=f"{diameter_in:.1f}x{pitch_in:.1f}",
            diameter_in=diameter_in,
            pitch_in=pitch_in,
            blade_count=blades,
            data_csv="",
        )
        prop_data: dict[int, list[PropellerDataPoint]] = {}
        p_d = pitch_in / max(diameter_in, 1e-3)
        j_max = p_d * 1.15
        for r in [2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 12000, 15000]:
            pts = []
            for j_i in range(30):
                j_val = j_i * (j_max / 29.0)
                ct_val = max(0.12 - 0.10 * (j_val / max(p_d, 0.1)), 0.0)
                cp_val = max(0.06 - 0.03 * (j_val / max(p_d, 0.1)), 0.005)
                pts.append(PropellerDataPoint(j=j_val, ct=ct_val, cp=cp_val))
            prop_data[r] = pts
        return PropellerEntry(metadata=prop_meta, data_by_rpm=prop_data)

    @classmethod
    def solve_rpm(
        cls,
        *,
        motor_spec: MotorSpec,
        prop_spec: PropellerSpec,
        prop_entry: PropellerEntry,
        total_voltage: float,
        rho: float,
        v_mps: float,
        throttle_val: float,
    ) -> float:
        """Find equilibrium operating RPM using BrentQ root solver."""
        v_app = max(throttle_val * total_voltage, 0.1)
        rpm_max = motor_spec.kv_rpm_per_v * v_app * 1.05

        def g(rpm_val: float) -> float:
            if rpm_val <= 10.0:
                return -v_app
            n_val = rpm_val / 60.0
            j_val = v_mps / (n_val * prop_spec.diameter_m) if prop_spec.diameter_m > 0 else 0.0
            ct_v, cp_v = prop_entry.get_coefficients(rpm_val, j_val)
            ct_v = max(ct_v, 0.0)
            cp_v = max(cp_v, 0.0)
            torque_nm = cp_v * rho * (n_val**2) * (prop_spec.diameter_m**5) / (2.0 * math.pi)
            kt = 30.0 / (math.pi * motor_spec.kv_rpm_per_v)
            i_a = torque_nm / kt + motor_spec.get_no_load_current(rpm_val)
            v_b = rpm_val / motor_spec.kv_rpm_per_v
            v_mot = v_b + i_a * motor_spec.get_winding_resistance(i_a)
            return v_mot + i_a * 0.01 - v_app

        try:
            res_root = root_scalar(g, bracket=[100.0, rpm_max], method="brentq")
            return res_root.root
        except (ValueError, RuntimeError) as exc:
            logger.debug("RPM solver bracket fallback at v=%.1f m/s (%s)", v_mps, exc)
            return rpm_max

    @classmethod
    def solve_point(
        cls,
        *,
        motor_spec: MotorSpec,
        prop_spec: PropellerSpec,
        prop_entry: PropellerEntry,
        total_voltage: float,
        rho: float,
        v_mps: float,
        throttle_val: float,
        x_val: float = 0.0,
    ) -> PropulsionPoint:
        """Calculate complete propulsion point metrics."""
        rpm_solved = cls.solve_rpm(
            motor_spec=motor_spec,
            prop_spec=prop_spec,
            prop_entry=prop_entry,
            total_voltage=total_voltage,
            rho=rho,
            v_mps=v_mps,
            throttle_val=throttle_val,
        )
        n = rpm_solved / 60.0
        j_solved = v_mps / (n * prop_spec.diameter_m) if (n * prop_spec.diameter_m) > 0 else 0.0
        ct_s, cp_s = prop_entry.get_coefficients(rpm_solved, j_solved)
        ct_s = max(ct_s, 0.0)
        cp_s = max(cp_s, 0.0)
        thrust = ct_s * rho * (n**2) * (prop_spec.diameter_m**4)
        p_shaft = cp_s * rho * (n**3) * (prop_spec.diameter_m**5)
        torque_nm = p_shaft / (2.0 * math.pi * n) if n > 0 else 0.0
        kt = 30.0 / (math.pi * motor_spec.kv_rpm_per_v)
        current_a = torque_nm / kt + motor_spec.get_no_load_current(rpm_solved)
        v_back = rpm_solved / motor_spec.kv_rpm_per_v
        v_motor = v_back + current_a * motor_spec.get_winding_resistance(current_a)
        p_elec = v_motor * current_a
        eta_p = (thrust * v_mps) / p_shaft if p_shaft > 0 else 0.0
        eta_m = p_shaft / p_elec if p_elec > 0 else 0.0
        eta_sys = (thrust * v_mps) / p_elec if p_elec > 0 else 0.0
        feasible = current_a <= motor_spec.current_max_a

        return PropulsionPoint(
            x_val=x_val,
            rpm=rpm_solved,
            thrust=max(thrust, 0.0),
            power=max(p_elec, 0.0),
            current=max(current_a, 0.0),
            eta_p=min(max(eta_p, 0.0), 1.0),
            eta_m=min(max(eta_m, 0.0), 1.0),
            eta_sys=min(max(eta_sys, 0.0), 1.0),
            j=j_solved,
            feasible=feasible,
        )

    @staticmethod
    def _arange(start: float, end: float, step: float) -> list[float]:
        values: list[float] = []
        curr = start
        while curr <= end + 1e-4:
            values.append(curr)
            curr += step
        return values

    @classmethod
    def run_airspeed_sweep(
        cls,
        context: dict[str, Any],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        """Execute airspeed parametric sweep."""
        params = context["params"]
        motor_spec: MotorSpec = context["motor_spec"]
        prop_spec: PropellerSpec = context["prop_spec"]
        prop_entry: PropellerEntry = context["prop_entry"]
        total_voltage: float = context["total_voltage"]
        capacity_mah: float = context["capacity_mah"]
        rho: float = context["rho"]

        throttle_pct = float(params.get("throttle", 100.0))
        v_min = float(params.get("v_min", 0.0))
        v_max = float(params.get("v_max", 35.0))
        v_step = max(float(params.get("v_step", 1.0)), 0.1)

        x_vals: list[float] = []
        thrusts: list[float] = []
        powers: list[float] = []
        currents: list[float] = []
        rpms: list[float] = []
        eta_tots: list[float] = []
        eta_props: list[float] = []
        eta_mots: list[float] = []
        sweep_rows: list[dict[str, Any]] = []

        throttle_norm = max(min(throttle_pct / 100.0, 1.0), 0.01)
        v_vals = cls._arange(v_min, v_max, v_step)
        total_points = len(v_vals)
        for index, curr_v in enumerate(v_vals, start=1):
            if progress_callback:
                progress_callback(index, total_points, f"Airspeed {curr_v:.0f} m/s")
            pt = cls.solve_point(
                motor_spec=motor_spec,
                prop_spec=prop_spec,
                prop_entry=prop_entry,
                total_voltage=total_voltage,
                rho=rho,
                v_mps=curr_v,
                throttle_val=throttle_norm,
                x_val=curr_v,
            )
            x_vals.append(curr_v)
            thrusts.append(pt.thrust)
            powers.append(pt.power)
            currents.append(pt.current)
            rpms.append(pt.rpm)
            eta_tots.append(pt.eta_sys)
            eta_props.append(pt.eta_p)
            eta_mots.append(pt.eta_m)
            sweep_rows.append(
                {
                    "x_val": curr_v,
                    "x_label": "Airspeed (m/s)",
                    "rpm": pt.rpm,
                    "thrust": pt.thrust,
                    "power": pt.power,
                    "current": pt.current,
                    "eta_sys": pt.eta_sys,
                    "eta_p": pt.eta_p,
                    "eta_m": pt.eta_m,
                    "j": pt.j,
                    "feasible": pt.feasible,
                }
            )

        cruise_idx = min(len(x_vals) - 1, max(0, int(len(x_vals) * 0.5)))
        cruise_power = max(powers[cruise_idx], 1e-3)
        batt_wh = total_voltage * capacity_mah / 1000.0
        endurance_min = (batt_wh * 0.8 / cruise_power) * 60.0

        return {
            "mode": "airspeed_sweep",
            "x_label": "Airspeed (m/s)",
            "x_values": x_vals,
            "thrust_n": thrusts,
            "power_w": powers,
            "current_a": currents,
            "rpm": rpms,
            "eta_total": eta_tots,
            "eta_prop": eta_props,
            "eta_motor": eta_mots,
            "static_thrust": thrusts[0] if thrusts else 0.0,
            "peak_power": max(powers) if powers else 0.0,
            "peak_current": max(currents) if currents else 0.0,
            "max_rpm": max(rpms) if rpms else 0.0,
            "cruise_thrust": thrusts[cruise_idx] if thrusts else 0.0,
            "cruise_efficiency": eta_tots[cruise_idx] if eta_tots else 0.0,
            "endurance_min": endurance_min,
            "advance_ratio": (
                x_vals[cruise_idx] / max((rpms[cruise_idx] / 60.0) * prop_spec.diameter_m, 1e-3)
            ),
            "prop_efficiency": eta_props[cruise_idx],
            "motor_efficiency": eta_mots[cruise_idx],
            "voltage_loaded": total_voltage - currents[cruise_idx] * 0.02,
            "sweep_table": sweep_rows,
            "motor_max_current": motor_spec.current_max_a,
            "clear_charts": False,
        }

    @classmethod
    def run_throttle_sweep(
        cls,
        context: dict[str, Any],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        """Execute throttle parametric sweep."""
        params = context["params"]
        motor_spec: MotorSpec = context["motor_spec"]
        prop_spec: PropellerSpec = context["prop_spec"]
        prop_entry: PropellerEntry = context["prop_entry"]
        total_voltage: float = context["total_voltage"]
        capacity_mah: float = context["capacity_mah"]
        rho: float = context["rho"]

        v_fixed = float(params.get("airspeed", 15.0))
        t_min = float(params.get("t_min", 10.0))
        t_max = float(params.get("t_max", 100.0))
        t_step = max(float(params.get("t_step", 5.0)), 1.0)

        x_vals: list[float] = []
        thrusts: list[float] = []
        powers: list[float] = []
        currents: list[float] = []
        rpms: list[float] = []
        eta_tots: list[float] = []
        eta_props: list[float] = []
        eta_mots: list[float] = []
        sweep_rows: list[dict[str, Any]] = []

        t_vals = cls._arange(t_min, t_max, t_step)
        total_points = len(t_vals)
        for index, curr_t in enumerate(t_vals, start=1):
            if progress_callback:
                progress_callback(index, total_points, f"Throttle {curr_t:.0f}%")
            pt = cls.solve_point(
                motor_spec=motor_spec,
                prop_spec=prop_spec,
                prop_entry=prop_entry,
                total_voltage=total_voltage,
                rho=rho,
                v_mps=v_fixed,
                throttle_val=curr_t / 100.0,
                x_val=curr_t,
            )
            x_vals.append(curr_t)
            thrusts.append(pt.thrust)
            powers.append(pt.power)
            currents.append(pt.current)
            rpms.append(pt.rpm)
            eta_tots.append(pt.eta_sys)
            eta_props.append(pt.eta_p)
            eta_mots.append(pt.eta_m)
            sweep_rows.append(
                {
                    "x_val": curr_t,
                    "x_label": "Throttle (%)",
                    "rpm": pt.rpm,
                    "thrust": pt.thrust,
                    "power": pt.power,
                    "current": pt.current,
                    "eta_sys": pt.eta_sys,
                    "eta_p": pt.eta_p,
                    "eta_m": pt.eta_m,
                    "j": pt.j,
                    "feasible": pt.feasible,
                }
            )

        cruise_idx = len(x_vals) - 1
        cruise_power = max(powers[cruise_idx], 1e-3)
        batt_wh = total_voltage * capacity_mah / 1000.0
        endurance_min = (batt_wh * 0.8 / cruise_power) * 60.0

        return {
            "mode": "throttle_sweep",
            "x_label": "Throttle (%)",
            "x_values": x_vals,
            "thrust_n": thrusts,
            "power_w": powers,
            "current_a": currents,
            "rpm": rpms,
            "eta_total": eta_tots,
            "eta_prop": eta_props,
            "eta_motor": eta_mots,
            "static_thrust": thrusts[-1] if thrusts else 0.0,
            "peak_power": max(powers) if powers else 0.0,
            "peak_current": max(currents) if currents else 0.0,
            "max_rpm": max(rpms) if rpms else 0.0,
            "cruise_thrust": thrusts[cruise_idx] if thrusts else 0.0,
            "cruise_efficiency": eta_tots[cruise_idx] if eta_tots else 0.0,
            "endurance_min": endurance_min,
            "advance_ratio": (
                v_fixed / max((rpms[cruise_idx] / 60.0) * prop_spec.diameter_m, 1e-3)
            ),
            "prop_efficiency": eta_props[cruise_idx],
            "motor_efficiency": eta_mots[cruise_idx],
            "voltage_loaded": total_voltage - currents[cruise_idx] * 0.02,
            "sweep_table": sweep_rows,
            "motor_max_current": motor_spec.current_max_a,
            "clear_charts": False,
        }

    @classmethod
    def run_operating_point(
        cls,
        context: dict[str, Any],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        """Execute single operating point evaluation."""
        params = context["params"]
        motor_spec: MotorSpec = context["motor_spec"]
        prop_spec: PropellerSpec = context["prop_spec"]
        prop_entry: PropellerEntry = context["prop_entry"]
        total_voltage: float = context["total_voltage"]
        capacity_mah: float = context["capacity_mah"]
        rho: float = context["rho"]

        v_val = float(params.get("airspeed", 18.0))
        t_val = float(params.get("throttle", 75.0))
        if progress_callback:
            progress_callback(1, 1, f"Operating Point (V={v_val:.1f} m/s, T={t_val:.0f}%)")

        pt = cls.solve_point(
            motor_spec=motor_spec,
            prop_spec=prop_spec,
            prop_entry=prop_entry,
            total_voltage=total_voltage,
            rho=rho,
            v_mps=v_val,
            throttle_val=t_val / 100.0,
            x_val=v_val,
        )

        cruise_power = max(pt.power, 1e-3)
        batt_wh = total_voltage * capacity_mah / 1000.0
        endurance_min = (batt_wh * 0.8 / cruise_power) * 60.0

        sweep_rows = [
            {
                "x_val": v_val,
                "x_label": "Airspeed (m/s)",
                "rpm": pt.rpm,
                "thrust": pt.thrust,
                "power": pt.power,
                "current": pt.current,
                "eta_sys": pt.eta_sys,
                "eta_p": pt.eta_p,
                "eta_m": pt.eta_m,
                "j": pt.j,
                "feasible": pt.feasible,
            }
        ]

        return {
            "mode": "operating_point",
            "x_label": "Airspeed (m/s)",
            "x_values": [v_val],
            "thrust_n": [pt.thrust],
            "power_w": [pt.power],
            "current_a": [pt.current],
            "rpm": [pt.rpm],
            "eta_total": [pt.eta_sys],
            "eta_prop": [pt.eta_p],
            "eta_motor": [pt.eta_m],
            "static_thrust": pt.thrust,
            "peak_power": pt.power,
            "peak_current": pt.current,
            "max_rpm": pt.rpm,
            "cruise_thrust": pt.thrust,
            "cruise_efficiency": pt.eta_sys,
            "endurance_min": endurance_min,
            "advance_ratio": pt.j,
            "prop_efficiency": pt.eta_p,
            "motor_efficiency": pt.eta_m,
            "voltage_loaded": total_voltage - pt.current * 0.02,
            "sweep_table": sweep_rows,
            "motor_max_current": motor_spec.current_max_a,
            "clear_charts": True,
        }

    @classmethod
    def run_analysis(
        cls,
        context: dict[str, Any],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        """Execute propulsion analysis for given context."""
        mode = context.get("mode", "airspeed_sweep")
        if mode == "airspeed_sweep":
            return cls.run_airspeed_sweep(context, progress_callback=progress_callback)
        elif mode == "throttle_sweep":
            return cls.run_throttle_sweep(context, progress_callback=progress_callback)
        elif mode == "operating_point":
            return cls.run_operating_point(context, progress_callback=progress_callback)
        else:
            raise ValueError(f"Unknown propulsion analysis mode: {mode}")
