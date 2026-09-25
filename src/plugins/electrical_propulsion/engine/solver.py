"""Analytical solver engine for electrical propulsion system equilibrium using PyThrust."""

from __future__ import annotations

import logging

from pythrust.propellers.database import PropellerEntry
from pythrust.propulsion.models import BatterySpec, MotorSpec, PropellerSpec, SystemSpec
from pythrust.propulsion.solver import PropulsionSolver

from .base import PropulsionPoint

logger = logging.getLogger(__name__)


class PropulsionSolverEngine:
    """Analytical engine delegating electrical propulsion equilibrium solving to PyThrust."""

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
