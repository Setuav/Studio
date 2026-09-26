"""Aerodynamics Analysis Plugin for Setuav Studio."""

from __future__ import annotations

from typing import TYPE_CHECKING

from setuav_studio_sdk import (
    StudioAPI,
    ToolbarContribution,
    ToolbarMenuItemContribution,
    ToolContribution,
)

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
from setuav_studio.solver import SolverConfig

if TYPE_CHECKING:
    from .airfoil_analysis_tool import AirfoilAnalysisToolWindow


class AerodynamicsPlugin:
    """Plugin providing aerodynamic analysis solvers, polar sweeps, stability, and airfoil tools."""

    id = "org.setuav.studio.aerodynamics"
    priority = 70

    def __init__(self) -> None:
        self._api: StudioAPI | None = None
        self._tool_windows: set[AirfoilAnalysisToolWindow] = set()
        self._analysis_tools: list[ToolContribution] = []
        self._analysis_toolbar_id: str | None = None

    def activate(self, api: StudioAPI) -> None:
        self._api = api

        # 1. Register Aerodynamics Solvers
        api.register_solver(SOLVER_ID_ALPHA_SWEEP, AlphaSweepSolver)
        api.register_solver(SOLVER_ID_BETA_SWEEP, BetaSweepSolver)
        api.register_solver(SOLVER_ID_CONTROL_DEFLECTION, ControlDeflectionSolver)
        api.register_solver(SOLVER_ID_OPERATING_POINT, OperatingPointSolver)

        # 2. Solver Config Creation Callbacks
        def add_alpha_sweep_analysis() -> None:
            if api.current_project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            config = SolverConfig(
                solver_id=SOLVER_ID_ALPHA_SWEEP,
                name="Alpha Sweep Analysis",
                parameters={
                    "alpha_min": -5.0,
                    "alpha_max": 15.0,
                    "alpha_step": 1.0,
                    "velocity": 25.0,
                    "altitude": 0.0,
                    "beta": 0.0,
                    "method": "aero_buildup",
                    "spanwise_resolution": 12.0,
                    "chordwise_resolution": 8.0,
                },
            )
            api.add_solver_config(config)
            api.show_status("Added Alpha Sweep (Polar) configuration.", "success", 3000)

        def add_beta_sweep_analysis() -> None:
            if api.current_project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            config = SolverConfig(
                solver_id=SOLVER_ID_BETA_SWEEP,
                name="Beta Sweep Analysis",
                parameters={
                    "beta_min": -15.0,
                    "beta_max": 15.0,
                    "beta_step": 1.0,
                    "alpha": 2.0,
                    "velocity": 25.0,
                    "altitude": 0.0,
                    "method": "aero_buildup",
                    "spanwise_resolution": 12.0,
                    "chordwise_resolution": 8.0,
                },
            )
            api.add_solver_config(config)
            api.show_status("Added Beta Sweep (Sideslip) configuration.", "success", 3000)

        def add_control_deflection_analysis() -> None:
            if api.current_project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            config = SolverConfig(
                solver_id=SOLVER_ID_CONTROL_DEFLECTION,
                name="Control Deflection Analysis",
                parameters={
                    "channel": "elevator",
                    "deflection_min": -20.0,
                    "deflection_max": 20.0,
                    "deflection_step": 2.0,
                    "alpha": 2.0,
                    "beta": 0.0,
                    "velocity": 25.0,
                    "altitude": 0.0,
                    "method": "aero_buildup",
                },
            )
            api.add_solver_config(config)
            api.show_status("Added Control Deflection configuration.", "success", 3000)

        def add_operating_point_analysis() -> None:
            if api.current_project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            config = SolverConfig(
                solver_id=SOLVER_ID_OPERATING_POINT,
                name="Operating Point Analysis",
                parameters={
                    "alpha": 2.0,
                    "beta": 0.0,
                    "velocity": 25.0,
                    "altitude": 0.0,
                    "method": "aero_buildup",
                    "spanwise_resolution": 12.0,
                    "chordwise_resolution": 8.0,
                },
            )
            api.add_solver_config(config)
            api.show_status("Added Aerodynamic Operating Point configuration.", "success", 3000)

        # 3. Register Toolbar Item with Dropdown Menu
        self._analysis_toolbar_id = "aerodynamics.add-analysis"
        api.register_toolbar_item(
            ToolbarContribution(
                id=self._analysis_toolbar_id,
                title="Add Aerodynamic Analysis",
                icon="fa6s.wind",
                menu_items=(
                    ToolbarMenuItemContribution(
                        title="Alpha Sweep (Polar) Analysis",
                        callback=add_alpha_sweep_analysis,
                        icon="fa6s.chart-line",
                        enabled_when=lambda: api.current_project is not None,
                    ),
                    ToolbarMenuItemContribution(
                        title="Beta Sweep (Sideslip) Analysis",
                        callback=add_beta_sweep_analysis,
                        icon="fa6s.arrows-left-right",
                        enabled_when=lambda: api.current_project is not None,
                    ),
                    ToolbarMenuItemContribution(
                        title="Control Deflection Analysis",
                        callback=add_control_deflection_analysis,
                        icon="fa6s.sliders",
                        enabled_when=lambda: api.current_project is not None,
                    ),
                    ToolbarMenuItemContribution(
                        title="Operating Point Analysis",
                        callback=add_operating_point_analysis,
                        icon="fa6s.crosshairs",
                        enabled_when=lambda: api.current_project is not None,
                    ),
                ),
                enabled_when=lambda: api.current_project is not None,
                group="aerodynamics-creation",
                order=130,
            )
        )

        # 4. Register Tools Menu Items
        self._analysis_tools = [
            ToolContribution(
                group="Aerodynamics",
                title="Add Alpha Sweep (Polar) Analysis",
                callback=add_alpha_sweep_analysis,
                icon="fa6s.chart-line",
            ),
            ToolContribution(
                group="Aerodynamics",
                title="Add Beta Sweep (Sideslip) Analysis",
                callback=add_beta_sweep_analysis,
                icon="fa6s.arrows-left-right",
            ),
            ToolContribution(
                group="Aerodynamics",
                title="Add Control Deflection Analysis",
                callback=add_control_deflection_analysis,
                icon="fa6s.sliders",
            ),
            ToolContribution(
                group="Aerodynamics",
                title="Add Aero Operating Point Analysis",
                callback=add_operating_point_analysis,
                icon="fa6s.crosshairs",
            ),
            ToolContribution(
                group="Aerodynamics",
                title="Airfoil Analysis…",
                callback=self._open_airfoil_analysis_tool,
                icon="fa6s.chart-area",
            ),
        ]
        for tool in self._analysis_tools:
            api.register_tool(tool)

    def deactivate(self, api: StudioAPI) -> None:
        if self._analysis_toolbar_id is not None:
            api.unregister_toolbar_item(self._analysis_toolbar_id)

        for tool in self._analysis_tools:
            api.unregister_tool(tool)
        self._analysis_tools.clear()

        api.unregister_solver(SOLVER_ID_ALPHA_SWEEP)
        api.unregister_solver(SOLVER_ID_BETA_SWEEP)
        api.unregister_solver(SOLVER_ID_CONTROL_DEFLECTION)
        api.unregister_solver(SOLVER_ID_OPERATING_POINT)

        for window in list(self._tool_windows):
            window.close()
        self._tool_windows.clear()
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
