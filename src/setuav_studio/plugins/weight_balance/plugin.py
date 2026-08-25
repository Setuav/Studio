"""Weight & Balance plugin."""

from __future__ import annotations

from PySide6.QtCore import Qt

from setuav_studio.plugin_system import (
    ComponentTreeNodeContribution,
    PanelContribution,
    StudioAPI,
    WorkspaceContribution,
)

from .balance_view_dock import WeightBalanceViewDock
from .engine.base import WeightBalanceError
from .engine.solver import EXTENSION_ID, WeightBalanceSolver
from .mass_definition_dock import MassPropertiesEditor
from .results_dock import WeightBalanceResultsDock


class WeightBalancePlugin:
    id = "org.setuav.studio.weight_balance"
    priority = 25
    provides = {EXTENSION_ID: "1.0.0"}

    def __init__(self) -> None:
        self._api: StudioAPI | None = None
        self._solver = WeightBalanceSolver()

    def activate(self, api: StudioAPI) -> None:
        self._api = api
        api.register_mass_properties_provider(EXTENSION_ID, self._solver)
        api.register_component_tree_provider(EXTENSION_ID, self._mass_property_nodes)
        api.register_kind_editor(
            "mass-properties",
            lambda selection: MassPropertiesEditor(api, selection),
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
        api.remove_panel("weight_balance.view_dock")
        api.remove_panel("weight_balance.results_dock")
        api.remove_workspace("studio.workspace.weight_balance")
        api.remove_project_listener(self._project_changed)
        api.remove_project_content_listener(self._project_changed)
        api.remove_kind_editor("mass-properties")
        api.remove_component_tree_provider(EXTENSION_ID)
        api.remove_mass_properties_provider(EXTENSION_ID)
        self._api = None

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
