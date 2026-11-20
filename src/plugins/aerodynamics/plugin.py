"""Aerodynamics Analysis Plugin for Setuav Studio."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from plugins.aerodynamics.solver import (
    SOLVER_ID_ALPHA_SWEEP,
    SOLVER_ID_BETA_SWEEP,
    SOLVER_ID_CONTROL_DEFLECTION,
    SOLVER_ID_OPERATING_POINT,
    AlphaSweepSolver,
    BetaSweepSolver,
    ControlDeflectionSolver,
    OperatingPointSolver,
)
from setuav_studio.api import (
    StudioAPI,
    ToolbarContribution,
    ToolContribution,
)
from setuav_studio.solver import SolverConfig
from setuav_studio.ui.style.icons import register_plugin_icons, unregister_plugin_icons

if TYPE_CHECKING:
    from .airfoil_analysis_tool import AirfoilAnalysisToolWindow


class AerodynamicsPlugin:
    """Plugin providing aerodynamic analysis solvers, polar sweeps, stability, and airfoil tools."""

    id = "org.setuav.studio.aerodynamics"
    priority = 70

    def __init__(self) -> None:
        self._api: StudioAPI | None = None
        self._tool_windows: set[AirfoilAnalysisToolWindow] = set()
        self._tools: list[ToolContribution] = []
        self._analysis_toolbar_ids: list[str] = []

    def activate(self, api: StudioAPI) -> None:
        register_plugin_icons(self.id, Path(__file__).parent / "assets" / "icons")
        self._api = api

        # 1. Register Aerodynamics Solvers
        api.register_solver(SOLVER_ID_ALPHA_SWEEP, AlphaSweepSolver, icon="aero_alpha_sweep")
        api.register_solver(SOLVER_ID_BETA_SWEEP, BetaSweepSolver, icon="aero_beta_sweep")
        api.register_solver(
            SOLVER_ID_CONTROL_DEFLECTION, ControlDeflectionSolver, icon="aero_control_deflection"
        )
        api.register_solver(
            SOLVER_ID_OPERATING_POINT, OperatingPointSolver, icon="aero_operating_point"
        )

        # 2. Solver Config Creation Callbacks
        def add_alpha_sweep_analysis() -> None:
            if api.project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            config = SolverConfig(
                solver_id=SOLVER_ID_ALPHA_SWEEP,
                name="Alpha Sweep",
                parameters=AlphaSweepSolver.default_parameters(),
            )
            api.add_solver_config(config)
            api.show_status("Added Alpha Sweep (Polar) configuration.", "success", 3000)

        def add_beta_sweep_analysis() -> None:
            if api.project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            config = SolverConfig(
                solver_id=SOLVER_ID_BETA_SWEEP,
                name="Beta Sweep",
                parameters=BetaSweepSolver.default_parameters(),
            )
            api.add_solver_config(config)
            api.show_status("Added Beta Sweep (Sideslip) configuration.", "success", 3000)

        def add_control_deflection_analysis() -> None:
            if api.project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            config = SolverConfig(
                solver_id=SOLVER_ID_CONTROL_DEFLECTION,
                name="Control Deflection",
                parameters=ControlDeflectionSolver.default_parameters(),
            )
            api.add_solver_config(config)
            api.show_status("Added Control Deflection configuration.", "success", 3000)

        def add_operating_point_analysis() -> None:
            if api.project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            config = SolverConfig(
                solver_id=SOLVER_ID_OPERATING_POINT,
                name="Operating Point",
                parameters=OperatingPointSolver.default_parameters(),
            )
            api.add_solver_config(config)
            api.show_status("Added Aerodynamic Operating Point configuration.", "success", 3000)

        # 3. Register one toolbar button per analysis
        analyses = (
            (
                "alpha-sweep",
                "Add Alpha Sweep (Polar) Analysis",
                add_alpha_sweep_analysis,
                "aero_alpha_sweep",
            ),
            (
                "beta-sweep",
                "Add Beta Sweep (Sideslip) Analysis",
                add_beta_sweep_analysis,
                "aero_beta_sweep",
            ),
            (
                "control-deflection",
                "Add Control Deflection Analysis",
                add_control_deflection_analysis,
                "aero_control_deflection",
            ),
            (
                "operating-point",
                "Add Aero Operating Point Analysis",
                add_operating_point_analysis,
                "aero_operating_point",
            ),
        )
        for index, (key, title, callback, icon) in enumerate(analyses):
            toolbar_id = f"aerodynamics.add-{key}"
            api.register_toolbar_item(
                ToolbarContribution(
                    id=toolbar_id,
                    title=title,
                    callback=callback,
                    icon=icon,
                    enabled_when=lambda: api.project is not None,
                    group="analysis",
                    order=200 + index,
                )
            )
            self._analysis_toolbar_ids.append(toolbar_id)

        # 4. Register the Tools menu item; the analyses are on the toolbar
        self._tools = [
            ToolContribution(
                group="Aerodynamics",
                title="Airfoil Analysis…",
                callback=self._open_airfoil_analysis_tool,
                icon="aero_airfoil_analysis",
            ),
        ]
        for tool in self._tools:
            api.register_tool(tool)

    def deactivate(self, api: StudioAPI) -> None:
        for toolbar_id in self._analysis_toolbar_ids:
            api.unregister_toolbar_item(toolbar_id)
        self._analysis_toolbar_ids.clear()

        for tool in self._tools:
            api.unregister_tool(tool)
        self._tools.clear()

        api.unregister_solver(SOLVER_ID_ALPHA_SWEEP)
        api.unregister_solver(SOLVER_ID_BETA_SWEEP)
        api.unregister_solver(SOLVER_ID_CONTROL_DEFLECTION)
        api.unregister_solver(SOLVER_ID_OPERATING_POINT)

        for window in list(self._tool_windows):
            window.close()
        self._tool_windows.clear()
        unregister_plugin_icons(self.id)
        self._api = None

    def _open_airfoil_analysis_tool(self) -> None:
        if self._api is None:
            return
        from .airfoil_analysis_tool import AirfoilAnalysisToolWindow

        window = AirfoilAnalysisToolWindow(self._api)
        self._tool_windows.add(window)
        window.destroyed.connect(
            lambda _object=None, tool_window=window: self._tool_windows.discard(tool_window)
        )
        window.show()
        window.raise_()
        window.activateWindow()
