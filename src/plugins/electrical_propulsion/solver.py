"""Electrical Propulsion Analysis Solvers integrating PyThrust with Core Studio Solver Architecture."""

from __future__ import annotations

import logging
import math
from typing import Any, ClassVar

from plugins.electrical_propulsion.powertrain import (
    Powertrain,
    PowertrainError,
    PowertrainPoint,
    build_powertrain,
    find_propulsion_system,
)
from setuav_studio.api import ParameterField
from setuav_studio.solver.base import AbstractSolver, SolverConfig, SolverStatus
from setuav_studio.solver.results import (
    PlotDefinition,
    PlotSeriesDef,
    SolverResult,
    SummaryItem,
    TableColumn,
    TableDefinition,
)
from setuav_studio.task.types import TaskCancelledError

logger = logging.getLogger(__name__)

SOLVER_ID_THROTTLE_SWEEP = "org.setuav.propulsion.throttle_sweep"
SOLVER_ID_AIRSPEED_SWEEP = "org.setuav.propulsion.airspeed_sweep"
SOLVER_ID_OPERATING_POINT = "org.setuav.propulsion.operating_point"


def _compute_air_density(altitude_m: float, temperature_c: float) -> float:
    """Compute atmospheric air density using ISA model."""
    t_kelvin = 273.15 + temperature_c
    if altitude_m <= 11000.0:
        p_pa = 101325.0 * (1.0 - 0.0065 * altitude_m / 288.15) ** 5.25588
    else:
        p_11k = 101325.0 * (1.0 - 0.0065 * 11000.0 / 288.15) ** 5.25588
        p_pa = p_11k * math.exp(-9.80665 * 0.0289644 * (altitude_m - 11000.0) / (8.31432 * 216.65))
    return p_pa / (287.058 * t_kelvin)


