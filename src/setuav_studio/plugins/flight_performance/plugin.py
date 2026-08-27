"""Flight Performance Analysis Plugin for Setuav Studio."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from setuav_studio_sdk import (
    PanelContribution,
    ProjectTreeNodeContribution,
    StudioAPI,
    WorkspaceContribution,
)

from setuav_studio.project import ProjectDocument

from .analysis_store import (
    EXTENSION_ID,
    RESULT_SELECTION_KIND,
    RESULTS_GROUP_ID,
    analysis_entries,
    delete_analysis_entry,
    performance_selection,
    rename_analysis_entry,
)
from .charts_dock import PerformanceChartsDock
from .controls_dock import PerformanceControlsDock
from .engine.models import FlightEnvelopeResult
from .results_dock import PerformanceResultsDock


class FlightPerformancePlugin:
    """Plugin providing coupled fixed-wing flight envelope, optimal speeds, climb, range, and endurance analysis."""

    id = "org.setuav.studio.flight_performance"
    priority = 25

    def __init__(self) -> None:
        self._api: StudioAPI | None = None

    def activate(self, api: StudioAPI) -> None:
        self._api = api

        # 1. Register Project Tree Provider
        api.register_project_tree_provider(self.id, self._project_tree_nodes)

        # 2. Register Selection Listener to restore saved results on tree click
        api.on_selection_changed(self._on_selection_changed)

        # 3. Register Flight Performance Workspace
        api.add_workspace(
            WorkspaceContribution(
                id="studio.workspace.flight_performance",
                order=25,
                title="Performance",
            )
        )

        # 4. Register Controls Dock (Left dock)
        api.add_panel(
            PanelContribution(
                id="flight_performance.controls_dock",
                title="Performance Controls",
                factory=lambda: PerformanceControlsDock(api),
                workspace_id="studio.workspace.flight_performance",
                area=Qt.DockWidgetArea.LeftDockWidgetArea,
                icon="fa6s.sliders",
            )
        )

        # 5. Register Charts Dock (Right dock)
        api.add_panel(
            PanelContribution(
                id="flight_performance.charts_dock",
                title="Performance Curves",
                factory=lambda: PerformanceChartsDock(api),
                workspace_id="studio.workspace.flight_performance",
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                icon="fa6s.chart-line",
            )
        )

        # 6. Register Results Dock (Right dock)
        api.add_panel(
            PanelContribution(
                id="flight_performance.results_dock",
                title="Flight Summary",
                factory=lambda: PerformanceResultsDock(api),
                workspace_id="studio.workspace.flight_performance",
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                icon="fa6s.table-list",
            )
        )

    def deactivate(self, api: StudioAPI) -> None:
        api.remove_selection_listener(self._on_selection_changed)
        api.remove_project_tree_provider(self.id)
        api.remove_panel("flight_performance.controls_dock")
        api.remove_panel("flight_performance.charts_dock")
        api.remove_panel("flight_performance.results_dock")
        api.remove_workspace("studio.workspace.flight_performance")
        self._api = None

    def _on_selection_changed(self, selection: dict[str, Any] | None) -> None:
        if not selection or not isinstance(selection, dict):
            return
        if selection.get("kind") != RESULT_SELECTION_KIND:
            return
        analysis_id = str(selection.get("id") or "")
        if not analysis_id or not self._api or not self._api.current_project:
            return

        for entry in analysis_entries(self._api.current_project):
            if str(entry.get("id")) == analysis_id:
                payload = entry.get("result")
                if isinstance(payload, dict):
                    try:
                        res = FlightEnvelopeResult.from_dict(payload)
                        self._api.publish("flight_performance.analysis_completed", res)
                    except Exception:
                        pass
                return

    def _delete_analysis(self, analysis_id: str) -> None:
        if self._api and self._api.current_project:
            self._api.edit_project_extension(
                EXTENSION_ID,
                "Delete flight performance analysis",
                lambda ext: delete_analysis_entry(ext, analysis_id),
            )

    def _delete_all_analyses(self) -> None:
        if self._api and self._api.current_project:
            self._api.edit_project_extension(
                EXTENSION_ID,
                "Delete all flight performance analyses",
                lambda ext: ext.update({"results": []}),
            )

    def _rename_analysis(self, analysis_id: str, new_name: str) -> None:
        if self._api and self._api.current_project:
            self._api.edit_project_extension(
                EXTENSION_ID,
                f"Rename flight performance analysis to '{new_name}'",
                lambda ext: rename_analysis_entry(ext, analysis_id, new_name),
            )

    def _project_tree_nodes(
        self,
        project: ProjectDocument,
    ) -> tuple[ProjectTreeNodeContribution, ...]:
        analysis_nodes: list[ProjectTreeNodeContribution] = []
        for entry in analysis_entries(project):
            analysis_id = str(entry.get("id") or "")
            payload = entry.get("result")
            if not analysis_id or not isinstance(payload, dict):
                continue

            name = str(entry.get("name") or "Flight Envelope")
            met = payload.get("metrics", {})
            opt = payload.get("optimal_speeds", {})

            v_stall = float(met.get("stall_speed", 0.0))
            v_cruise = float(opt.get("best_range", 0.0))
            max_range = float(met.get("max_range_km", 0.0))
            max_roc = float(met.get("max_rate_of_climb", 0.0))
            created_at = str(entry.get("created_at") or "")

            sel = performance_selection(analysis_id)

            tooltip_lines = [
                name,
                f"V_stall: {v_stall:.1f} m/s ({v_stall * 3.6:.1f} km/h)",
                f"V_cruise: {v_cruise:.1f} m/s ({v_cruise * 3.6:.1f} km/h)",
                f"Max Range: {max_range:.1f} km · ROC_max: {max_roc:.2f} m/s",
            ]
            if created_at:
                tooltip_lines.append(f"Created: {created_at}")

            analysis_nodes.append(
                ProjectTreeNodeContribution(
                    id=f"flight_performance.analysis-result.{analysis_id}",
                    title=name,
                    selection=sel,
                    icon="fa6s.gauge-high",
                    tooltip="\n".join(tooltip_lines),
                    delete=lambda aid=analysis_id: self._delete_analysis(aid),
                    rename=lambda n, aid=analysis_id: self._rename_analysis(aid, n),
                )
            )

        if not analysis_nodes:
            return ()

        return (
            ProjectTreeNodeContribution(
                id=RESULTS_GROUP_ID,
                title="Performance Analyses",
                selection={"id": RESULTS_GROUP_ID, "kind": "flight-performance-results"},
                children=tuple(analysis_nodes),
                icon="fa6s.gauge-high",
                tooltip="Saved flight performance envelopes",
                delete=self._delete_all_analyses,
            ),
        )
