"""Aerodynamics Analysis Plugin for Setuav Studio."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt

from setuav_studio.plugin_system import (
    PanelContribution,
    ProjectTreeNodeContribution,
    StudioAPI,
    ToolContribution,
    WorkspaceContribution,
)
from setuav_studio.project import ProjectDocument
from .charts_dock import AeroChartsDock
from .controls_dock import AeroControlsDock
from .results_dock import AeroResultsDock
from .engine.base import AeroResult
from .analysis_store import (
    EXTENSION_ID,
    RESULTS_VERSION,
    RESULTS_GROUP_ID,
    analysis_entries,
    analysis_selection,
    append_analysis_entry,
    make_analysis_entry,
    migrate_analysis_extension,
    rename_analysis_entry,
    short_result_name,
)
if TYPE_CHECKING:
    from .aero_3d_tool import Aero3DToolWindow
    from .airfoil_analysis_tool import AirfoilAnalysisToolWindow


class AerodynamicsPlugin:
    """Plugin providing aerodynamic analysis, persisted results, and curves."""

    id = "org.setuav.studio.aerodynamics"
    priority = 20

    def __init__(self) -> None:
        self._api: StudioAPI | None = None
        self._latest_result: AeroResult | None = None
        self._tool_windows: set[
            Aero3DToolWindow | AirfoilAnalysisToolWindow
        ] = set()

    def activate(self, api: StudioAPI) -> None:
        self._api = api
        api.register_project_tree_provider(self.id, self._project_tree_nodes)
        api.on_project_changed(self._migrate_project_results)
        if api.current_project is not None:
            self._migrate_project_results(api.current_project)

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
        api.register_tool(
            ToolContribution(
                group="Aerodynamics",
                title="Airfoil Analysis…",
                callback=self._open_airfoil_analysis_tool,
                icon="fa6s.chart-area",
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
        api.remove_project_listener(self._migrate_project_results)
        api.remove_project_tree_provider(self.id)
        api.remove_panel("aerodynamics.controls_dock")
        api.remove_panel("aerodynamics.results_dock")
        api.remove_panel("aerodynamics.charts_dock")
        api.remove_action("Tools/Aerodynamics", "AeroSandbox 3D Snapshot…")
        api.remove_action("Tools/Aerodynamics", "Airfoil Analysis…")
        api.remove_workspace("studio.workspace.aerodynamics")
        for window in list(self._tool_windows):
            window.close()
        self._tool_windows.clear()
        self._latest_result = None
        self._api = None

    def _migrate_project_results(self, project: ProjectDocument) -> None:
        if self._api is None or project.read_only:
            return
        extension = project.get_extension(EXTENSION_ID)
        if not isinstance(extension, dict) or not isinstance(
            extension.get("results"), list
        ):
            return
        if extension.get("results_version") == RESULTS_VERSION:
            return
        self._api.edit_project_extension(
            EXTENSION_ID,
            "Migrate aerodynamic analysis results",
            migrate_analysis_extension,
        )

    def _handle_analysis_result(self, result: AeroResult) -> None:
        if not result.polar_points or result.converged_point_count == 0:
            if self._api is not None:
                self._api.show_status(
                    "Aerodynamic result was discarded: no converged operating points",
                    "error",
                )
            return
        self._latest_result = result
        if self._api is not None:
            entry = None
            project = self._api.current_project
            if project is not None and not project.read_only:
                entry = make_analysis_entry(result)
                self._api.edit_project_extension(
                    EXTENSION_ID,
                    f"Store aerodynamic analysis: {entry['name']}",
                    lambda extension: append_analysis_entry(extension, entry),
                )
            self._api.publish("aerodynamics.analysis_completed", result)
            if entry is not None:
                self._api.set_selection(analysis_selection(str(entry["id"])))

    def _project_tree_nodes(
        self,
        project: ProjectDocument,
    ) -> tuple[ProjectTreeNodeContribution, ...]:
        children: list[ProjectTreeNodeContribution] = []
        for entry in analysis_entries(project):
            analysis_id = str(entry.get("id") or "")
            payload = entry.get("result")
            if not analysis_id or not isinstance(payload, dict):
                continue
            name = short_result_name(
                str(entry.get("name") or "Aerodynamic Analysis")
            )
            method = str(payload.get("method") or "").replace("_", " ").upper()
            points = payload.get("polar_points")
            point_count = len(points) if isinstance(points, list) else 0
            created_at = str(entry.get("created_at") or "")
            children.append(
                ProjectTreeNodeContribution(
                    id=f"aerodynamics.analysis-result.{analysis_id}",
                    title=name,
                    selection=analysis_selection(analysis_id),
                    icon="fa6s.chart-line",
                    tooltip=(
                        f"{name}\n{method} · {point_count} result point(s)"
                        + (f"\n{created_at}" if created_at else "")
                    ),
                    rename=lambda new_name, result_id=analysis_id: self._rename_result(
                        result_id,
                        new_name,
                    ),
                )
            )
        if not children:
            return ()
        return (
            ProjectTreeNodeContribution(
                id=RESULTS_GROUP_ID,
                title="Aero Analyses",
                selection={"id": RESULTS_GROUP_ID, "kind": "aerodynamics-results"},
                children=tuple(children),
                icon="fa6s.wind",
                tooltip="Saved aerodynamic analysis results",
            ),
        )

    def _rename_result(self, analysis_id: str, name: str) -> None:
        if self._api is None:
            return
        self._api.edit_project_extension(
            EXTENSION_ID,
            f"Rename aerodynamic analysis to {name}",
            lambda extension: rename_analysis_entry(extension, analysis_id, name),
        )

    def _open_aero_3d_tool(self) -> None:
        if self._api is None:
            return
        # Keep the module unloaded until the UI tool is requested. The
        # detached renderer executes this module with ``python -m``; importing
        # it during package initialization makes runpy execute it a second time.
        from .aero_3d_tool import Aero3DToolWindow

        window = Aero3DToolWindow(self._api, defaults=self._latest_result)
        self._tool_windows.add(window)
        window.destroyed.connect(
            lambda _object=None, tool_window=window: self._tool_windows.discard(tool_window)
        )
        window.show()
        window.raise_()
        window.activateWindow()

    def _open_airfoil_analysis_tool(self) -> None:
        if self._api is None:
            return
        from .airfoil_analysis_tool import AirfoilAnalysisToolWindow

        window = AirfoilAnalysisToolWindow(self._api)
        self._tool_windows.add(window)
        window.destroyed.connect(
            lambda _object=None, tool_window=window: self._tool_windows.discard(
                tool_window
            )
        )
        window.show()
        window.raise_()
        window.activateWindow()