class BasePropulsionSolver(AbstractSolver):
    """Base class for electrical propulsion solvers resolving project powertrain entities."""

    def __init__(self, config: SolverConfig, project: Any | None = None) -> None:
        super().__init__(config, project)

    def _powertrain(self) -> Powertrain:
        project = self.project
        if project is None and self.api is not None:
            project = self.api.project
        if project is None:
            raise RuntimeError("No active project available for propulsion analysis.")
        components = [c for c in project.data.get("components", []) if isinstance(c, dict)]
        members = find_propulsion_system(components)
        if members is None:
            raise PowertrainError("Propulsion analysis requires an electrical propulsion system.")
        return build_powertrain(members)

    def _build_result(
        self,
        plot_x_col: str,
        plot_x_label: str,
        points_data: list[tuple[float, PowertrainPoint]],
        powertrain: Powertrain,
    ) -> SolverResult:
        x_vals = [p[0] for p in points_data]
        rpms = [round(p[1].rpm, 1) for p in points_data]
        thrusts = [round(p[1].thrust_n, 3) for p in points_data]
        powers = [round(p[1].battery_power_w, 2) for p in points_data]
        currents = [round(p[1].battery_current_a, 2) for p in points_data]
        voltages = [round(p[1].battery_voltage_v, 2) for p in points_data]
        advance_ratios = [round(p[1].advance_ratio, 3) for p in points_data]
        sys_effs = [round(p[1].system_efficiency, 4) for p in points_data]
        prop_effs = [round(p[1].propeller_efficiency, 4) for p in points_data]
        motor_effs = [round(p[1].motor_efficiency, 4) for p in points_data]
        feasibles = [p[1].feasible for p in points_data]

        table_columns = [
            TableColumn(
                key=plot_x_col,
                label=plot_x_label,
                unit="%" if plot_x_col == "throttle" else "m/s",
                quantity_id=None if plot_x_col == "throttle" else "velocity",
            ),
            TableColumn(key="rpm", label="RPM", unit="RPM", quantity_id="frequency"),
            TableColumn(key="thrust", label="Thrust", unit="N", quantity_id="force"),
            TableColumn(key="power", label="Electrical Power", unit="W", quantity_id="power"),
            TableColumn(key="current", label="Current", unit="A", quantity_id="current"),
            TableColumn(key="voltage", label="Battery Voltage", unit="V", quantity_id="voltage"),
            TableColumn(key="advance_ratio", label="Advance Ratio (J)", unit=""),
            TableColumn(key="sys_efficiency", label="System Efficiency", unit=""),
            TableColumn(key="prop_efficiency", label="Propeller Efficiency", unit=""),
            TableColumn(key="motor_efficiency", label="Motor Efficiency", unit=""),
            TableColumn(key="feasible", label="Feasible", unit=""),
        ]

        table_data: dict[str, list[Any]] = {
            plot_x_col: x_vals,
            "rpm": rpms,
            "thrust": thrusts,
            "power": powers,
            "current": currents,
            "voltage": voltages,
            "advance_ratio": advance_ratios,
            "sys_efficiency": sys_effs,
            "prop_efficiency": prop_effs,
            "motor_efficiency": motor_effs,
            "feasible": feasibles,
        }
        dataset_table = TableDefinition(
            id="propulsion_data",
            title="Propulsion Performance Data",
            columns=table_columns,
            data=table_data,
        )

        plots: dict[str, PlotDefinition] = {
            "plot_thrust": PlotDefinition(
                id="plot_thrust",
                title="Thrust Force",
                table_id="propulsion_data",
                x_column=plot_x_col,
                x_label=plot_x_label,
                y_label="Thrust (N)",
                series=[PlotSeriesDef(y_column="thrust", label="Thrust Force", color="#2563eb")],
            ),
            "plot_power_current": PlotDefinition(
                id="plot_power_current",
                title="Power & Current",
                table_id="propulsion_data",
                x_column=plot_x_col,
                x_label=plot_x_label,
                y_label="Power (W) / Current (A)",
                series=[
                    PlotSeriesDef(y_column="power", label="Battery Power (W)", color="#dc2626"),
                    PlotSeriesDef(y_column="current", label="Battery Current (A)", color="#ea580c"),
                ],
            ),
            "plot_rpm": PlotDefinition(
                id="plot_rpm",
                title="Rotational Speed (RPM)",
                table_id="propulsion_data",
                x_column=plot_x_col,
                x_label=plot_x_label,
                y_label="Motor RPM",
                series=[PlotSeriesDef(y_column="rpm", label="Equilibrium RPM", color="#16a34a")],
            ),
            "plot_efficiency": PlotDefinition(
                id="plot_efficiency",
                title="System & Component Efficiency",
                table_id="propulsion_data",
                x_column=plot_x_col,
                x_label=plot_x_label,
                y_label="Efficiency (-)",
                series=[
                    PlotSeriesDef(
                        y_column="sys_efficiency", label="System Efficiency", color="#8b5cf6"
                    ),
                    PlotSeriesDef(
                        y_column="prop_efficiency", label="Propeller Efficiency", color="#06b6d4"
                    ),
                    PlotSeriesDef(
                        y_column="motor_efficiency", label="Motor Efficiency", color="#f59e0b"
                    ),
                ],
            ),
        }

        nominal_idx = min(len(x_vals) - 1, max(0, int(len(x_vals) * 0.5)))
        cruise_power = max(powers[nominal_idx] if powers else 0.0, 1.0)
        battery_energy_wh = (powertrain.battery.voltage_v * powertrain.capacity_mah) / 1000.0
        est_endurance_min = (battery_energy_wh * 0.8 / cruise_power) * 60.0

        summary: dict[str, SummaryItem] = {
            "static_thrust": SummaryItem(
                key="static_thrust",
                value=thrusts[0] if thrusts else 0.0,
                label="Static Thrust",
                unit="N",
                quantity_id="force",
            ),
            "peak_power": SummaryItem(
                key="peak_power",
                value=max(powers) if powers else 0.0,
                label="Peak Power",
                unit="W",
                quantity_id="power",
            ),
            "peak_current": SummaryItem(
                key="peak_current",
                value=max(currents) if currents else 0.0,
                label="Peak Current",
                unit="A",
                quantity_id="current",
            ),
            "max_rpm": SummaryItem(
                key="max_rpm",
                value=max(rpms) if rpms else 0.0,
                label="Max RPM",
                unit="RPM",
                quantity_id="frequency",
            ),
            "cruise_thrust": SummaryItem(
                key="cruise_thrust",
                value=thrusts[nominal_idx] if thrusts else 0.0,
                label="Cruise Thrust",
                unit="N",
                quantity_id="force",
            ),
            "cruise_efficiency": SummaryItem(
                key="cruise_efficiency",
                value=sys_effs[nominal_idx] if sys_effs else 0.0,
                label="Cruise Efficiency",
                unit="",
            ),
            "estimated_endurance": SummaryItem(
                key="estimated_endurance",
                value=round(est_endurance_min, 1),
                label="Estimated Endurance (80% DoD)",
                unit="min",
            ),
        }

        return SolverResult(
            solver_id=self.config.solver_id,
            config=self.config,
            name=self.config.name,
            status=SolverStatus.COMPLETED,
            summary=summary,
            tables={"propulsion_data": dataset_table},
            plots=plots,
        )


