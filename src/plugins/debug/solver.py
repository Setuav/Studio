"""Mock analysis solver for generating multi-unit synthetic engineering data."""

from __future__ import annotations

import math
import time
from typing import Any

from setuav_studio.solver.base import AbstractSolver, SolverConfig, SolverStatus
from setuav_studio.solver.results import (
    AnalysisResult,
    PlotDefinition,
    PlotSeriesDef,
    SummaryItem,
    TableColumn,
    TableDefinition,
)
from setuav_studio.task.types import TaskCancelledError

SOLVER_ID_MOCK_GENERATOR = "debug.mock_generator"

# Canonical channels with unique physical quantities and base units
CHANNEL_PALETTE: list[dict[str, Any]] = [
    {
        "key": "time",
        "label": "Time",
        "unit": "s",
        "quantity_id": None,
        "base": 0.0,
        "scale": 1.0,
        "waveform": "linear",
    },
    {
        "key": "airspeed",
        "label": "Airspeed",
        "unit": "m/s",
        "quantity_id": "velocity",
        "base": 24.0,
        "scale": 8.0,
        "waveform": "sine",
    },
    {
        "key": "aoa",
        "label": "Angle of Attack",
        "unit": "deg",
        "quantity_id": "angle",
        "base": 3.5,
        "scale": 6.5,
        "waveform": "cosine",
    },
    {
        "key": "lift",
        "label": "Lift Force",
        "unit": "N",
        "quantity_id": "force",
        "base": 150.0,
        "scale": 75.0,
        "waveform": "quadratic",
    },
    {
        "key": "dyn_pressure",
        "label": "Dynamic Pressure",
        "unit": "Pa",
        "quantity_id": "pressure",
        "base": 350.0,
        "scale": 120.0,
        "waveform": "sine",
    },
    {
        "key": "shaft_power",
        "label": "Shaft Power",
        "unit": "W",
        "quantity_id": "power",
        "base": 550.0,
        "scale": 180.0,
        "waveform": "cosine",
    },
    {
        "key": "voltage",
        "label": "Battery Voltage",
        "unit": "V",
        "quantity_id": "voltage",
        "base": 22.2,
        "scale": -3.2,
        "waveform": "linear",
    },
    {
        "key": "current",
        "label": "Motor Current",
        "unit": "A",
        "quantity_id": "current",
        "base": 25.0,
        "scale": 10.0,
        "waveform": "sine",
    },
    {
        "key": "energy",
        "label": "Consumed Energy",
        "unit": "Wh",
        "quantity_id": "energy",
        "base": 2.0,
        "scale": 60.0,
        "waveform": "linear",
    },
    {
        "key": "deflection",
        "label": "Wing Deflection",
        "unit": "mm",
        "quantity_id": "length",
        "base": 15.0,
        "scale": 12.0,
        "waveform": "sine",
    },
    {
        "key": "fuel_mass",
        "label": "Fuel Mass",
        "unit": "g",
        "quantity_id": "mass",
        "base": 900.0,
        "scale": -250.0,
        "waveform": "linear",
    },
    {
        "key": "wetted_area",
        "label": "Wetted Area",
        "unit": "dm2",
        "quantity_id": "area",
        "base": 4.5,
        "scale": 1.5,
        "waveform": "cosine",
    },
    {
        "key": "volume",
        "label": "Displaced Volume",
        "unit": "dm3",
        "quantity_id": "volume",
        "base": 18.0,
        "scale": 4.0,
        "waveform": "sine",
    },
    {
        "key": "torque",
        "label": "Motor Torque",
        "unit": "N*m",
        "quantity_id": "torque",
        "base": 2.2,
        "scale": 0.8,
        "waveform": "sine",
    },
    {
        "key": "frequency",
        "label": "Propeller RPM",
        "unit": "rpm",
        "quantity_id": "frequency",
        "base": 5200.0,
        "scale": 1100.0,
        "waveform": "cosine",
    },
    {
        "key": "capacity",
        "label": "Remaining Capacity",
        "unit": "mAh",
        "quantity_id": "capacity",
        "base": 5200.0,
        "scale": -2200.0,
        "waveform": "linear",
    },
    {
        "key": "resistance",
        "label": "Internal Resistance",
        "unit": "ohm",
        "quantity_id": "resistance",
        "base": 0.03,
        "scale": 0.01,
        "waveform": "sine",
    },
    {
        "key": "inertia",
        "label": "Roll Inertia",
        "unit": "kg*m2",
        "quantity_id": "inertia",
        "base": 0.55,
        "scale": 0.12,
        "waveform": "cosine",
    },
    {
        "key": "density",
        "label": "Air Density",
        "unit": "kg/m3",
        "quantity_id": "density",
        "base": 1.225,
        "scale": -0.18,
        "waveform": "linear",
    },
    {
        "key": "wing_loading",
        "label": "Wing Loading",
        "unit": "g/dm2",
        "quantity_id": "wing_loading",
        "base": 45.0,
        "scale": -4.0,
        "waveform": "linear",
    },
]

