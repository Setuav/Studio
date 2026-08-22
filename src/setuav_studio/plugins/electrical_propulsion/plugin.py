"""Electrical Propulsion Plugin for Setuav Studio."""

from __future__ import annotations

from PySide6.QtCore import Qt

from setuav_studio.plugin_system import (
    PanelContribution,
    StudioAPI,
    ToolContribution,
    WorkspaceContribution,
)
from .creation import PropulsionCreationController
from .catalog_dialog import ComponentCatalogDialog
from .charts_dock import PropulsionChartsDock
from .controls_dock import PropulsionControlsDock
from .results_dock import PropulsionResultsDock
from .editors.assembly import ElectricPropulsionSystemEditor
from .editors.battery import BatteryEditor
from .editors.esc import EscEditor
from .editors.motor import MotorEditor
from .editors.propeller import PropellerEditor


class ElectricalPropulsionPlugin:
    """Plugin providing electrical propulsion component editors, icons, database, and assemblies."""

    id = "org.setuav.studio.electrical_propulsion"

    def activate(self, api: StudioAPI) -> None:
        self._creation_controller = PropulsionCreationController(api)
        for contribution in self._creation_controller.contributions():
            api.add_toolbar_item(contribution)

        # Register Component Editors
        api.register_component_editor(
            "org.setuav.core:motor",
            lambda comp: MotorEditor(api, comp),
        )
        api.register_component_editor(
            "org.setuav.core:propeller",
            lambda comp: PropellerEditor(api, comp),
        )
        api.register_component_editor(
            "org.setuav.core:rotor",
            lambda comp: PropellerEditor(api, comp),
        )
        api.register_component_editor(
            "org.setuav.core:esc",
            lambda comp: EscEditor(api, comp),
        )
        api.register_component_editor(
            "org.setuav.core:battery",
            lambda comp: BatteryEditor(api, comp),
        )
        api.register_component_editor(
            "org.setuav.core:electric-propulsion-system",
            lambda comp: ElectricPropulsionSystemEditor(api, comp),
        )

        # Register Component & Assembly Icons
        api.register_component_icon("org.setuav.core:motor", "component_motor")
        api.register_component_icon("org.setuav.core:propeller", "component_propeller")
        api.register_component_icon("org.setuav.core:rotor", "component_rotor")
        api.register_component_icon("org.setuav.core:esc", "component_esc")
        api.register_component_icon("org.setuav.core:battery", "component_battery")
        api.register_component_icon(
            "org.setuav.core:electric-propulsion-system",
            "component_propulsion_system",
        )

        # Register Propulsion Workspace
        api.add_workspace(
            WorkspaceContribution(
                id="studio.workspace.propulsion",
                title="Propulsion",
                order=20,
            )
        )

        # Register Propulsion Controls Dock (Left dock in Propulsion workspace)
        api.add_panel(
            PanelContribution(
                id="propulsion.controls_dock",
                title="Propulsion Controls",
                factory=lambda: PropulsionControlsDock(api),
                workspace_id="studio.workspace.propulsion",
                area=Qt.DockWidgetArea.LeftDockWidgetArea,
                icon="fa6s.gear",
            )
        )

        # Register Propulsion Charts Dock (Center/Right dock in Propulsion workspace)
        api.add_panel(
            PanelContribution(
                id="propulsion.charts_dock",
                title="Performance Charts",
                factory=lambda: PropulsionChartsDock(api),
                workspace_id="studio.workspace.propulsion",
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                icon="fa6s.chart-line",
            )
        )

        # Register Propulsion Results Dock (Right dock in Propulsion workspace)
        api.add_panel(
            PanelContribution(
                id="propulsion.results_dock",
                title="Propulsion Results",
                factory=lambda: PropulsionResultsDock(api),
                workspace_id="studio.workspace.propulsion",
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                icon="fa6s.table-list",
            )
        )

        # Register Tools in Tools menu
        def open_component_database() -> None:
            dialog = ComponentCatalogDialog(component_type="all")
            dialog.exec()

        api.register_tool(
            ToolContribution(
                group="Electrical Propulsion",
                title="Component Database…",
                callback=open_component_database,
                icon="fa6s.database",
            )
        )

    def deactivate(self, api: StudioAPI) -> None:
        controller = getattr(self, "_creation_controller", None)
        if controller is not None:
            for contribution_id in controller.toolbar_ids:
                api.remove_toolbar_item(contribution_id)
        api.remove_panel("propulsion.controls_dock")
        api.remove_panel("propulsion.results_dock")
        api.remove_panel("propulsion.charts_dock")
        api.remove_workspace("studio.workspace.propulsion")
