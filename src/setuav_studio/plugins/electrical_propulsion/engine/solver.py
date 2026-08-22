import logging
import math

from scipy.optimize import root_scalar

from pythrust.propellers.database import PropellerDataPoint, PropellerEntry, PropellerMetadata
from pythrust.propulsion.models.motor import MotorSpec
from pythrust.propulsion.models.propeller import PropellerSpec
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
