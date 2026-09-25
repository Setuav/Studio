"""Electrical Propulsion Analysis Solver integrating PyThrust with Core Studio Solver Architecture."""

from __future__ import annotations

import logging
import math
from typing import Any

from pythrust.propellers.database import (
    PropellerDataPoint,
    PropellerEntry,
    PropellerMetadata,
)
from pythrust.propulsion.models import (
    BatterySpec,
    MotorSpec,
    OperatingPoint,
    PropellerSpec,
    SystemSpec,
)
from pythrust.propulsion.solver import PropulsionSolver

from plugins.electrical_propulsion.database import get_propeller_database
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

SOLVER_ID_PROPULSION = "org.setuav.propulsion.analysis"


def _build_fallback_propeller(
    diameter_in: float, pitch_in: float, blades: int = 2
) -> PropellerEntry:
    """Construct synthetic analytical propeller polar when no database match exists."""
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


def _compute_air_density(altitude_m: float, temperature_c: float) -> float:
    """Compute atmospheric air density using ISA model."""
    t_kelvin = 273.15 + temperature_c
    if altitude_m <= 11000.0:
        p_pa = 101325.0 * (1.0 - 0.0065 * altitude_m / 288.15) ** 5.25588
    else:
        p_11k = 101325.0 * (1.0 - 0.0065 * 11000.0 / 288.15) ** 5.25588
        p_pa = p_11k * math.exp(-9.80665 * 0.0289644 * (altitude_m - 11000.0) / (8.31432 * 216.65))
    return p_pa / (287.058 * t_kelvin)


