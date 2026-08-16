"""Electrical Propulsion Plugin for Setuav Studio."""

from __future__ import annotations

from typing import Any
from PySide6.QtWidgets import QWidget

from setuav_studio.plugin_system import StudioAPI, ToolContribution
from .catalog_dialog import ComponentCatalogDialog
from .editors.assembly import ElectricPropulsionSystemEditor
from .editors.battery import BatteryEditor
from .editors.esc import EscEditor
from .editors.motor import MotorEditor
from .editors.propeller import PropellerEditor


class ElectricalPropulsionPlugin:
    """Plugin providing electrical propulsion component editors, icons, database, and assemblies."""

    id = "org.setuav.studio.electrical_propulsion"

    def activate(self, api: StudioAPI) -> None:
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
        api.register_component_icon("org.setuav.core:motor", "mdi6.engine")
        api.register_component_icon("org.setuav.core:propeller", "fa6s.fan")
        api.register_component_icon("org.setuav.core:rotor", "fa6s.fan")
        api.register_component_icon("org.setuav.core:esc", "fa6s.microchip")
        api.register_component_icon("org.setuav.core:battery", "fa6s.battery-full")
        api.register_component_icon(
            "org.setuav.core:electric-propulsion-system",
            "fa6s.bolt",
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