# Secondary units pool for extra columns beyond 20
SECONDARY_UNITS: list[tuple[str, str, str, str]] = [
    ("ground_speed", "Ground Speed", "km/h", "velocity"),
    ("thrust", "Thrust Force", "kN", "force"),
    ("pitch_angle", "Pitch Angle", "rad", "angle"),
    ("static_pressure", "Static Pressure", "kPa", "pressure"),
    ("peak_power", "Peak Power", "kW", "power"),
    ("cell_voltage", "Cell Voltage", "mV", "voltage"),
    ("telemetry_current", "Telemetry Current", "mA", "current"),
    ("kinetic_energy", "Kinetic Energy", "kJ", "energy"),
    ("chord_length", "Chord Position", "cm", "length"),
    ("total_mass", "Total Mass", "kg", "mass"),
]


def resolve_channel_definitions(col_count: int) -> list[dict[str, Any]]:
    """Build a list of unique channel specifications with distinct units."""
    channels: list[dict[str, Any]] = []
    used_units: set[str] = set()

    for ch in CHANNEL_PALETTE:
        if len(channels) >= col_count:
            break
        channels.append(ch)
        used_units.add(ch["unit"])

    sec_idx = 0
    while len(channels) < col_count:
        if sec_idx < len(SECONDARY_UNITS):
            key, label, unit, qty = SECONDARY_UNITS[sec_idx]
            sec_idx += 1
        else:
            n = len(channels) + 1
            key, label, unit, qty = f"param_{n}", f"Parameter {n}", f"u{n}", None

        channels.append(
            {
                "key": key,
                "label": label,
                "unit": unit,
                "quantity_id": qty,
                "base": 10.0 + len(channels),
                "scale": 5.0,
                "waveform": "sine" if len(channels) % 2 == 0 else "cosine",
            }
        )

    return channels