class ElectricalPropulsionSolver(AbstractSolver):
    """Core engineering solver for electrical propulsion performance and operating point analysis."""

    def __init__(self, config: SolverConfig, project: Any | None = None) -> None:
        super().__init__(config, project)

    def _resolve_powertrain(
        self,
    ) -> tuple[MotorSpec, PropellerSpec, PropellerEntry, BatterySpec, SystemSpec, float]:
        project = self.project
        if project is None and hasattr(self, "api"):
            project = getattr(self.api, "current_project", None)

        if project is None or not hasattr(project, "data") or not isinstance(project.data, dict):
            raise RuntimeError("No active project available for propulsion analysis.")

        components = project.data.get("components", [])
        if not isinstance(components, list):
            raise RuntimeError("Project components collection is invalid.")

        motor_comp = next(
            (
                c
                for c in components
                if isinstance(c, dict) and c.get("type") == "org.setuav.core:motor"
            ),
            None,
        )
        prop_comp = next(
            (
                c
                for c in components
                if isinstance(c, dict)
                and c.get("type") in ("org.setuav.core:propeller", "org.setuav.core:rotor")
            ),
            None,
        )
        battery_comp = next(
            (
                c
                for c in components
                if isinstance(c, dict) and c.get("type") == "org.setuav.core:battery"
            ),
            None,
        )
        esc_comp = next(
            (
                c
                for c in components
                if isinstance(c, dict) and c.get("type") == "org.setuav.core:esc"
            ),
            None,
        )

        missing: list[str] = []
        if motor_comp is None:
            missing.append("Electric Motor")
        if prop_comp is None:
            missing.append("Propeller")
        if battery_comp is None:
            missing.append("Battery")
        if missing:
            raise RuntimeError(f"Propulsion analysis requires: {', '.join(missing)}.")

        assert motor_comp is not None
        assert prop_comp is not None
        assert battery_comp is not None

        # Motor spec
        motor_params = motor_comp.get("parameters", {})
        kv = float(motor_params.get("kv", 900.0))
        rm = float(motor_params.get("resistance", 0.055))
        i0 = float(motor_params.get("no_load_current", 1.1))
        imax = float(motor_params.get("max_current", 40.0))
        motor_spec = MotorSpec(
            kv_rpm_per_v=kv,
            resistance_ohm=rm,
            no_load_current_a=i0,
            current_max_a=imax,
        )

        # Propeller spec & entry
        prop_params = prop_comp.get("parameters", {})
        diameter_mm = float(prop_params.get("diameter", 330.0))
        pitch_mm = float(prop_params.get("pitch", 165.0))
        blade_count = int(prop_params.get("blade_count", 2))
        d_m = diameter_mm / 1000.0
        p_m = pitch_mm / 1000.0
        d_in = d_m / 0.0254
        p_in = p_m / 0.0254
        prop_spec = PropellerSpec(diameter_m=d_m, blade_count=blade_count, pitch_m=p_m)

        prop_db = get_propeller_database()
        prop_entry: PropellerEntry | None = None
        model_id = str(prop_comp.get("model") or "")
        if model_id:
            prop_entry = prop_db.get(model_id)

        if prop_entry is None:
            prop_entry = prop_db.find_by_size(
                diameter_in=d_in, pitch_in=p_in, blade_count=blade_count, tolerance=1.5
            )

        if prop_entry is None:
            prop_entry = _build_fallback_propeller(d_in, p_in, blade_count)

        # Battery spec
        battery_params = battery_comp.get("parameters", {})
        cell_count = int(battery_params.get("cell_count", 6))
        cell_v = float(battery_params.get("cell_voltage", 3.7))
        v_nom = float(
            battery_params.get(
                "nominal_voltage", battery_params.get("voltage", cell_count * cell_v)
            )
        )
        capacity_mah = float(battery_params.get("capacity", 5000.0))
        battery_spec = BatterySpec(voltage_v=v_nom, discharge_efficiency=0.98)

        # System spec
        esc_params = esc_comp.get("parameters", {}) if esc_comp is not None else {}
        esc_r = float(esc_params.get("resistance", 0.005))
        system_spec = SystemSpec(resistance_ohm=esc_r)

        return motor_spec, prop_spec, prop_entry, battery_spec, system_spec, capacity_mah

    def _determine_sweep_points(self) -> tuple[str, str, str, list[tuple[float, float]]]:
        mode = str(self.config.parameters.get("mode", "airspeed_sweep"))
        pairs: list[tuple[float, float]] = []

        if mode == "airspeed_sweep":
            v_min = float(self.config.parameters.get("v_min", 0.0))
            v_max = float(self.config.parameters.get("v_max", 35.0))
            v_step = max(0.5, float(self.config.parameters.get("v_step", 1.0)))
            throttle_pct = max(
                1.0, min(100.0, float(self.config.parameters.get("throttle", 100.0)))
            )
            throttle = throttle_pct / 100.0

            curr_v = v_min
            while curr_v <= v_max + 1e-4:
                pairs.append((round(curr_v, 2), throttle))
                curr_v += v_step
            return mode, "airspeed", "Airspeed", pairs

        if mode == "throttle_sweep":
            v_fixed = max(0.0, float(self.config.parameters.get("airspeed", 15.0)))
            t_min = max(5.0, float(self.config.parameters.get("t_min", 10.0)))
            t_max = min(100.0, float(self.config.parameters.get("t_max", 100.0)))
            t_step = max(1.0, float(self.config.parameters.get("t_step", 5.0)))

            curr_t = t_min
            while curr_t <= t_max + 1e-4:
                pairs.append((v_fixed, round(curr_t / 100.0, 3)))
                curr_t += t_step
            return mode, "throttle", "Throttle", pairs

        # Single Operating Point
        v_val = max(0.0, float(self.config.parameters.get("airspeed", 18.0)))
        t_pct = max(1.0, min(100.0, float(self.config.parameters.get("throttle", 75.0))))
        pairs.append((v_val, t_pct / 100.0))
        return "operating_point", "airspeed", "Airspeed", pairs

    def run(self) -> SolverResult:
        """Execute propulsion analysis using PyThrust solver."""
        if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
            self.status = SolverStatus.CANCELLED
            raise TaskCancelledError("Analysis cancelled before execution.")

        motor_spec, prop_spec, prop_entry, battery_spec, system_spec, capacity_mah = (
            self._resolve_powertrain()
        )

        altitude_m = float(self.config.parameters.get("altitude", 0.0))
        temperature_c = float(self.config.parameters.get("temperature", 15.0))
        rho = _compute_air_density(altitude_m, temperature_c)

        mode, plot_x_col, plot_x_label, sweep_pairs = self._determine_sweep_points()
        pythrust_solver = PropulsionSolver()

        total_points = len(sweep_pairs)
        points_data: list[tuple[float, OperatingPoint]] = []

        for idx, (v_val, t_val) in enumerate(sweep_pairs):
            if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
                self.status = SolverStatus.CANCELLED
                raise TaskCancelledError("Analysis cancelled during sweep.")

            if self.token is not None:
                pct = int((idx + 1) / total_points * 100)
                status_msg = (
                    f"Throttle Sweep {t_val * 100:.0f}% ({pct}%)"
                    if plot_x_col == "throttle"
                    else f"Airspeed Sweep {v_val:.1f} m/s ({pct}%)"
                )
                self.token.report_progress(idx + 1, total_points, status_msg)

            op = pythrust_solver.solve_operating_point(
                motor=motor_spec,
                battery=battery_spec,
                system=system_spec,
                propeller=prop_spec,
                prop_entry=prop_entry,
                rho=rho,
                airspeed_mps=v_val,
                throttle=t_val,
                battery_state=None,
            )
            x_coord = t_val * 100.0 if plot_x_col == "throttle" else v_val
            points_data.append((x_coord, op))

        return self._build_result(
            mode=mode,
            plot_x_col=plot_x_col,
            plot_x_label=plot_x_label,
            points_data=points_data,
            v_nom=battery_spec.voltage_v,
            capacity_mah=capacity_mah,
        )

    def _build_result(
        self,
        mode: str,
        plot_x_col: str,
        plot_x_label: str,
        points_data: list[tuple[float, OperatingPoint]],
        v_nom: float,
        capacity_mah: float,
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
        feasibles = [p[1].is_feasible for p in points_data]

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
                    PlotSeriesDef(y_column="current", label="Motor Current (A)", color="#ea580c"),
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
        battery_energy_wh = (v_nom * capacity_mah) / 1000.0
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