class ThrottleSweepSolver(BasePropulsionSolver):
    """Evaluates propulsion performance across a range of throttle settings at a constant airspeed."""

    PARAMETER_FIELDS: ClassVar[list[ParameterField]] = [
        ParameterField(
            key="airspeed",
            label="Airspeed",
            unit="m/s",
            quantity="velocity",
            field_type=float,
            default=15.0,
            min_value=0.0,
            max_value=200.0,
            decimals=1,
            tooltip="Constant flight airspeed for throttle sweep.",
        ),
        ParameterField(
            key="t_min",
            label="Throttle Min",
            unit="%",
            field_type=float,
            default=10.0,
            min_value=1.0,
            max_value=100.0,
            decimals=0,
            tooltip="Starting throttle percentage.",
        ),
        ParameterField(
            key="t_max",
            label="Throttle Max",
            unit="%",
            field_type=float,
            default=100.0,
            min_value=1.0,
            max_value=100.0,
            decimals=0,
            tooltip="Ending throttle percentage.",
        ),
        ParameterField(
            key="t_step",
            label="Throttle Step",
            unit="%",
            field_type=float,
            default=5.0,
            min_value=1.0,
            max_value=50.0,
            decimals=0,
            tooltip="Throttle evaluation increment.",
        ),
        ParameterField(
            key="altitude",
            label="Altitude",
            unit="m",
            quantity="length",
            field_type=float,
            default=0.0,
            min_value=-500.0,
            max_value=25000.0,
            decimals=0,
            tooltip="Atmospheric flight altitude.",
        ),
        ParameterField(
            key="temperature",
            label="Temperature",
            unit="°C",
            field_type=float,
            default=15.0,
            min_value=-50.0,
            max_value=60.0,
            decimals=1,
            tooltip="Ambient air temperature.",
        ),
    ]

    def run(self) -> SolverResult:
        if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
            self.status = SolverStatus.CANCELLED
            raise TaskCancelledError("Analysis cancelled before execution.")

        powertrain = self._powertrain()

        altitude_m = float(self.config.parameters.get("altitude", 0.0))
        temperature_c = float(self.config.parameters.get("temperature", 15.0))
        rho = _compute_air_density(altitude_m, temperature_c)

        v_fixed = max(0.0, float(self.config.parameters.get("airspeed", 15.0)))
        t_min = max(1.0, float(self.config.parameters.get("t_min", 10.0)))
        t_max = min(100.0, float(self.config.parameters.get("t_max", 100.0)))
        t_step = max(1.0, float(self.config.parameters.get("t_step", 5.0)))

        t_list: list[float] = []
        curr_t = t_min
        while curr_t <= t_max + 1e-4:
            t_list.append(round(curr_t, 1))
            curr_t += t_step

        total_points = len(t_list)
        points_data: list[tuple[float, PowertrainPoint]] = []

        for idx, t_val in enumerate(t_list):
            if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
                self.status = SolverStatus.CANCELLED
                raise TaskCancelledError("Analysis cancelled during sweep.")

            if self.token is not None:
                pct = int((idx + 1) / total_points * 100)
                self.token.report_progress(
                    idx + 1, total_points, f"Throttle Sweep {t_val:.0f}% ({pct}%)"
                )

            op = powertrain.solve(rho=rho, airspeed_mps=v_fixed, throttle=t_val / 100.0)
            points_data.append((t_val, op))

        return self._build_result(
            plot_x_col="throttle",
            plot_x_label="Throttle",
            points_data=points_data,
            powertrain=powertrain,
        )


