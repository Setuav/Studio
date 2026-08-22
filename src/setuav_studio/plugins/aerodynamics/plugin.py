"""Aerodynamics Analysis Plugin for Setuav Studio."""
from __future__ import annotations

from PySide6.QtCore import Qt

from setuav_studio.plugin_system import (
    PanelContribution,
    StudioAPI,
    WorkspaceContribution,
)
from .aero_3d_dock import Aero3DDock
from .charts_dock import AeroChartsDock
from .controls_dock import AeroControlsDock
from .results_dock import AeroResultsDock
from .engine.base import AeroResult


class AerodynamicsPlugin:
    """Plugin providing multi-engine aerodynamic analysis, polars, 3D visualization, and curves."""

    id = "org.setuav.studio.aerodynamics"
    priority = 20

    def __init__(self) -> None:
        self._api: StudioAPI | None = None

    def activate(self, api: StudioAPI) -> None:
        self._api = api

        # 1. Register Aerodynamics Workspace
        api.add_workspace(
            WorkspaceContribution(
                id="studio.workspace.aerodynamics",
                title="Aerodynamics",
                order=15,
            )
        )

        # 2. Register Controls Dock (Left)
        api.add_panel(
            PanelContribution(
                id="aerodynamics.controls_dock",
                title="Aero Controls",
                factory=lambda: AeroControlsDock(api, on_result_callback=self._handle_analysis_result),
                workspace_id="studio.workspace.aerodynamics",
                area=Qt.DockWidgetArea.LeftDockWidgetArea,
                icon="fa6s.wind",
            )
        )

        # 3. Register Performance Charts Dock (Right)
        api.add_panel(
            PanelContribution(
                id="aerodynamics.charts_dock",
                title="Aerodynamic Curves",
                factory=lambda: AeroChartsDock(api),
                workspace_id="studio.workspace.aerodynamics",
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                icon="fa6s.chart-line",
            )
        )

        # 4. Register Aero 3D Dock (Right)
        api.add_panel(
            PanelContribution(
                id="aerodynamics.aero_3d",
                title="Aero 3D",
                factory=lambda: Aero3DDock(api),
                workspace_id="studio.workspace.aerodynamics",
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                icon="fa6s.cube",
            )
        )

        # 5. Register Results Dock (Right)
        api.add_panel(
            PanelContribution(
                id="aerodynamics.results_dock",
                title="Aero Results",
                factory=lambda: AeroResultsDock(api),
                workspace_id="studio.workspace.aerodynamics",
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                icon="fa6s.table-list",
            )
        )

    def deactivate(self, api: StudioAPI) -> None:
        api.remove_panel("aerodynamics.controls_dock")
        api.remove_panel("aerodynamics.results_dock")
        api.remove_panel("aerodynamics.charts_dock")
        api.remove_panel("aerodynamics.aero_3d")
        api.remove_workspace("studio.workspace.aerodynamics")
        self._api = None

    def _handle_analysis_result(self, result: AeroResult) -> None:
        if self._api is not None:
            self._api.publish("aerodynamics.analysis_completed", result)
