"""Analytical solver engine for electrical propulsion system equilibrium using PyThrust."""

from __future__ import annotations

import logging

from pythrust.propellers.database import (
    PropellerDataPoint,
    PropellerEntry,
    PropellerMetadata,
)
from pythrust.propulsion.models import BatterySpec, MotorSpec, PropellerSpec, SystemSpec
from pythrust.propulsion.solver import PropulsionSolver

from .base import PropulsionPoint

logger = logging.getLogger(__name__)


class PropulsionSolverEngine:
    """Analytical engine delegating electrical propulsion equilibrium solving to PyThrust."""

    @staticmethod
    def synthetic_propeller(diameter_in: float, pitch_in: float, blades: int = 2) -> PropellerEntry:
        """Construct a synthetic analytical propeller polar for sizes without catalog data."""
        prop_meta = PropellerMetadata(
            id=f"prop_{diameter_in:.1f}x{pitch_in:.1f}",
            manufacturer="Synthetic",
            model=f"{diameter_in:.1f}x{pitch_in:.1f}",
            diameter_in=diameter_in,
            pitch_in=pitch_in,
            blade_count=blades,
            data_csv="",
        )
        prop_data: dict[float, list[PropellerDataPoint]] = {}
        p_d = pitch_in / max(diameter_in, 1e-3)
        j_max = p_d * 1.15
        for r in [2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 12000, 15000]:
            pts: list[PropellerDataPoint] = []
            for j_i in range(30):
                j_val = j_i * (j_max / 29.0)
                ct_val = max(0.12 - 0.10 * (j_val / max(p_d, 0.1)), 0.0)
                cp_val = max(0.06 - 0.03 * (j_val / max(p_d, 0.1)), 0.005)
                pts.append(PropellerDataPoint(j=j_val, ct=ct_val, cp=cp_val))
            prop_data[float(r)] = pts
        return PropellerEntry(metadata=prop_meta, data_by_rpm=prop_data)

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
        """Solve equilibrium operating point using PyThrust PropulsionSolver."""
        battery_spec = BatterySpec(voltage_v=max(total_voltage, 0.1), discharge_efficiency=0.98)
        system_spec = SystemSpec(resistance_ohm=0.005)
        solver = PropulsionSolver()

        op = solver.solve_operating_point(
            motor=motor_spec,
            battery=battery_spec,
            system=system_spec,
            propeller=prop_spec,
            prop_entry=prop_entry,
            rho=rho,
            airspeed_mps=v_mps,
            throttle=max(0.0, min(1.0, throttle_val)),
            battery_state=None,
        )

        return PropulsionPoint(
            x_val=x_val,
            rpm=op.rpm,
            thrust=max(op.thrust_n, 0.0),
            power=max(op.battery_power_w, 0.0),
            current=max(op.battery_current_a, 0.0),
            eta_p=min(max(op.propeller_efficiency, 0.0), 1.0),
            eta_m=min(max(op.motor_efficiency, 0.0), 1.0),
            eta_sys=min(max(op.system_efficiency, 0.0), 1.0),
            j=max(op.advance_ratio, 0.0),
            feasible=op.is_feasible,
        )
