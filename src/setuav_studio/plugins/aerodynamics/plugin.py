"""Aerodynamics Analysis Plugin for Setuav Studio."""
from __future__ import annotations

from typing import Any
from PySide6.QtCore import Qt

from setuav_studio.plugin_system import (
    PanelContribution,
    StudioAPI,
    WorkspaceContribution,
)
from .aero_3d_dock import Aero3DDock
from .charts_dock import (
    AeroChartsDock,
    LiftChartDock,
    PolarChartDock,
    MomentChartDock,
    LdChartDock,
)
from .controls_dock import AeroControlsDock
from .results_dock import AeroResultsDock
from .engine.base import AeroResult


class AerodynamicsPlugin:
    """Plugin providing multi-engine aerodynamic analysis, polars, 3D visualization, and curves."""

    id = "org.setuav.studio.aerodynamics"
    priority = 20

    def __init__(self) -> None:
        self._controls_dock: AeroControlsDock | None = None
        self._results_dock: AeroResultsDock | None = None
        self._charts_dock: AeroChartsDock | None = None
        self._aero_3d_dock: Aero3DDock | None = None
        self._chart_lift: LiftChartDock | None = None
        self._chart_polar: PolarChartDock | None = None
        self._chart_moment: MomentChartDock | None = None
        self._chart_ld: LdChartDock | None = None

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

        def create_aero_3d_dock() -> Aero3DDock:
            dock = Aero3DDock(api)
            self._aero_3d_dock = dock
            return dock

        def create_chart_lift() -> LiftChartDock:
            dock = LiftChartDock(api)
            self._chart_lift = dock
            return dock

        def create_chart_polar() -> PolarChartDock:
            dock = PolarChartDock(api)
            self._chart_polar = dock
            return dock

        def create_chart_moment() -> MomentChartDock:
            dock = MomentChartDock(api)
            self._chart_moment = dock
            return dock

        def create_chart_ld() -> LdChartDock:
            dock = LdChartDock(api)
            self._chart_ld = dock
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

        # 4. Register Performance Charts Dock (Center)
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

        # 5. Register Aero 3D Dock (Center/Tabbed or Right)
        api.add_panel(
            PanelContribution(
                id="aerodynamics.aero_3d",
                title="Aero 3D",
                factory=create_aero_3d_dock,
                workspace_id="studio.workspace.aerodynamics",
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                icon="fa6s.cube",
            )
        )

        # 6. Register Results Dock (Right)
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

    def deactivate(self, api: StudioAPI) -> None:
        api.remove_panel("aerodynamics.controls_dock")
        api.remove_panel("aerodynamics.results_dock")
        api.remove_panel("aerodynamics.charts_dock")
        api.remove_panel("aerodynamics.aero_3d")
        api.remove_workspace("studio.workspace.aerodynamics")
        self._controls_dock = None
        self._results_dock = None
        self._charts_dock = None
        self._aero_3d_dock = None

    def _handle_analysis_result(self, result: AeroResult) -> None:
        if self._results_dock:
            self._results_dock.display_results(result)
        if self._charts_dock:
            self._charts_dock.plot_results(result)
        if self._aero_3d_dock and result.raw and "airplane" in result.raw:
            self._aero_3d_dock.set_airplane_context(
                airplane=result.raw["airplane"],
                velocity=result.raw.get("velocity", 20.0),
                alpha=result.ld_max_alpha if result.ld_max_alpha is not None else 4.0,
            )
