"""Flight performance solver coupling aircraft mass, aerodynamics and the electric powertrain."""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from plugins.electrical_propulsion.powertrain import (
    Powertrain,
    build_powertrain,
    find_powertrain_members,
)
from setuav_studio.api import ParameterField
from setuav_studio.model.atmosphere import Atmosphere
from setuav_studio.solver.base import AbstractSolver, SolverStatus
from setuav_studio.solver.results import (
    PlotDefinition,
    PlotSeriesDef,
    SolverResult,
    SummaryItem,
    TableColumn,
    TableDefinition,
)
from setuav_studio.task.types import TaskCancelledError

from .engine.aerodynamics import aerobuildup_model
from .engine.performance import (
    AerodynamicModel,
    PerformanceEnvelope,
    PropulsionSweep,
    level_flight_envelope,
    max_level_speed,
    stall_speed,
    velocity_sweep,
)

SOLVER_ID_FLIGHT_PERFORMANCE = "org.setuav.flight_performance.level_flight"

_TABLE_ID = "level_flight"


class FlightPerformanceSolver(AbstractSolver):
    """Steady level-flight envelope: speeds, climb, range and endurance."""

    PARAMETER_FIELDS: ClassVar[list[ParameterField]] = [
        ParameterField(
            key="payload",
            label="Payload",
            unit="g",
            quantity="mass",
            field_type=float,
            default=0.0,
            min_value=0.0,
            max_value=100000.0,
            step=10.0,
            decimals=1,
            tooltip="Mass carried in addition to the aircraft's component masses.",
        ),
        ParameterField(
            key="altitude",
            label="Altitude",
            unit="m",
            quantity="length",
            field_type=float,
            default=0.0,
            min_value=-500.0,
            max_value=15000.0,
            decimals=0,
            tooltip="Flight altitude.",
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
            key="v_min",
            label="Min Speed",
            unit="m/s",
            quantity="velocity",
            field_type=float,
            default=8.0,
            min_value=1.0,
            max_value=100.0,
            decimals=1,
            tooltip="Lowest swept airspeed; the sweep never starts below the stall margin.",
        ),
        ParameterField(
            key="v_max",
            label="Max Speed",
            unit="m/s",
            quantity="velocity",
            field_type=float,
            default=35.0,
            min_value=5.0,
            max_value=200.0,
            decimals=1,
            tooltip="Highest swept airspeed.",
        ),
        ParameterField(
            key="v_step",
            label="Speed Step",
            unit="m/s",
            quantity="velocity",
            field_type=float,
            default=0.25,
            min_value=0.05,
            max_value=5.0,
            step=0.05,
            decimals=2,
            tooltip="Airspeed increment of the sweep.",
        ),
        ParameterField(
            key="stall_margin",
            label="Stall Margin",
            unit="×",
            field_type=float,
            default=1.15,
            min_value=1.0,
            max_value=2.0,
            step=0.05,
            decimals=2,
            tooltip="Lowest swept airspeed as a multiple of the stall speed.",
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
            tooltip="State of charge at the start of the flight.",
        ),
        ParameterField(
            key="reserve_soc",
            label="Landing Reserve",
            unit="%",
            field_type=float,
            default=20.0,
            min_value=0.0,
            max_value=99.0,
            decimals=0,
            tooltip="State of charge left at the end of the endurance and range flights.",
        ),
        ParameterField(
            key="polar_velocity",
            label="Polar Airspeed",
            unit="m/s",
            quantity="velocity",
            field_type=float,
            default=15.0,
            min_value=1.0,
            max_value=200.0,
            decimals=1,
            tooltip="Airspeed of the AeroBuildup polar (sets its Reynolds numbers).",
        ),
        ParameterField(
            key="alpha_min",
            label="Polar AoA Min",
            unit="°",
            quantity="angle",
            field_type=float,
            default=-8.0,
            min_value=-30.0,
            max_value=30.0,
            decimals=1,
            tooltip="Starting angle of attack of the polar.",
        ),
        ParameterField(
            key="alpha_max",
            label="Polar AoA Max",
            unit="°",
            quantity="angle",
            field_type=float,
            default=25.0,
            min_value=0.0,
            max_value=45.0,
            decimals=1,
            tooltip="Ending angle of attack of the polar; it must reach stall.",
        ),
        ParameterField(
            key="alpha_step",
            label="Polar AoA Step",
            unit="°",
            quantity="angle",
            field_type=float,
            default=0.5,
            min_value=0.1,
            max_value=5.0,
            decimals=1,
            tooltip="Angle of attack increment of the polar.",
        ),
    ]

    def run(self) -> SolverResult:
        self._check_cancelled()
        project = self.project
        if project is None and self.api is not None:
            project = self.api.project
        if project is None:
            raise RuntimeError("No active project available for flight performance analysis.")
        params = self.config.parameters
        components = [c for c in project.data["components"] if isinstance(c, dict)]

        mass_kg = project.mass_properties.mass_kg + float(params["payload"]) / 1000.0
        if mass_kg <= 0.0:
            raise ValueError("Flight performance needs the aircraft mass; define component masses.")
        rho = Atmosphere.at_temperature(
            float(params["altitude"]), float(params["temperature"])
        ).density_kg_m3

        self._report(0, "Aerodynamic polar")
        aero = aerobuildup_model(
            components,
            velocity=float(params["polar_velocity"]),
            altitude=float(params["altitude"]),
            alpha_min=float(params["alpha_min"]),
            alpha_max=float(params["alpha_max"]),
            alpha_step=float(params["alpha_step"]),
            progress_callback=lambda current, total, _message: self._report(
                int(40 * current / max(total, 1)), "Aerodynamic polar"
            ),
        )
        powertrain = self._powertrain(components)
        velocities = velocity_sweep(
            v_min=float(params["v_min"]),
            v_max=float(params["v_max"]),
            v_step=float(params["v_step"]),
            minimum_speed=stall_speed(mass_kg, aero.area_m2, aero.cl_max, rho)
            * float(params["stall_margin"]),
        )
        envelope = level_flight_envelope(
            mass_kg=mass_kg,
            rho=rho,
            aero=aero,
            velocities=velocities,
            powertrain=powertrain,
            reserve_soc=float(params["reserve_soc"]) / 100.0,
            progress=lambda fraction: self._report(40 + int(55 * fraction), "Level flight"),
        )
        self._report(100, "Done")
        return self._result(mass_kg, rho, aero, powertrain, envelope)

    def _powertrain(self, components: list[dict[str, Any]]) -> Powertrain | None:
        members = find_powertrain_members(components)
        if members is None:
            return None
        return build_powertrain(
            members, state_of_charge=float(self.config.parameters["state_of_charge"]) / 100.0
        )

    def _check_cancelled(self) -> None:
        if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
            self.status = SolverStatus.CANCELLED
            raise TaskCancelledError("Flight performance analysis cancelled.")

    def _report(self, percent: int, message: str) -> None:
        self._check_cancelled()
        if self.token is not None:
            self.token.report_progress(percent, 100, message)

    def _result(
        self,
        mass_kg: float,
        rho: float,
        aero: AerodynamicModel,
        powertrain: Powertrain | None,
        envelope: PerformanceEnvelope,
    ) -> SolverResult:
        summary = [
            SummaryItem("mass", round(mass_kg * 1000.0, 1), "Flight Mass", "g", "mass"),
            SummaryItem("air_density", round(rho, 4), "Air Density", "kg/m³", "density"),
            SummaryItem("wing_area", round(aero.area_m2 * 100.0, 3), "Wing Area", "dm²", "area"),
            SummaryItem("cl_max", round(aero.cl_max, 4), "Max Lift (CL,max)"),
            SummaryItem("ld_max", round(aero.max_lift_to_drag, 2), "Max L/D"),
            SummaryItem(
                "stall_speed",
                round(envelope.stall_speed, 2),
                "Stall Speed",
                "m/s",
                "velocity",
            ),
            SummaryItem(
                "best_ld_speed",
                round(envelope.best_lift_to_drag_speed, 2),
                "Best L/D Speed",
                "m/s",
                "velocity",
            ),
            SummaryItem(
                "min_power_speed",
                round(envelope.min_power_speed, 2),
                "Min Power Speed",
                "m/s",
                "velocity",
            ),
        ]
        if aero.drag_polar is not None:
            summary.append(SummaryItem("cd0", round(aero.drag_polar.cd0, 5), "Zero-Lift Drag CD0"))
            summary.append(
                SummaryItem("k_induced", round(aero.drag_polar.k_induced, 5), "Induced Drag k")
            )
        if powertrain is not None and envelope.propulsion is not None:
            summary.extend(self._propulsion_summary(powertrain, envelope, envelope.propulsion))

        return SolverResult(
            solver_id=self.config.solver_id,
            config=self.config,
            name=self.config.name,
            status=SolverStatus.COMPLETED,
            summary={item.key: item for item in summary},
            tables={_TABLE_ID: self._table(envelope)},
            plots={plot.id: plot for plot in self._plots(envelope)},
        )

    @staticmethod
    def _propulsion_summary(
        powertrain: Powertrain, envelope: PerformanceEnvelope, propulsion: PropulsionSweep
    ) -> list[SummaryItem]:
        velocities = envelope.velocities
        max_speed, bounded = max_level_speed(
            velocities, propulsion.thrust_available, envelope.drag, propulsion.feasible
        )
        items = [
            SummaryItem(
                "battery_voltage",
                round(powertrain.open_circuit_voltage_v, 2),
                "Battery Open-Circuit Voltage",
                "V",
                "voltage",
            ),
            SummaryItem("max_speed", round(max_speed, 2), "Max Level Speed", "m/s", "velocity"),
            SummaryItem("max_speed_bounded", bounded, "Max Speed Within Sweep"),
        ]
        if not np.any(propulsion.feasible):
            items.append(SummaryItem("feasible", False, "Level Flight Feasible"))
            return items

        feasible = np.flatnonzero(propulsion.feasible)
        endurance_index = int(feasible[np.argmin(propulsion.electrical_power[feasible])])
        range_index = int(feasible[np.argmax(envelope.range_km[feasible])])
        climb_index = int(feasible[np.argmax(envelope.rate_of_climb[feasible])])
        items.extend(
            [
                SummaryItem("feasible", True, "Level Flight Feasible"),
                SummaryItem(
                    "best_endurance_speed",
                    round(float(velocities[endurance_index]), 2),
                    "Best Endurance Speed",
                    "m/s",
                    "velocity",
                ),
                SummaryItem(
                    "max_endurance",
                    round(float(envelope.endurance_min[endurance_index]), 1),
                    "Max Endurance",
                    "min",
                ),
                SummaryItem(
                    "best_range_speed",
                    round(float(velocities[range_index]), 2),
                    "Best Range Speed",
                    "m/s",
                    "velocity",
                ),
                SummaryItem(
                    "max_range",
                    round(float(envelope.range_km[range_index]), 2),
                    "Max Range",
                    "km",
                ),
                SummaryItem(
                    "cruise_power",
                    round(float(propulsion.electrical_power[range_index]), 1),
                    "Cruise Battery Power",
                    "W",
                    "power",
                ),
                SummaryItem(
                    "cruise_current",
                    round(float(propulsion.current[range_index]), 2),
                    "Cruise Current",
                    "A",
                    "current",
                ),
                SummaryItem(
                    "cruise_throttle",
                    round(float(propulsion.throttle_pct[range_index]), 1),
                    "Cruise Throttle",
                    "%",
                ),
                SummaryItem(
                    "best_climb_speed",
                    round(float(velocities[climb_index]), 2),
                    "Best Climb Speed",
                    "m/s",
                    "velocity",
                ),
                SummaryItem(
                    "max_rate_of_climb",
                    round(float(envelope.rate_of_climb[climb_index]), 2),
                    "Max Rate of Climb",
                    "m/s",
                    "velocity",
                ),
                SummaryItem(
                    "max_climb_angle",
                    round(float(np.max(envelope.climb_angle_deg[feasible])), 2),
                    "Max Climb Angle",
                    "°",
                    "angle",
                ),
            ]
        )
        return items

    @staticmethod
    def _table(envelope: PerformanceEnvelope) -> TableDefinition:
        columns = [
            TableColumn("velocity", "Airspeed", unit="m/s", quantity_id="velocity"),
            TableColumn("cl", "CL"),
            TableColumn("drag", "Drag", unit="N", quantity_id="force"),
            TableColumn("power_required", "Power Required", unit="W", quantity_id="power"),
        ]
        data: dict[str, list[Any]] = {
            "velocity": envelope.velocities.round(3).tolist(),
            "cl": envelope.lift_coefficient.round(4).tolist(),
            "drag": envelope.drag.round(4).tolist(),
            "power_required": envelope.power_required.round(2).tolist(),
        }
        propulsion = envelope.propulsion
        if propulsion is not None:
            columns.extend(
                [
                    TableColumn("thrust_available", "Thrust Available", "N", "force"),
                    TableColumn("power_available", "Power Available", "W", "power"),
                    TableColumn("throttle", "Throttle", "%"),
                    TableColumn("electrical_power", "Battery Power", "W", "power"),
                    TableColumn("current", "Current", "A", "current"),
                    TableColumn("rate_of_climb", "Rate of Climb", "m/s", "velocity"),
                    TableColumn("climb_angle", "Climb Angle", "°", "angle"),
                    TableColumn("endurance", "Endurance", "min"),
                    TableColumn("range", "Range", "km"),
                    TableColumn("feasible", "Feasible"),
                ]
            )
            data.update(
                {
                    "thrust_available": propulsion.thrust_available.round(4).tolist(),
                    "power_available": propulsion.power_available.round(2).tolist(),
                    "throttle": propulsion.throttle_pct.round(1).tolist(),
                    "electrical_power": propulsion.electrical_power.round(2).tolist(),
                    "current": propulsion.current.round(3).tolist(),
                    "rate_of_climb": envelope.rate_of_climb.round(3).tolist(),
                    "climb_angle": envelope.climb_angle_deg.round(2).tolist(),
                    "endurance": envelope.endurance_min.round(2).tolist(),
                    "range": envelope.range_km.round(3).tolist(),
                    "feasible": propulsion.feasible.tolist(),
                }
            )
        return TableDefinition(id=_TABLE_ID, title="Envelope", columns=columns, data=data)

    @staticmethod
    def _plots(envelope: PerformanceEnvelope) -> list[PlotDefinition]:
        with_propulsion = envelope.propulsion is not None
        # Speeds the powertrain cannot hold in level flight are shaded.
        valid_column = "feasible" if with_propulsion else None
        plots = [
            PlotDefinition(
                id="power_curves",
                title="Power",
                table_id=_TABLE_ID,
                x_column="velocity",
                series=[
                    PlotSeriesDef("power_required", "Required", color="#ef4444"),
                    *(
                        [PlotSeriesDef("power_available", "Available", color="#10b981")]
                        if with_propulsion
                        else []
                    ),
                ],
                y_label="Power",
                valid_column=valid_column,
            ),
            PlotDefinition(
                id="thrust_curves",
                title="Drag & Thrust",
                table_id=_TABLE_ID,
                x_column="velocity",
                series=[
                    PlotSeriesDef("drag", "Drag", color="#ef4444"),
                    *(
                        [PlotSeriesDef("thrust_available", "Thrust Available", color="#3b82f6")]
                        if with_propulsion
                        else []
                    ),
                ],
                y_label="Force",
                valid_column=valid_column,
            ),
        ]
        if with_propulsion:
            plots.extend(
                [
                    PlotDefinition(
                        id="climb",
                        title="Rate of Climb",
                        table_id=_TABLE_ID,
                        x_column="velocity",
                        series=[PlotSeriesDef("rate_of_climb", "Rate of Climb", color="#8b5cf6")],
                        y_label="Rate of Climb",
                        valid_column=valid_column,
                    ),
                    PlotDefinition(
                        id="endurance",
                        title="Endurance",
                        table_id=_TABLE_ID,
                        x_column="velocity",
                        series=[PlotSeriesDef("endurance", "Endurance", color="#f59e0b")],
                        y_label="Endurance",
                        valid_column=valid_column,
                    ),
                    PlotDefinition(
                        id="range",
                        title="Range",
                        table_id=_TABLE_ID,
                        x_column="velocity",
                        series=[PlotSeriesDef("range", "Range", color="#06b6d4")],
                        y_label="Range",
                        valid_column=valid_column,
                    ),
                    PlotDefinition(
                        id="battery_load",
                        title="Current & Throttle",
                        table_id=_TABLE_ID,
                        x_column="velocity",
                        series=[
                            PlotSeriesDef("current", "Current", color="#f97316"),
                            PlotSeriesDef(
                                "throttle",
                                "Throttle",
                                style="dashed",
                                color="#64748b",
                                axis="right",
                            ),
                        ],
                        valid_column=valid_column,
                    ),
                ]
            )
        return plots


__all__ = ["SOLVER_ID_FLIGHT_PERFORMANCE", "FlightPerformanceSolver"]
