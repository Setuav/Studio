"""Aerodynamics Analysis Plugin for Setuav Studio."""
from __future__ import annotations

from typing import Any
from PySide6.QtCore import Qt

from setuav_studio.plugin_system import (
    PanelContribution,
    StudioAPI,
    ToolContribution,
    WorkspaceContribution,
)
from .charts_dock import AeroChartsDock
from .controls_dock import AeroControlsDock
from .results_dock import AeroResultsDock
from .engine.base import AeroResult


class AerodynamicsPlugin:
    """Plugin providing multi-engine aerodynamic analysis, polars, and curves."""

    id = "org.setuav.studio.aerodynamics"
    priority = 20

    def __init__(self) -> None:
        self._controls_dock: AeroControlsDock | None = None
        self._results_dock: AeroResultsDock | None = None
        self._charts_dock: AeroChartsDock | None = None

    def activate(self, api: StudioAPI) -> None:
        # 1. Register Aerodynamics Workspace
        api.add_workspace(
            WorkspaceContribution(
                id="studio.workspace.aerodynamics",
                title="Aerodynamics",
                order=15,
            )
        )

        # 2. Factories with instance retention for inter-dock event dispatch
        def create_controls_dock() -> AeroControlsDock:
            dock = AeroControlsDock(api, on_result_callback=self._handle_analysis_result)
            self._controls_dock = dock
            return dock

        def create_results_dock() -> AeroResultsDock:
            dock = AeroResultsDock(api)
            self._results_dock = dock
            return dock

        def create_charts_dock() -> AeroChartsDock:
            dock = AeroChartsDock(api)
            self._charts_dock = dock
            return dock

        # 3. Register Controls Dock (Left)
        api.add_panel(
            PanelContribution(
                id="aerodynamics.controls_dock",
                title="Aero Controls",
                factory=create_controls_dock,
                workspace_id="studio.workspace.aerodynamics",
                area=Qt.DockWidgetArea.LeftDockWidgetArea,
                icon="fa6s.wind",
            )
        )

        # 4. Register Performance Charts Dock (Center/Right)
        api.add_panel(
            PanelContribution(
                id="aerodynamics.charts_dock",
                title="Aerodynamic Curves",
                factory=create_charts_dock,
                workspace_id="studio.workspace.aerodynamics",
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                icon="fa6s.chart-line",
            )
        )

        # 5. Register Results Dock (Right)
        api.add_panel(
            PanelContribution(
                id="aerodynamics.results_dock",
                title="Aero Results",
                factory=create_results_dock,
                workspace_id="studio.workspace.aerodynamics",
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                icon="fa6s.table-list",
            )
        )

        # 6. Register Tool Contribution
        def run_quick_analysis() -> None:
            api.switch_workspace("studio.workspace.aerodynamics")
            if self._controls_dock:
                self._controls_dock.run_analysis()

        api.register_tool(
            ToolContribution(
                group="Aerodynamics",
                title="Run Aerodynamic Analysis…",
                callback=run_quick_analysis,
                icon="fa6s.wind",
                shortcut="Ctrl+Alt+A",
            )
        )

    def deactivate(self, api: StudioAPI) -> None:
        api.remove_panel("aerodynamics.controls_dock")
        api.remove_panel("aerodynamics.results_dock")
        api.remove_panel("aerodynamics.charts_dock")
        api.remove_workspace("studio.workspace.aerodynamics")
        api.remove_action("Tools/Aerodynamics", "Run Aerodynamic Analysis…")
        self._controls_dock = None
        self._results_dock = None
        self._charts_dock = None

    def _handle_analysis_result(self, result: AeroResult) -> None:
        if self._results_dock:
            self._results_dock.display_results(result)
        if self._charts_dock:
            self._charts_dock.plot_results(result)
