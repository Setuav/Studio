"""Toolbar commands for creating electrical propulsion components and root system."""

from __future__ import annotations

from typing import Any

from plugins.electrical_propulsion.models.battery import BatteryModel, battery_pack_mass
from setuav_studio.api import (
    StudioAPI,
    ToolbarContribution,
    ToolbarMenuItemContribution,
)

_PROPULSION_TYPE = "org.setuav.core:propulsion-system"
_PROPULSION_ID = "propulsion"
_PROPULSION_NAME = "Propulsion"

_COMPONENT_SPECS: dict[str, tuple[str, str, str]] = {
    "battery": ("org.setuav.core:battery", "Battery", "component"),
    "esc": ("org.setuav.core:esc", "ESC", "component"),
    "motor": ("org.setuav.core:motor", "Motor", "component"),
    "propeller": (
        "org.setuav.core:propeller",
        "Propeller",
        "component",
    ),
    "rotor": ("org.setuav.core:rotor", "Rotor", "component"),
}


def create_default_propulsion_component() -> dict[str, Any]:
    return {
        "kind": "component",
        "id": _PROPULSION_ID,
        "name": _PROPULSION_NAME,
        "type": _PROPULSION_TYPE,
        "parent": None,
        "parameters": {},
        "has_transform": False,
        "has_mass": False,
    }