class MockGeneratorSolver(AbstractSolver):
    """Solver generating configurable multi-unit engineering data for testing and debug."""

    def __init__(self, config: SolverConfig) -> None:
        super().__init__(config)

    def run(self) -> AnalysisResult:
        """Execute mock generation simulating long-running analysis and pairwise plotting."""
        duration = max(0.0, float(self.config.parameters.get("duration", 3.0)))
        rows = max(1, int(self.config.parameters.get("rows", 50)))
        columns = max(4, int(self.config.parameters.get("columns", 4)))

        # 1. Initial cancellation check
        if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
            self.status = SolverStatus.CANCELLED
            raise TaskCancelledError("Solver cancelled before start.")

        # 2. Simulated execution loop with smooth progress reporting
        if duration > 0.01:
            num_steps = max(5, int(duration * 20))
            dt = duration / num_steps
            for step in range(num_steps):
                if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
                    self.status = SolverStatus.CANCELLED
                    raise TaskCancelledError("Solver cancelled during execution.")

                pct = int((step + 1) / num_steps * 100)
                self.progress = pct / 100.0
                if self.token is not None:
                    self.token.report_progress(step + 1, num_steps, f"Mock Analysis ({pct}%)")

                time.sleep(dt)

        if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
            self.status = SolverStatus.CANCELLED
            raise TaskCancelledError("Solver cancelled after execution.")

        # 3. Generate data columns with distinct units
        channels = resolve_channel_definitions(columns)
        table_data: dict[str, list[float]] = {ch["key"]: [] for ch in channels}

        for i in range(rows):
            u = i / max(1, rows - 1)
            for ch in channels:
                w_type = ch.get("waveform", "sine")
                base = float(ch.get("base", 0.0))
                scale = float(ch.get("scale", 1.0))

                if w_type == "linear":
                    val = base + scale * u
                elif w_type == "sine":
                    val = base + scale * math.sin(2.0 * math.pi * u)
                elif w_type == "cosine":
                    val = base + scale * math.cos(2.0 * math.pi * u)
                elif w_type == "quadratic":
                    val = base + scale * (4.0 * u * (1.0 - u))
                else:
                    val = base + scale * u

                table_data[ch["key"]].append(round(val, 4))

        # 4. Construct TableDefinition
        table_columns = [
            TableColumn(
                key=ch["key"],
                label=ch["label"],
                unit=ch["unit"],
                quantity_id=ch.get("quantity_id"),
            )
            for ch in channels
        ]
        table = TableDefinition(
            id="mock_data",
            title="Mock Generated Data",
            columns=table_columns,
            data=table_data,
        )

        # 5. Construct pairwise consecutive PlotDefinitions
        palette = ["#2196F3", "#4CAF50", "#FF9800", "#E91E63", "#9C27B0", "#00BCD4"]
        plots: dict[str, PlotDefinition] = {}
        plot_idx = 0
        for i in range(0, len(channels) - 1, 2):
            x_ch = channels[i]
            y_ch = channels[i + 1]
            plot_id = f"plot_{x_ch['key']}_{y_ch['key']}"
            series_color = palette[plot_idx % len(palette)]
            plots[plot_id] = PlotDefinition(
                id=plot_id,
                title=f"{y_ch['label']} vs {x_ch['label']}",
                table_id="mock_data",
                x_column=x_ch["key"],
                series=[
                    PlotSeriesDef(y_column=y_ch["key"], label=y_ch["label"], color=series_color)
                ],
            )
            plot_idx += 1

        if len(channels) % 2 != 0:
            first_ch = channels[0]
            last_ch = channels[-1]
            plot_id = f"plot_{first_ch['key']}_{last_ch['key']}"
            series_color = palette[plot_idx % len(palette)]
            plots[plot_id] = PlotDefinition(
                id=plot_id,
                title=f"{last_ch['label']} vs {first_ch['label']}",
                table_id="mock_data",
                x_column=first_ch["key"],
                series=[
                    PlotSeriesDef(
                        y_column=last_ch["key"], label=last_ch["label"], color=series_color
                    )
                ],
            )

        # 6. Summary metrics
        summary = {
            "rows_generated": SummaryItem(key="rows_generated", label="Rows Generated", value=rows),
            "columns_generated": SummaryItem(
                key="columns_generated", label="Columns Generated", value=len(channels)
            ),
            "run_duration": SummaryItem(
                key="run_duration", label="Target Duration", value=duration, unit="s"
            ),
        }

        self.status = SolverStatus.COMPLETED
        return AnalysisResult(
            solver_id=self.config.solver_id,
            config=self.config,
            name=self.config.name,
            status=SolverStatus.COMPLETED,
            summary=summary,
            tables={"mock_data": table},
            plots=plots,
        )
