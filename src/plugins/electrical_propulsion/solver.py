"""Electrical Propulsion Analysis Solvers integrating PyThrust with Core Studio Solver Architecture."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from plugins.electrical_propulsion.powertrain import (
    Powertrain,
    PowertrainError,
    PowertrainPoint,
    build_powertrain,
    find_powertrain_members,
)
from setuav_studio.api import ParameterField
from setuav_studio.model.atmosphere import Atmosphere
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

_ENDURANCE_FINAL_SOC = 0.2


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
        components = [c for c in project.data["components"] if isinstance(c, dict)]
        members = find_powertrain_members(components)
        if members is None:
            raise PowertrainError("Propulsion analysis requires propulsors and a battery.")
        return build_powertrain(
            members,
            state_of_charge=float(self.config.parameters["state_of_charge"]) / 100.0,
        )

    def _parameter(self, key: str) -> float:
        return float(self.config.parameters[key])

    def _air_density(self) -> float:
        return Atmosphere.at_temperature(
            self._parameter("altitude"), self._parameter("temperature")
        ).density_kg_m3

    def _airspeed(self, key: str) -> float:
        airspeed = self._parameter(key)
        if airspeed < 0.0:
            raise ValueError(f"The airspeed ({airspeed:g} m/s) must not be negative.")
        return airspeed

    def _throttle_pct(self, key: str) -> float:
        throttle = self._parameter(key)
        if not 0.0 < throttle <= 100.0:
            raise ValueError(f"The throttle ({throttle:g} %) must be above 0 % and at most 100 %.")
        return throttle

    def _sweep(self, low: float, high: float, step: float, name: str) -> list[float]:
        """Return the points from ``low`` to ``high`` in ``step`` increments."""
        if step <= 0.0:
            raise ValueError(f"The {name} step must be positive.")
        if high < low:
            raise ValueError(f"The {name} maximum ({high:g}) is below its minimum ({low:g}).")
        count = int((high - low) / step + 1e-6) + 1
        return [round(low + k * step, 6) for k in range(count)]

    @staticmethod
    def _feasible_summary(
        feasible: list[int],
        points_data: list[tuple[float, PowertrainPoint]],
        *,
        plot_x_col: str,
        plot_x_label: str,
        endurances: list[float],
    ) -> dict[str, SummaryItem]:
        """Summary metrics over the points within the current limits."""
        points = [point for _, point in points_data]
        strongest = max(feasible, key=lambda i: points[i].thrust_n)
        most_efficient = max(feasible, key=lambda i: points[i].system_efficiency)
        summary = {
            "max_thrust": SummaryItem(
                key="max_thrust",
                value=round(points[strongest].thrust_n, 3),
                label="Max Thrust",
                unit="N",
                quantity_id="force",
            ),
            "peak_power": SummaryItem(
                key="peak_power",
                value=round(max(points[i].battery_power_w for i in feasible), 2),
                label="Peak Power",
                unit="W",
                quantity_id="power",
            ),
            "peak_current": SummaryItem(
                key="peak_current",
                value=round(max(points[i].battery_current_a for i in feasible), 2),
                label="Peak Current",
                unit="A",
                quantity_id="current",
            ),
            "max_rpm": SummaryItem(
                key="max_rpm",
                value=round(max(points[i].rpm for i in feasible), 1),
                label="Max RPM",
                unit="RPM",
                quantity_id="frequency",
            ),
            "best_efficiency": SummaryItem(
                key="best_efficiency",
                value=round(points[most_efficient].system_efficiency, 4),
                label="Best System Efficiency",
                unit="",
            ),
            "best_efficiency_at": SummaryItem(
                key="best_efficiency_at",
                value=points_data[most_efficient][0],
                label=f"Best Efficiency {plot_x_label}",
                unit="%" if plot_x_col == "throttle" else "m/s",
                quantity_id=None if plot_x_col == "throttle" else "velocity",
            ),
        }
        static = [i for i in feasible if points[i].advance_ratio == 0.0]
        if static:
            summary["static_thrust"] = SummaryItem(
                key="static_thrust",
                value=round(max(points[i].thrust_n for i in static), 3),
                label="Static Thrust",
                unit="N",
                quantity_id="force",
            )
        if endurances and len(points) == 1:
            summary["endurance"] = SummaryItem(
                key="endurance",
                value=endurances[0],
                label=f"Endurance to {_ENDURANCE_FINAL_SOC:.0%} SoC",
                unit="min",
            )
        return summary

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
        feasible = [i for i, ok in enumerate(feasibles) if ok]
        has_reserve = powertrain.state_of_charge > _ENDURANCE_FINAL_SOC
        endurances = (
            [
                round(
                    powertrain.discharge_time_s(
                        power_w=point.battery_power_w, final_soc=_ENDURANCE_FINAL_SOC
                    )
                    / 60.0,
                    2,
                )
                for _, point in points_data
            ]
            if has_reserve
            else []
        )

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
        if has_reserve:
            table_columns.append(
                TableColumn(
                    key="endurance",
                    label=f"Endurance to {_ENDURANCE_FINAL_SOC:.0%} SoC",
                    unit="min",
                    quantity_id=None,
                )
            )

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
        if has_reserve:
            table_data["endurance"] = endurances
        dataset_table = TableDefinition(
            id="propulsion_data",
            title="Performance",
            columns=table_columns,
            data=table_data,
        )

        plots: dict[str, PlotDefinition] = {
            "plot_thrust": PlotDefinition(
                id="plot_thrust",
                title="Thrust",
                table_id="propulsion_data",
                x_column=plot_x_col,
                x_label=plot_x_label,
                y_label="Thrust (N)",
                series=[PlotSeriesDef(y_column="thrust", label="Thrust Force", color="#2563eb")],
                valid_column="feasible",
            ),
            "plot_power_current": PlotDefinition(
                id="plot_power_current",
                title="Power & Current",
                table_id="propulsion_data",
                x_column=plot_x_col,
                x_label=plot_x_label,
                series=[
                    PlotSeriesDef(y_column="power", label="Battery Power", color="#dc2626"),
                    PlotSeriesDef(
                        y_column="current",
                        label="Battery Current",
                        style="dashed",
                        color="#ea580c",
                        axis="right",
                    ),
                ],
                valid_column="feasible",
            ),
            "plot_rpm": PlotDefinition(
                id="plot_rpm",
                title="RPM",
                table_id="propulsion_data",
                x_column=plot_x_col,
                x_label=plot_x_label,
                y_label="Motor RPM",
                series=[PlotSeriesDef(y_column="rpm", label="Equilibrium RPM", color="#16a34a")],
                valid_column="feasible",
            ),
            "plot_efficiency": PlotDefinition(
                id="plot_efficiency",
                title="Efficiency",
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
                valid_column="feasible",
            ),
        }

        summary: dict[str, SummaryItem] = {
            "feasible_points": SummaryItem(
                key="feasible_points",
                value=len(feasible),
                label=f"Feasible Points (of {len(points_data)})",
                unit="",
            ),
        }
        if feasible:
            summary.update(
                self._feasible_summary(
                    feasible,
                    points_data,
                    plot_x_col=plot_x_col,
                    plot_x_label=plot_x_label,
                    endurances=endurances,
                )
            )

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
            quantity="altitude",
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
        ParameterField(
            key="state_of_charge",
            label="Battery State of Charge",
            unit="%",
            field_type=float,
            default=100.0,
            min_value=1.0,
            max_value=100.0,
            decimals=0,
            tooltip="Battery state of charge the pack is evaluated at.",
        ),
    ]

    def run(self) -> SolverResult:
        if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
            self.status = SolverStatus.CANCELLED
            raise TaskCancelledError("Analysis cancelled before execution.")

        powertrain = self._powertrain()

        rho = self._air_density()
        v_fixed = self._airspeed("airspeed")
        t_list = self._sweep(
            self._throttle_pct("t_min"),
            self._throttle_pct("t_max"),
            self._parameter("t_step"),
            "throttle",
        )

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
            quantity="altitude",
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
        ParameterField(
            key="state_of_charge",
            label="Battery State of Charge",
            unit="%",
            field_type=float,
            default=100.0,
            min_value=1.0,
            max_value=100.0,
            decimals=0,
            tooltip="Battery state of charge the pack is evaluated at.",
        ),
    ]

    def run(self) -> SolverResult:
        if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
            self.status = SolverStatus.CANCELLED
            raise TaskCancelledError("Analysis cancelled before execution.")

        powertrain = self._powertrain()

        rho = self._air_density()
        throttle = self._throttle_pct("throttle") / 100.0
        v_list = self._sweep(
            self._airspeed("v_min"),
            self._airspeed("v_max"),
            self._parameter("v_step"),
            "airspeed",
        )

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
            quantity="altitude",
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
        ParameterField(
            key="state_of_charge",
            label="Battery State of Charge",
            unit="%",
            field_type=float,
            default=100.0,
            min_value=1.0,
            max_value=100.0,
            decimals=0,
            tooltip="Battery state of charge the pack is evaluated at.",
        ),
    ]

    def run(self) -> SolverResult:
        if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
            self.status = SolverStatus.CANCELLED
            raise TaskCancelledError("Analysis cancelled before execution.")

        powertrain = self._powertrain()

        rho = self._air_density()
        v_val = self._airspeed("airspeed")
        t_pct = self._throttle_pct("throttle")

        if self.token is not None:
            self.token.report_progress(1, 1, f"Operating Point (V={v_val:.1f} m/s)")

        op = powertrain.solve(rho=rho, airspeed_mps=v_val, throttle=t_pct / 100.0)

        return self._build_result(
            plot_x_col="airspeed",
            plot_x_label="Airspeed",
            points_data=[(v_val, op)],
            powertrain=powertrain,
        )
