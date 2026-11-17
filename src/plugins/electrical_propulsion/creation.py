"""Toolbar commands for adding propulsors and battery packs."""

from __future__ import annotations

from typing import Any

from plugins.electrical_propulsion.models.battery import BatteryModel, battery_pack
from plugins.electrical_propulsion.models.propulsor import (
    PROPULSOR_TYPE,
    PropulsorModel,
    propulsor_mass,
)
from setuav_studio.api import (
    StudioAPI,
    ToolbarContribution,
    ToolbarMenuItemContribution,
)

_BATTERY_TYPE = "org.setuav.core:battery"


class PropulsionCreationController:
    """Add propulsors and battery packs to the vehicle."""

    toolbar_id = "propulsion.add-component"

    def __init__(self, api: StudioAPI) -> None:
        self._api = api

    def contributions(self) -> tuple[ToolbarContribution, ...]:
        return (
            ToolbarContribution(
                id=self.toolbar_id,
                title="Add Propulsion Component",
                icon="add",
                menu_items=(
                    ToolbarMenuItemContribution(
                        title="Add Propulsor",
                        callback=self.add_propulsor,
                        icon="component",
                        enabled_when=self._can_edit_project,
                    ),
                    ToolbarMenuItemContribution(
                        title="Add Battery",
                        callback=self.add_battery,
                        icon="component",
                        enabled_when=self._can_edit_project,
                    ),
                ),
                enabled_when=self._can_edit_project,
                group="propulsion-creation",
                order=110,
            ),
        )

    def add_propulsor(self) -> None:
        """Add a propulsor; its motor and propeller are picked on their own pages."""
        if not self._require_editable_project():
            return
        component_id, name = self._unique_identity("propulsor", "Propulsor")
        self._add(new_propulsor(component_id, name))

    def add_battery(self) -> None:
        """Add a battery pack with the default chemistry and cell."""
        if not self._require_editable_project():
            return
        component_id, name = self._unique_identity("battery", "Battery")
        self._add(new_battery(component_id, name))

    def _add(self, component: dict[str, Any]) -> None:
        project = self._api.project
        if project is None:
            return

        def change() -> None:
            project.data["components"].append(component)

        self._api.edit_project(f"Add {component['name']}", change)
        created = self._find_component(component["id"])
        if created is not None:
            self._api.set_selection(created)
            self._api.show_status(f"Added {component['name']}", "success", 3000)

    def _unique_identity(self, base_id: str, base_name: str) -> tuple[str, str]:
        project = self._api.project
        if project is None:
            return base_id, base_name
        components = [c for c in project.data["components"] if isinstance(c, dict)]
        ids = {str(item.get("id") or "") for item in components}
        names = {str(item.get("name") or "") for item in components}
        if base_id not in ids and base_name not in names:
            return base_id, base_name
        suffix = 2
        while f"{base_id}-{suffix}" in ids or f"{base_name} {suffix}" in names:
            suffix += 1
        return f"{base_id}-{suffix}", f"{base_name} {suffix}"

    def _can_edit_project(self) -> bool:
        project = self._api.project
        return project is not None and not project.read_only

    def _require_editable_project(self) -> bool:
        project = self._api.project
        if project is None:
            self._api.show_status("Open a project before adding propulsion components", "warning")
            return False
        if project.read_only:
            self._api.show_status("The project is read-only", "warning")
            return False
        return True

    def _find_component(self, component_id: str) -> dict[str, Any] | None:
        project = self._api.project
        if project is None:
            return None
        return next(
            (
                component
                for component in project.data["components"]
                if isinstance(component, dict) and component.get("id") == component_id
            ),
            None,
        )


def new_propulsor(component_id: str, name: str) -> dict[str, Any]:
    """Return a propulsor with no motor or propeller picked yet."""
    params = PropulsorModel.default_parameters()
    return {
        "kind": "component",
        "id": component_id,
        "name": name,
        "type": PROPULSOR_TYPE,
        "mass": propulsor_mass(params),
        "transform": _origin_transform(),
        "parameters": params,
    }


def new_battery(component_id: str, name: str) -> dict[str, Any]:
    """Return a battery pack component with the default chemistry and cell."""
    params = BatteryModel.default_parameters()
    return {
        "kind": "component",
        "id": component_id,
        "name": name,
        "type": _BATTERY_TYPE,
        "mass": battery_pack(params).mass_g,
        "transform": _origin_transform(),
        "envelope": {
            "shape": "box",
            "size_mm": {"x": 150.0, "y": 50.0, "z": 50.0},
            "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "parameters": params,
    }


def _origin_transform() -> dict[str, Any]:
    return {
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
    }


__all__ = ["PropulsionCreationController", "new_battery", "new_propulsor"]