class PropulsionCreationController:
    """Create electrical propulsion system and components."""

    toolbar_ids = (
        "propulsion.add-system",
        "propulsion.add-component",
    )

    def __init__(self, api: StudioAPI) -> None:
        self._api = api

    def contributions(self) -> tuple[ToolbarContribution, ...]:
        return (
            ToolbarContribution(
                id=self.toolbar_ids[0],
                title="Add Electrical Propulsion",
                icon="component_propulsion_system",
                callback=self.add_propulsion_system,
                enabled_when=self._can_add_propulsion_system,
                group="propulsion-creation",
                order=100,
            ),
            ToolbarContribution(
                id=self.toolbar_ids[1],
                title="Add Propulsion Component",
                icon="add",
                menu_items=tuple(
                    ToolbarMenuItemContribution(
                        title=f"Add {label}",
                        callback=lambda component_kind=component_kind: self.add_component(
                            component_kind
                        ),
                        icon=icon,
                        enabled_when=self._can_add_component,
                    )
                    for component_kind, (
                        _component_type,
                        label,
                        icon,
                    ) in _COMPONENT_SPECS.items()
                ),
                enabled_when=self._can_add_component,
                group="propulsion-creation",
                order=110,
            ),
        )

    def _has_propulsion_component(self) -> bool:
        project = self._api.project
        if project is None:
            return False
        components = project.data.get("components", [])
        if not isinstance(components, list):
            return False
        return any(
            isinstance(c, dict)
            and (c.get("id") == _PROPULSION_ID or c.get("type") == _PROPULSION_TYPE)
            for c in components
        )

    def _can_add_propulsion_system(self) -> bool:
        return self._can_edit_project() and not self._has_propulsion_component()

    def _can_add_component(self) -> bool:
        return self._can_edit_project() and self._has_propulsion_component()

    def add_propulsion_system(self) -> None:
        if not self._require_editable_project():
            return
        if self._has_propulsion_component():
            self._api.show_status(
                "Electrical Propulsion already exists in the project",
                "warning",
                3000,
            )
            return
        project = self._api.project
        if project is None:
            return

        propulsion = create_default_propulsion_component()

        def change() -> None:
            components = project.data.setdefault("components", [])
            insert_idx = 1 if (components and components[0].get("id") == "airframe") else 0
            components.insert(insert_idx, propulsion)

        self._api.edit_project("Add Electrical Propulsion", change)
        created = self._find_component(_PROPULSION_ID)
        if created is not None:
            self._api.set_selection(created)
            self._api.show_status("Added Electrical Propulsion", "success", 3000)

    def add_component(self, component_kind: str) -> None:
        if component_kind not in _COMPONENT_SPECS:
            return
        if not self._require_editable_project():
            return
        if not self._has_propulsion_component():
            self._api.show_status(
                "Please add Electrical Propulsion before adding components",
                "warning",
                3000,
            )
            return
        project = self._api.project
        if project is None:
            return

        # Propellers and rotors are mounted on (and positioned relative to) a motor.
        parent_id = _PROPULSION_ID
        if component_kind in {"propeller", "rotor"}:
            motor_id = self._propulsor_motor()
            if motor_id is None:
                return
            parent_id = motor_id

        selected_motor = None
        selected_propeller = None

        if component_kind == "motor":
            from PySide6.QtWidgets import QDialog

            from plugins.electrical_propulsion.catalog_dialog import ComponentCatalogDialog

            dialog = ComponentCatalogDialog(component_type="motor")
            if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selected_motor:
                return
            selected_motor = dialog.selected_motor
        elif component_kind in {"propeller", "rotor"}:
            from PySide6.QtWidgets import QDialog

            from plugins.electrical_propulsion.catalog_dialog import ComponentCatalogDialog

            dialog = ComponentCatalogDialog(component_type="propeller")
            if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selected_propeller:
                return
            selected_propeller = dialog.selected_propeller

        _component_type, base_name, _icon = _COMPONENT_SPECS[component_kind]
        if selected_motor is not None:
            initial_name = selected_motor.name or base_name
        elif selected_propeller is not None:
            initial_name = (
                f"APC {selected_propeller.metadata.model}"
                if selected_propeller.metadata.model
                else base_name
            )
        else:
            initial_name = base_name

        component_id, component_name = self._unique_identity(
            component_kind,
            initial_name,
        )

        component = self._new_component(
            component_kind,
            component_id,
            component_name,
            parent=parent_id,
            selected_motor=selected_motor,
            selected_propeller=selected_propeller,
        )

        def change() -> None:
            components = project.data.setdefault("components", [])
            components.append(component)

        self._api.edit_project(
            f"Add {component_name} to Propulsion",
            change,
        )
        created = self._find_component(component_id)
        if created is not None:
            self._api.set_selection(created)
            self._api.show_status(
                f"Added {component_name} to Propulsion",
                "success",
                3000,
            )

    def _propulsor_motor(self) -> str | None:
        """Motor a new propeller/rotor mounts on: the selected motor, or the only one."""
        motors = [c for c in self._components() if c.get("type") == "org.setuav.core:motor"]
        if not motors:
            self._api.show_status("Add a motor before adding a propeller", "warning", 4000)
            return None
        selection = self._api.current_selection
        if isinstance(selection, dict) and selection.get("type") == "org.setuav.core:motor":
            return str(selection.get("id"))
        if len(motors) == 1:
            return str(motors[0]["id"])
        self._api.show_status("Select the motor to mount the propeller on", "warning", 4000)
        return None

    def _components(self) -> list[dict[str, Any]]:
        project = self._api.project
        components = project.data.get("components") if project is not None else None
        if not isinstance(components, list):
            return []
        return [item for item in components if isinstance(item, dict)]

    def _new_component(
        self,
        component_kind: str,
        component_id: str,
        component_name: str | None = None,
        *,
        parent: str | None = _PROPULSION_ID,
        selected_motor: Any | None = None,
        selected_propeller: Any | None = None,
    ) -> dict[str, Any]:
        component_type, base_name, _icon = _COMPONENT_SPECS[component_kind]
        params = self._default_parameters(component_kind)
        mass = self._default_mass(component_kind, params)
        manufacturer = ""
        model = ""
        catalog_id: str | None = None

        if selected_motor is not None:
            manufacturer = selected_motor.manufacturer or ""
            model = selected_motor.name or ""
            if selected_motor.weight_g:
                mass = float(selected_motor.weight_g)
            params["kv"] = float(selected_motor.kv)
            params["resistance"] = float(selected_motor.resistance)
            params["no_load_current"] = float(selected_motor.io or 0.0)
            params["max_current"] = float(selected_motor.max_current)
            params["max_power"] = float(selected_motor.max_power)
        elif selected_propeller is not None:
            manufacturer = selected_propeller.metadata.manufacturer or ""
            model = selected_propeller.metadata.model or ""
            catalog_id = selected_propeller.metadata.id
            params["diameter"] = round(selected_propeller.diameter_m * 1000.0, 1)
            params["pitch"] = round(selected_propeller.pitch_m * 1000.0, 1)
            params["blade_count"] = int(selected_propeller.metadata.blade_count)

        component: dict[str, Any] = {
            "kind": "component",
            "id": component_id,
            "name": component_name or base_name,
            "type": component_type,
            "parent": parent,
            "manufacturer": manufacturer,
            "model": model,
            "mass": mass,
            "transform": {
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            },
            "envelope": self._default_envelope(component_kind),
            "parameters": params,
        }
        if catalog_id is not None:
            component["catalog_id"] = catalog_id
        return component

    @staticmethod
    def _default_mass(component_kind: str, params: dict[str, Any]) -> float:
        if component_kind == "battery":
            return battery_pack_mass(params)
        masses = {
            "esc": 45.0,
            "motor": 120.0,
            "propeller": 25.0,
            "rotor": 30.0,
        }
        return masses[component_kind]

    @staticmethod
    def _default_envelope(component_kind: str) -> dict[str, Any]:
        if component_kind == "battery":
            return {
                "shape": "box",
                "size_mm": {"x": 150.0, "y": 50.0, "z": 50.0},
                "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
            }
        if component_kind == "esc":
            return {
                "shape": "box",
                "size_mm": {"x": 65.0, "y": 30.0, "z": 12.0},
                "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
            }
        if component_kind == "motor":
            return {
                "shape": "cylinder",
                "size_mm": {"x": 40.0, "y": 35.0, "z": 35.0},
                "offset_mm": {"x": 20.0, "y": 0.0, "z": 0.0},
            }
        if component_kind in {"propeller", "rotor"}:
            return {
                "shape": "cylinder",
                "size_mm": {"x": 20.0, "y": 330.0, "z": 330.0},
                "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
            }
        return {
            "shape": "box",
            "size_mm": {"x": 50.0, "y": 50.0, "z": 50.0},
            "offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
        }

    @staticmethod
    def _default_parameters(component_kind: str) -> dict[str, Any]:
        if component_kind == "battery":
            return BatteryModel.default_parameters()
        if component_kind == "esc":
            return {
                "continuous_current": 50.0,
                "max_current": 60.0,
                "max_voltage": 25.2,
                "resistance": 0.004,
            }
        if component_kind == "motor":
            return {
                "kv": 900.0,
                "resistance": 0.055,
                "no_load_current": 1.1,
                "max_current": 40.0,
                "max_power": 800.0,
            }
        if component_kind == "rotor":
            return {
                "diameter": 330.0,
                "pitch": 165.0,
                "blade_count": 2,
                "hub_diameter": 25.0,
                "collective_pitch": 0.0,
            }
        return {
            "diameter": 330.0,
            "pitch": 165.0,
            "blade_count": 2,
            "hub_diameter": 25.0,
        }

    def _unique_identity(
        self,
        base_id: str,
        base_name: str,
    ) -> tuple[str, str]:
        project = self._api.project
        if project is None:
            return base_id, base_name
        components = project.data.get("components")
        raw_components = components if isinstance(components, list) else []
        ids = {str(item.get("id") or "") for item in raw_components if isinstance(item, dict)}
        names = {str(item.get("name") or "") for item in raw_components if isinstance(item, dict)}
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
            self._api.show_status(
                "Open a project before adding propulsion components",
                "warning",
            )
            return False
        if project.read_only:
            self._api.show_status("The project is read-only", "warning")
            return False
        if not isinstance(project.data.get("components"), list):
            self._api.show_status("Project components are invalid", "error")
            return False
        return True

    def _find_component(self, component_id: str) -> dict[str, Any] | None:
        project = self._api.project
        components = project.data.get("components") if project is not None else None
        if not isinstance(components, list):
            return None
        return next(
            (
                component
                for component in components
                if isinstance(component, dict) and str(component.get("id") or "") == component_id
            ),
            None,
        )