class AirspeedSweepSolver(BasePropulsionSolver):
    """Evaluates propulsion performance across an airspeed range at a constant throttle setting."""

    PARAMETER_FIELDS: ClassVar[list[ParameterField]] = [
        ParameterField(
            key="v_min",
            label="Airspeed Min",
            unit="m/s",
            quantity="velocity",
            field_type=float,
            default=0.0,
            min_value=0.0,
            max_value=200.0,
            decimals=1,
            tooltip="Starting flight airspeed.",
        ),
        ParameterField(
            key="v_max",
            label="Airspeed Max",
            unit="m/s",
            quantity="velocity",
            field_type=float,
            default=35.0,
            min_value=0.5,
            max_value=200.0,
            decimals=1,
            tooltip="Ending flight airspeed.",
        ),
        ParameterField(
            key="v_step",
            label="Airspeed Step",
            unit="m/s",
            quantity="velocity",
            field_type=float,
            default=1.0,
            min_value=0.1,
            max_value=20.0,
            decimals=1,
            tooltip="Airspeed evaluation step.",
        ),
        ParameterField(
            key="throttle",
            label="Throttle",
            unit="%",
            field_type=float,
            default=100.0,
            min_value=1.0,
            max_value=100.0,
            decimals=0,
            tooltip="Constant throttle percentage during airspeed sweep.",
        ),
        ParameterField(
            key="altitude",
            label="Altitude",
            unit="m",
            quantity="length",
            field_type=float,
            default=0.0,
            min_value=-500.0,
            max_value=25000.0,
            decimals=0,
            tooltip="Atmospheric flight altitude.",
        ),
        ParameterField(
            key="temperature",
            label="Temperature",
            unit="°C",
            field_type=float,
            default=15.0,
            min_value=-50.0,
            max_value=60.0,
            decimals=1,
            tooltip="Ambient air temperature.",
        ),
    ]

    def run(self) -> SolverResult:
        if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
            self.status = SolverStatus.CANCELLED
            raise TaskCancelledError("Analysis cancelled before execution.")

        powertrain = self._powertrain()

        altitude_m = float(self.config.parameters.get("altitude", 0.0))
        temperature_c = float(self.config.parameters.get("temperature", 15.0))
        rho = _compute_air_density(altitude_m, temperature_c)

        v_min = float(self.config.parameters.get("v_min", 0.0))
        v_max = float(self.config.parameters.get("v_max", 35.0))
        v_step = max(0.5, float(self.config.parameters.get("v_step", 1.0)))
        throttle_pct = max(1.0, min(100.0, float(self.config.parameters.get("throttle", 100.0))))
        throttle = throttle_pct / 100.0

        v_list: list[float] = []
        curr_v = v_min
        while curr_v <= v_max + 1e-4:
            v_list.append(round(curr_v, 2))
            curr_v += v_step

        total_points = len(v_list)
        points_data: list[tuple[float, PowertrainPoint]] = []

        for idx, v_val in enumerate(v_list):
            if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
                self.status = SolverStatus.CANCELLED
                raise TaskCancelledError("Analysis cancelled during sweep.")

            if self.token is not None:
                pct = int((idx + 1) / total_points * 100)
                self.token.report_progress(
                    idx + 1, total_points, f"Airspeed Sweep {v_val:.1f} m/s ({pct}%)"
                )

            op = powertrain.solve(rho=rho, airspeed_mps=v_val, throttle=throttle)
            points_data.append((v_val, op))

        return self._build_result(
            plot_x_col="airspeed",
            plot_x_label="Airspeed",
            points_data=points_data,
            powertrain=powertrain,
        )


class OperatingPointSolver(BasePropulsionSolver):
    """Evaluates propulsion performance at a single discrete operating airspeed and throttle."""

    PARAMETER_FIELDS: ClassVar[list[ParameterField]] = [
        ParameterField(
            key="airspeed",
            label="Airspeed",
            unit="m/s",
            quantity="velocity",
            field_type=float,
            default=18.0,
            min_value=0.0,
            max_value=200.0,
            decimals=1,
            tooltip="Flight airspeed.",
        ),
        ParameterField(
            key="throttle",
            label="Throttle",
            unit="%",
            field_type=float,
            default=75.0,
            min_value=1.0,
            max_value=100.0,
            decimals=0,
            tooltip="Throttle setting percentage.",
        ),
        ParameterField(
            key="altitude",
            label="Altitude",
            unit="m",
            quantity="length",
            field_type=float,
            default=0.0,
            min_value=-500.0,
            max_value=25000.0,
            decimals=0,
            tooltip="Atmospheric flight altitude.",
        ),
        ParameterField(
            key="temperature",
            label="Temperature",
            unit="°C",
            field_type=float,
            default=15.0,
            min_value=-50.0,
            max_value=60.0,
            decimals=1,
            tooltip="Ambient air temperature.",
        ),
    ]

    def run(self) -> SolverResult:
        if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
            self.status = SolverStatus.CANCELLED
            raise TaskCancelledError("Analysis cancelled before execution.")

        powertrain = self._powertrain()

        altitude_m = float(self.config.parameters.get("altitude", 0.0))
        temperature_c = float(self.config.parameters.get("temperature", 15.0))
        rho = _compute_air_density(altitude_m, temperature_c)

        v_val = max(0.0, float(self.config.parameters.get("airspeed", 18.0)))
        t_pct = max(1.0, min(100.0, float(self.config.parameters.get("throttle", 75.0))))

        if self.token is not None:
            self.token.report_progress(1, 1, f"Operating Point (V={v_val:.1f} m/s)")

        op = powertrain.solve(rho=rho, airspeed_mps=v_val, throttle=t_pct / 100.0)

        return self._build_result(
            plot_x_col="airspeed",
            plot_x_label="Airspeed",
            points_data=[(v_val, op)],
            powertrain=powertrain,
        )
