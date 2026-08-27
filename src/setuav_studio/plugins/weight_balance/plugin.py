"""Weight & Balance plugin."""

from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import Qt

from setuav_studio_sdk import (
    ComponentTreeNodeContribution,
    PanelContribution,
    StudioAPI,
    ToolbarContribution,
    WorkspaceContribution,
)

from .balance_view_dock import WeightBalanceViewDock
from .engine.base import WeightBalanceError
from .engine.solver import EXTENSION_ID, WeightBalanceSolver
from .mass_definition_dock import MassPropertiesEditor
from .point_mass_editor import PointMassEditor
from .results_dock import WeightBalanceResultsDock

POINT_MASS_ICON = "fa6s.weight-scale"


class WeightBalancePlugin:
    id = "org.setuav.studio.weight_balance"
    priority = 25
    provides: ClassVar[dict[str, str]] = {EXTENSION_ID: "1.0.0"}

    def __init__(self) -> None:
        self._api: StudioAPI | None = None
        self._solver = WeightBalanceSolver()

    def activate(self, api: StudioAPI) -> None:
        self._api = api
        api.add_toolbar_item(
            ToolbarContribution(
                id="weight_balance.add_point_mass",
                title="Add Point Mass",
                callback=self._add_point_mass,
                icon=POINT_MASS_ICON,
                enabled_when=self._can_edit_project,
                group="weight-balance",
                order=100,
                workspace_id="studio.workspace.weight_balance",
            )
        )
        api.register_component_icon(
            "org.setuav.core:point-mass",
            POINT_MASS_ICON,
        )
        api.register_component_tree_provider(EXTENSION_ID, self._mass_property_nodes)
        api.register_kind_editor(
            "mass-properties",
            lambda selection: MassPropertiesEditor(api, selection),
        )
        api.register_component_editor(
            "org.setuav.core:point-mass",
            lambda component: PointMassEditor(api, component),
        )
        api.add_workspace(
            WorkspaceContribution(
                id="studio.workspace.weight_balance",
                title="Weight-Balance",
                order=10,
            )
        )
        api.add_panel(
            PanelContribution(
                id="weight_balance.view_dock",
                title="CG View",
                factory=lambda: WeightBalanceViewDock(api),
                workspace_id="studio.workspace.weight_balance",
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                icon="fa6s.crosshairs",
            )
        )
        api.add_panel(
            PanelContribution(
                id="weight_balance.results_dock",
                title="Mass Properties",
                factory=lambda: WeightBalanceResultsDock(api),
                workspace_id="studio.workspace.weight_balance",
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                icon="fa6s.table-list",
            )
        )
        api.on_project_changed(self._project_changed)
        api.on_project_content_changed(self._project_changed)

    def deactivate(self, api: StudioAPI) -> None:
        api.remove_toolbar_item("weight_balance.add_point_mass")
        api.remove_panel("weight_balance.view_dock")
        api.remove_panel("weight_balance.results_dock")
        api.remove_workspace("studio.workspace.weight_balance")
        api.remove_project_listener(self._project_changed)
        api.remove_project_content_listener(self._project_changed)
        api.remove_kind_editor("mass-properties")
        api.remove_component_editor("org.setuav.core:point-mass")
        api.remove_component_icon("org.setuav.core:point-mass")
        api.remove_component_tree_provider(EXTENSION_ID)
        self._api = None

    def _can_edit_project(self) -> bool:
        project = self._api.current_project if self._api is not None else None
        return project is not None and not project.read_only

    def _add_point_mass(self) -> None:
        """Create a starter point mass in the active project."""
        api = self._api
        project = api.current_project if api is not None else None
        if api is None or project is None:
            if api is not None:
                api.show_status("Open a project before adding a point mass", "warning")
            return
        if project.read_only:
            api.show_status("The project is read-only", "warning")
            return

        components = project.data.get("components")
        if not isinstance(components, list):
            api.show_status("Project components are invalid", "error")
            return

        existing_ids = {
            str(item.get("id")) for item in components if isinstance(item, dict) and item.get("id")
        }
        existing_names = {
            str(item.get("name"))
            for item in components
            if isinstance(item, dict) and item.get("name")
        }
        base_id = "point-mass"
        base_name = "Point Mass"
        suffix = 1
        component_id = base_id
        component_name = base_name
        while component_id in existing_ids or component_name in existing_names:
            suffix += 1
            component_id = f"{base_id}-{suffix}"
            component_name = f"{base_name} {suffix}"

        component = {
            "kind": "component",
            "id": component_id,
            "name": component_name,
            "type": "org.setuav.core:point-mass",
            "parent": None,
            "transform": {
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            },
            "parameters": {
                "mass": 100.0,
                "inertia": {
                    "ixx": 0.0,
                    "iyy": 0.0,
                    "izz": 0.0,
                    "ixy": 0.0,
                    "ixz": 0.0,
                    "iyz": 0.0,
                },
            },
            "mass": 100.0,
        }

        def change() -> None:
            components.append(component)

        api.edit_project("Add point mass", change)
        api.set_selection(component)
        api.show_status(f"Created {component_name}", "success", 3000)

    @staticmethod
    def _mass_property_nodes(
        component: dict,
    ) -> tuple[ComponentTreeNodeContribution, ...]:
        component_id = str(component.get("id") or "")
        if not component_id:
            return ()
        node_id = f"{component_id}:mass-properties"
        return (
            ComponentTreeNodeContribution(
                id=node_id,
                title="Mass",
                selection={
                    "id": node_id,
                    "name": "Mass",
                    "kind": "mass-properties",
                    "component_id": component_id,
                },
                icon="fa6s.cubes-stacked",
                tooltip=f"Mass, local CG and inertia for {component.get('name') or component_id}",
            ),
        )

    def run_analysis(self) -> None:
        if self._api is None or self._api.current_project is None:
            return
        try:
            result = self._solver.evaluate(self._api.current_project)
        except WeightBalanceError as exc:
            self._api.show_status(str(exc), "error", 8000)
            return
        self._api.publish("weight_balance.analysis_completed", result)
        level = "warning" if result.warnings else "success"
        self._api.show_status(
            f"Weight-Balance complete: {result.total.mass_kg:.3f} kg, "
            f"CG X={result.total.cg_body_m[0] * 1000.0:+.1f} mm "
            f"({len(result.warnings)} warning(s))",
            level,
            8000,
        )

    def _project_changed(self, _project) -> None:
        self.run_analysis()
