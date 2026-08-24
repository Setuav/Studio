"""Aerodynamics Analysis Plugin for Setuav Studio."""
from __future__ import annotations

from PySide6.QtCore import Qt

from setuav_studio.plugin_system import (
    PanelContribution,
    StudioAPI,
    ToolContribution,
    WorkspaceContribution,
)
from .aero_3d_tool import Aero3DToolWindow
from .charts_dock import AeroChartsDock
from .controls_dock import AeroControlsDock
from .results_dock import AeroResultsDock
from .engine.base import AeroResult


class AerodynamicsPlugin:
    """Plugin providing aerodynamic analysis, result history, and curves."""

    id = "org.setuav.studio.aerodynamics"
    priority = 20

    def __init__(self) -> None:
        self._api: StudioAPI | None = None
        self._latest_result: AeroResult | None = None
        self._tool_windows: set[Aero3DToolWindow] = set()

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

        api.register_tool(
            ToolContribution(
                group="Aerodynamics",
                title="AeroSandbox 3D Snapshot…",
                callback=self._open_aero_3d_tool,
                icon="fa6s.cube",
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

        # 4. Register Results Dock (Right)
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
        api.remove_action("Tools/Aerodynamics", "AeroSandbox 3D Snapshot…")
        api.remove_workspace("studio.workspace.aerodynamics")
        for window in list(self._tool_windows):
            window.close()
        self._tool_windows.clear()
        self._latest_result = None
        self._api = None

    def _handle_analysis_result(self, result: AeroResult) -> None:
        self._latest_result = result
        if self._api is not None:
            self._api.publish("aerodynamics.analysis_completed", result)

    def _open_aero_3d_tool(self) -> None:
        if self._api is None:
            return
        window = Aero3DToolWindow(self._api, defaults=self._latest_result)
        self._tool_windows.add(window)
        window.destroyed.connect(
            lambda _object=None, tool_window=window: self._tool_windows.discard(tool_window)
        )
        window.show()
        window.raise_()
        window.activateWindow()
