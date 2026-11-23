# Writing a Plugin

This page builds a small but complete plugin, **Hover Power**. It adds an
analysis that estimates the ideal hover power of the aircraft for a range of
rotor diameters, with a table, a plot and a summary. Along the way it uses the
parts most plugins need: a solver with parameters, a toolbar item, and the
project's data.

## Package layout

```text
hover-power/
├── pyproject.toml
└── hover_power/
    ├── __init__.py
    ├── plugin.py
    └── solver.py
```

`pyproject.toml` declares the plugin in the `setuav_studio.plugins` entry-point
group, so Studio finds it once the package is installed:

```toml
[project]
name = "hover-power"
version = "0.1.0"
dependencies = ["setuav-studio"]

[project.entry-points."setuav_studio.plugins"]
"com.example.hover" = "hover_power.plugin:HoverPowerPlugin"
```

## The solver

A solver declares its parameters as `ParameterField`s and returns a
`SolverResult`. Studio builds the parameter editor from the fields, checks
their ranges before a run, and runs the solver in the background with
`self.project` set to the open project.

The result holds tables, plots that draw columns of a table, and summary rows.
Give every column and summary row its unit, so Studio can show it in the
user's display units.

```python title="hover_power/solver.py"
"""Ideal hover power of the aircraft for a range of rotor diameters."""

from __future__ import annotations

import math
from typing import ClassVar

from setuav_studio.api import ParameterField
from setuav_studio.solver import AbstractSolver, SolverResult
from setuav_studio.solver.results import (
    PlotDefinition,
    PlotSeriesDef,
    SummaryItem,
    TableColumn,
    TableDefinition,
)

SOLVER_ID = "com.example.hover:hover-power"
STANDARD_GRAVITY = 9.80665


class HoverPowerSolver(AbstractSolver):
    """Momentum-theory hover power for rotor diameters from Diameter Min to Max."""

    PARAMETER_FIELDS: ClassVar[list[ParameterField]] = [
        ParameterField(
            key="rotor_count",
            label="Rotors",
            field_type=int,
            default=4,
            min_value=1,
            max_value=12,
            decimals=0,
        ),
        ParameterField(
            key="diameter_min",
            label="Diameter Min",
            unit="mm",
            quantity="length",
            default=200.0,
            min_value=10.0,
            max_value=5000.0,
        ),
        ParameterField(
            key="diameter_max",
            label="Diameter Max",
            unit="mm",
            quantity="length",
            default=500.0,
            min_value=10.0,
            max_value=5000.0,
        ),
        ParameterField(
            key="air_density",
            label="Air Density",
            unit="kg/m³",
            default=1.225,
            min_value=0.1,
            max_value=2.0,
            decimals=3,
        ),
    ]

    def run(self) -> SolverResult:
        parameters = self.config.parameters
        rotors = int(parameters["rotor_count"])
        density = float(parameters["air_density"])
        low, high = float(parameters["diameter_min"]), float(parameters["diameter_max"])
        # The project's total mass, in kg, from every component's mass.
        weight_n = self.project.mass_properties.mass_kg * STANDARD_GRAVITY
        thrust_n = weight_n / rotors

        diameters_mm = [low + (high - low) * i / 9 for i in range(10)]
        powers_w = []
        for diameter_mm in diameters_mm:
            disk_area_m2 = math.pi * (diameter_mm / 2000.0) ** 2
            powers_w.append(rotors * thrust_n**1.5 / math.sqrt(2.0 * density * disk_area_m2))

        table = TableDefinition(
            id="hover",
            title="Hover",
            columns=[
                TableColumn("diameter", "Rotor Diameter", "mm", "length"),
                TableColumn("power", "Ideal Power", "W", "power"),
            ],
            data={"diameter": diameters_mm, "power": powers_w},
        )
        plot = PlotDefinition(
            id="power",
            title="Power",
            table_id="hover",
            x_column="diameter",
            series=[PlotSeriesDef("power", "Ideal Power")],
            x_label="Rotor Diameter",
            y_label="Ideal Power",
        )
        return SolverResult(
            solver_id=SOLVER_ID,
            config=self.config,
            name=self.config.name,
            summary={
                "thrust": SummaryItem("thrust", round(thrust_n, 2), "Thrust per Rotor", "N"),
                "power": SummaryItem("power", round(powers_w[-1], 1), "Power at Max Diameter", "W"),
            },
            tables={table.id: table},
            plots={plot.id: plot},
        )
```

!!! tip
    Read the model through the project: `self.project.mass_properties` gives
    the total mass and CG, `self.project.data["components"]` the components,
    and `self.project.get_scope()` the values formulas see.

## The plugin

The plugin registers the solver and a toolbar item in the **analysis** group.
The toolbar item adds a configuration of the solver to the project, which
appears under **Analyses** with the default parameters. Everything registered
in `activate` is removed in `deactivate`.

```python title="hover_power/plugin.py"
"""Hover Power: an example Setuav Studio plugin that adds an analysis."""

from __future__ import annotations

from setuav_studio.api import StudioAPI, ToolbarContribution
from setuav_studio.solver import SolverConfig

from .solver import SOLVER_ID, HoverPowerSolver

TOOLBAR_ID = "com.example.hover.add-analysis"


class HoverPowerPlugin:
    id = "com.example.hover"

    def activate(self, api: StudioAPI) -> None:
        api.register_solver(SOLVER_ID, HoverPowerSolver, icon="fa6s.helicopter")
        api.register_toolbar_item(
            ToolbarContribution(
                id=TOOLBAR_ID,
                title="Add Hover Power Analysis",
                icon="fa6s.helicopter",
                callback=lambda: self._add_analysis(api),
                enabled_when=lambda: api.project is not None,
                group="analysis",
                order=280,
            )
        )

    def deactivate(self, api: StudioAPI) -> None:
        api.unregister_toolbar_item(TOOLBAR_ID)
        api.unregister_solver(SOLVER_ID)

    @staticmethod
    def _add_analysis(api: StudioAPI) -> None:
        api.add_solver_config(
            SolverConfig(
                solver_id=SOLVER_ID,
                name="Hover Power",
                parameters=HoverPowerSolver.default_parameters(),
            )
        )
```

## Try it

Install the package into Studio's environment in editable mode and start
Studio:

```bash
uv pip install -e path/to/hover-power
uv run --locked setuav-studio
```

Open a project, click **Add Hover Power Analysis** in the toolbar, and run it.
Its **Hover** table and **Power** plot appear under the analysis, and the
summary shows the thrust per rotor. **Tools → Plugin Manager** lists the
plugin and can disable it.

!!! note
    During development you can also place the package folder in the user
    plugin folder instead of installing it; see
    [Discovery and loading](index.md#discovery-and-loading).

## Next steps

- Add a panel with `register_panel` and a `PanelContribution`, or a command in
  the Tools menu with `register_tool`.
- Ship your own icons with `register_plugin_icons`; see
  [Icons](api.md#icons).
- Add a component type with `register_component_type`, its editor and its
  scene objects; the 3D Viewer colors them with the component's color, see
  [Component colors](api.md#component-colors).
- Test that the plugin can be activated, deactivated and activated again; see
  [Testing a plugin](index.md#testing-a-plugin).
