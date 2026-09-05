"""Preliminary Sizing and Matching Chart Plugin for SetUAV Studio."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt

from plugins.sizing.engine.aerodynamics import AeroParameters
from plugins.sizing.engine.battery import BatteryParameters
from plugins.sizing.engine.solver import MatchingChartAnalysis, solve_sizing_for_mission
from plugins.sizing.engine.weight import MissionProfile, SizingResult, converge_sizing
from plugins.sizing.ui.matching_chart import SizingChartDock
from plugins.sizing.ui.requirements_dock import SizingRequirementsDock
from plugins.sizing.ui.results_dock import SizingResultsDock
from setuav_studio_sdk import (
    PanelContribution,
    StudioAPI,
    WorkspaceContribution,
    WorkspaceLayoutContext,
)

logger = logging.getLogger(__name__)

SIZING_WORKSPACE_ID = "studio.workspace.sizing"
REQUIREMENTS_DOCK_ID = "sizing.requirements_dock"
CHART_DOCK_ID = "sizing.chart_dock"
RESULTS_DOCK_ID = "sizing.results_dock"


def _apply_sizing_workspace_layout(layout: WorkspaceLayoutContext) -> None:
    """Configure the initial sizing workspace arrangement."""
    layout.hide("studio.viewer.opengl", "studio.properties")
    layout.split("project.explorer", REQUIREMENTS_DOCK_ID)
    layout.split(REQUIREMENTS_DOCK_ID, CHART_DOCK_ID)
    layout.split(CHART_DOCK_ID, RESULTS_DOCK_ID)
    layout.show(
        "project.explorer",
        REQUIREMENTS_DOCK_ID,
        CHART_DOCK_ID,
        RESULTS_DOCK_ID,
    )
    layout.resize(
        (
            "project.explorer",
            REQUIREMENTS_DOCK_ID,
            CHART_DOCK_ID,
            RESULTS_DOCK_ID,
        ),
        (220, 270, 560, 310),
    )


class SizingPlugin:
    """Preliminary Sizing & Requirements Plugin."""

    id = "org.setuav.studio.sizing"
    priority = 10  # Conceptual sizing comes before detailed geometry

    def __init__(self) -> None:
        self._api: StudioAPI | None = None
        self._requirements_dock: SizingRequirementsDock | None = None
        self._chart_dock: SizingChartDock | None = None
        self._results_dock: SizingResultsDock | None = None
        self._last_analysis: MatchingChartAnalysis | None = None
        self._last_mission: MissionProfile | None = None
        self._last_aero: AeroParameters | None = None
        self._last_battery: BatteryParameters | None = None

    def activate(self, api: StudioAPI) -> None:
        """Register sizing workspace, panels, and event bridges."""
        self._api = api

        # 1. Register Workspace
        api.add_workspace(
            WorkspaceContribution(
                id=SIZING_WORKSPACE_ID,
                order=5,
                title="Sizing",
                default_layout=_apply_sizing_workspace_layout,
            )
        )

        # 2. Register Requirements Dock (Left)
        api.add_panel(
            PanelContribution(
                id=REQUIREMENTS_DOCK_ID,
                title="Sizing Requirements",
                factory=self._get_or_create_requirements_dock,
                workspace_id=SIZING_WORKSPACE_ID,
                area=Qt.DockWidgetArea.LeftDockWidgetArea,
                icon="fa6s.crosshairs",
            )
        )

        # 3. Register Matching Chart Dock (Center)
        api.add_panel(
            PanelContribution(
                id=CHART_DOCK_ID,
                title="Matching Chart",
                factory=self._get_or_create_chart_dock,
                workspace_id=SIZING_WORKSPACE_ID,
                area=Qt.DockWidgetArea.LeftDockWidgetArea,
                icon="fa6s.chart-area",
            )
        )

        # 4. Register Results Dock (Right)
        api.add_panel(
            PanelContribution(
                id=RESULTS_DOCK_ID,
                title="Sizing Results",
                factory=self._get_or_create_results_dock,
                workspace_id=SIZING_WORKSPACE_ID,
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                icon="fa6s.calculator",
            )
        )

        # Trigger initial solve after UI initialization
        self._run_initial_solve()

    def _get_or_create_requirements_dock(self) -> SizingRequirementsDock:
        if self._requirements_dock is None:
            self._requirements_dock = SizingRequirementsDock(self._api)
            self._requirements_dock.requirements_changed.connect(self._on_requirements_changed)
        return self._requirements_dock

    def _get_or_create_chart_dock(self) -> SizingChartDock:
        if self._chart_dock is None:
            self._chart_dock = SizingChartDock()
            self._chart_dock.chart_widget.design_point_changed.connect(self._on_design_point_changed)
        return self._chart_dock

    def _get_or_create_results_dock(self) -> SizingResultsDock:
        if self._results_dock is None:
            self._results_dock = SizingResultsDock(self._api)
            self._results_dock.apply_to_project_requested.connect(self._apply_to_project)
        return self._results_dock

    def _run_initial_solve(self) -> None:
        req_dock = self._get_or_create_requirements_dock()
        mission, aero, battery = req_dock.get_current_configuration()
        self._on_requirements_changed(mission, aero, battery)

    def _on_requirements_changed(
        self,
        mission: MissionProfile,
        aero: AeroParameters,
        battery: BatteryParameters,
    ) -> None:
        """Re-solve constraints and sizing when user tweaks requirements."""
        self._last_mission = mission
        self._last_aero = aero
        self._last_battery = battery

        chart_analysis, sizing_result = solve_sizing_for_mission(
            mission=mission,
            aero=aero,
        )
        self._last_analysis = chart_analysis

        chart_dock = self._get_or_create_chart_dock()
        chart_dock.chart_widget.plot_analysis(chart_analysis)

        results_dock = self._get_or_create_results_dock()
        results_dock.set_results(sizing_result)

        if self._api:
            self._api.publish("sizing.analysis_completed", sizing_result)

    def _on_design_point_changed(self, ws_selected: float, pw_selected: float) -> None:
        """Re-run mass convergence when user interacts with matching chart."""
        if not self._last_mission or not self._last_aero or not self._last_analysis:
            return

        try:
            new_sizing = converge_sizing(
                mission=self._last_mission,
                aero=self._last_aero,
                design_wing_loading_pa=ws_selected,
                design_power_loading_wn=pw_selected,
                atmosphere=self._last_analysis.atmosphere,
                battery_params=self._last_battery,
            )
            results_dock = self._get_or_create_results_dock()
            results_dock.set_results(new_sizing)

            if self._api:
                self._api.publish("sizing.analysis_completed", new_sizing)
        except Exception:
            pass

    def _apply_to_project(self, result: SizingResult) -> None:
        """Write sized parameters to project extensions and parameters."""
        if not self._api:
            return

        project = self._api.project
        if not project:
            return

        def _update_extension(data: dict[str, Any]) -> None:
            data["sizing"] = {
                "mtow_kg": result.weights.mtow_kg,
                "empty_mass_kg": result.weights.empty_mass_kg,
                "payload_mass_kg": result.weights.payload_mass_kg,
                "battery_mass_kg": result.weights.battery_mass_kg,
                "wing_area_m2": result.wing_area_m2,
                "wingspan_m": result.wingspan_m,
                "mean_chord_m": result.mean_chord_m,
                "max_shaft_power_w": result.max_shaft_power_w,
                "cruise_shaft_power_w": result.cruise_shaft_power_w,
                "wing_loading_pa": result.wing_loading_pa,
                "power_loading_wn": result.power_loading_wn,
                "battery_capacity_mah": result.battery.capacity_mah,
                "battery_cells_s": result.battery.cell_count_s,
            }

        try:
            self._api.edit_project_extension(
                self.id,
                "Apply Preliminary Sizing",
                _update_extension,
            )
            logger.info("Successfully applied preliminary sizing to project.")
        except Exception as exc:
            logger.warning("Could not apply sizing to project extension: %s", exc)


__all__ = ["SizingPlugin"]
