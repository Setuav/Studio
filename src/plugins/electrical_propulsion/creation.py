"""Toolbar commands for creating electrical propulsion systems and members."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QApplication, QInputDialog

from setuav_studio_sdk import (
    StudioAPI,
    ToolbarContribution,
    ToolbarMenuItemContribution,
)

_ASSEMBLY_TYPE = "org.setuav.core:electric-propulsion-system"
_DESIGN_WORKSPACE = "studio.workspace.design"
_PROPULSION_WORKSPACE = "studio.workspace.propulsion"
_WORKSPACES = (_PROPULSION_WORKSPACE, _DESIGN_WORKSPACE)

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


class PropulsionCreationController:
    """Create valid propulsion assemblies and add members to existing ones."""

    toolbar_ids = (
        "propulsion.create-assembly",
        "propulsion.add-component",
    )

    def __init__(self, api: StudioAPI) -> None:
        self._api = api

    def contributions(self) -> tuple[ToolbarContribution, ...]:
        return (
            ToolbarContribution(
                id=self.toolbar_ids[0],
                title="New Propulsion Assembly",
                callback=self.add_assembly,
                icon="component_propulsion_system",
                enabled_when=self._can_edit_project,
                group="propulsion-creation",
                order=100,
                workspace_id=_WORKSPACES,
            ),
            ToolbarContribution(
                id=self.toolbar_ids[1],
                title="Add Component to Propulsion Assembly",
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
                enabled_when=self._can_edit_project,
                group="propulsion-creation",
                order=110,
                workspace_id=_WORKSPACES,
            ),
        )

    def add_assembly(self) -> None:
        if not self._require_editable_project():
            return
        project = self._api.current_project
        if project is None:
            return

        assembly_id, assembly_name = self._unique_identity(
            "propulsion-system",
            "Propulsion System",
            include_assemblies=True,
        )
        battery_id, battery_name = self._unique_identity(
            f"{assembly_id}-battery",
            "Battery",
        )
        esc_id, esc_name = self._unique_identity(
            f"{assembly_id}-esc",
            "ESC",
        )
        motor_id, motor_name = self._unique_identity(
            f"{assembly_id}-motor",
            "Motor",
        )
        propeller_id, propeller_name = self._unique_identity(
            f"{assembly_id}-propeller",
            "Propeller",
        )
        battery = self._new_component("battery", battery_id, battery_name)
        esc = self._new_component("esc", esc_id, esc_name)
        motor = self._new_component("motor", motor_id, motor_name)
        propeller = self._new_component(
            "propeller",
            propeller_id,
            propeller_name,
            attach_to=str(motor["id"]),
        )
        new_components = [battery, esc, motor, propeller]
        assembly = {
            "id": assembly_id,
            "name": assembly_name,
            "type": _ASSEMBLY_TYPE,
            "members": {
                "battery": battery["id"],
                "controllers": [esc["id"]],
                "motors": [motor["id"]],
                "propulsors": [propeller["id"]],
            },
        }

        def change() -> None:
            components = project.data.get("components")
            assemblies = project.data.get("assemblies")
            if assemblies is None:
                assemblies = []
                project.data["assemblies"] = assemblies
            if not isinstance(components, list) or not isinstance(assemblies, list):
                return
            components.extend(new_components)
            assemblies.append(assembly)

        self._api.edit_project(f"Add {assembly_name}", change)
        created = self._find_assembly(assembly_id)
        if created is not None:
            self._api.set_selection(created)
            self._api.show_status(f"Created {assembly_name}", "success", 3000)

    def add_component(self, component_kind: str) -> None:
        if component_kind not in _COMPONENT_SPECS:
            return
        if not self._require_editable_project():
            return
        assembly = self._choose_target_assembly()
        if assembly is None:
            return

        project = self._api.current_project
        if project is None:
            return
        assembly_id = str(assembly.get("id") or "")
        _component_type, base_name, _icon = _COMPONENT_SPECS[component_kind]
        component_id, component_name = self._unique_identity(
            f"{assembly_id}-{component_kind}",
            base_name,
        )
        attach_to = self._propulsor_attachment(component_kind, assembly)
        component = self._new_component(
            component_kind,
            component_id,
            component_name,
            attach_to=attach_to,
        )

        def change() -> None:
            self._append_component(project.data, assembly_id, component_kind, component)

        assembly_name = str(assembly.get("name") or assembly_id)
        self._api.edit_project(
            f"Add {component_name} to {assembly_name}",
            change,
        )
        created = self._find_component(component_id)
        if created is not None:
            self._api.set_selection(created)
            self._api.show_status(
                f"Added {component_name} to {assembly_name}",
                "success",
                3000,
            )

    @staticmethod
    def _propulsor_attachment(component_kind: str, assembly: dict[str, Any]) -> str | None:
        if component_kind not in {"propeller", "rotor"}:
            return None
        members = assembly.get("members")
        motors = members.get("motors") if isinstance(members, dict) else None
        return str(motors[-1]) if isinstance(motors, list) and motors else None

    def _append_component(
        self,
        project_data: dict[str, Any],
        assembly_id: str,
        component_kind: str,
        component: dict[str, Any],
    ) -> None:
        components = project_data.get("components")
        target = self._find_assembly(assembly_id)
        if not isinstance(components, list) or target is None:
            return
        components.append(component)
        members = target.setdefault("members", {})
        component_id = str(component.get("id") or "")
        if component_kind == "battery":
            members["battery"] = component_id
            return
        role = {
            "esc": "controllers",
            "motor": "motors",
            "propeller": "propulsors",
            "rotor": "propulsors",
        }[component_kind]
        values = members.setdefault(role, [])
        if isinstance(values, list):
            values.append(component_id)
        else:
            members[role] = [component_id]

    def _new_component(
        self,
        component_kind: str,
        component_id: str,
        component_name: str | None = None,
        *,
        attach_to: str | None = None,
    ) -> dict[str, Any]:
        component_type, base_name, _icon = _COMPONENT_SPECS[component_kind]
        component: dict[str, Any] = {
            "kind": "component",
            "id": component_id,
            "name": component_name or base_name,
            "type": component_type,
            "parent": None,
            "transform": {},
            "parameters": self._default_parameters(component_kind),
        }
        if attach_to:
            component["attach_to"] = attach_to
        return component

    @staticmethod
    def _default_parameters(component_kind: str) -> dict[str, Any]:
        if component_kind == "battery":
            return {
                "cell_count": 6,
                "parallel_count": 1,
                "capacity": 5000.0,
                "nominal_voltage": 22.2,
                "internal_resistance": 0.015,
                "chemistry": "LiPo",
            }
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
                "rotation_direction": "ccw",
            }
        return {
            "diameter": 330.0,
            "pitch": 165.0,
            "blade_count": 2,
            "hub_diameter": 25.0,
            "rotation_direction": "ccw",
        }

    def _choose_target_assembly(self) -> dict[str, Any] | None:
        assemblies = self._propulsion_assemblies()
        if not assemblies:
            self._api.show_status(
                "Create a propulsion assembly before adding components",
                "warning",
                4000,
            )
            return None

        selected = self._selected_assembly(assemblies)
        if selected is not None:
            return selected
        if len(assemblies) == 1:
            return assemblies[0]

        labels = [f"{item.get('name') or item.get('id')} ({item.get('id')})" for item in assemblies]
        selected_label, accepted = QInputDialog.getItem(
            QApplication.activeWindow(),
            "Select Propulsion Assembly",
            "Add the component to:",
            labels,
            0,
            False,
        )
        if not accepted:
            return None
        selected_index = labels.index(selected_label)
        return assemblies[selected_index]

    def _selected_assembly(
        self,
        assemblies: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        selection = self._api.current_selection
        if not isinstance(selection, dict):
            return None
        selection_id = str(selection.get("id") or "")
        if selection.get("type") == _ASSEMBLY_TYPE:
            return next(
                (
                    assembly
                    for assembly in assemblies
                    if str(assembly.get("id") or "") == selection_id
                ),
                None,
            )
        if not selection_id:
            return None
        for assembly in assemblies:
            members = assembly.get("members")
            if not isinstance(members, dict):
                continue
            for value in members.values():
                if value == selection_id:
                    return assembly
                if isinstance(value, list) and selection_id in value:
                    return assembly
        return None

    def _unique_identity(
        self,
        base_id: str,
        base_name: str,
        *,
        include_assemblies: bool = False,
    ) -> tuple[str, str]:
        project = self._api.current_project
        if project is None:
            return base_id, base_name
        components = project.data.get("components")
        assemblies = project.data.get("assemblies")
        raw_components = components if isinstance(components, list) else []
        raw_assemblies = assemblies if isinstance(assemblies, list) else []
        identity_items = raw_components + raw_assemblies
        name_items = raw_assemblies if include_assemblies else raw_components
        ids = {str(item.get("id") or "") for item in identity_items if isinstance(item, dict)}
        names = {str(item.get("name") or "") for item in name_items if isinstance(item, dict)}
        if base_id not in ids and base_name not in names:
            return base_id, base_name
        suffix = 2
        while f"{base_id}-{suffix}" in ids or f"{base_name} {suffix}" in names:
            suffix += 1
        return f"{base_id}-{suffix}", f"{base_name} {suffix}"

    def _can_edit_project(self) -> bool:
        project = self._api.current_project
        return project is not None and not project.read_only

    def _can_add_component(self) -> bool:
        return self._can_edit_project() and bool(self._propulsion_assemblies())

    def _require_editable_project(self) -> bool:
        project = self._api.current_project
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
        assemblies = project.data.get("assemblies")
        if assemblies is not None and not isinstance(assemblies, list):
            self._api.show_status("Project assemblies are invalid", "error")
            return False
        return True

    def _propulsion_assemblies(self) -> list[dict[str, Any]]:
        project = self._api.current_project
        assemblies = project.data.get("assemblies") if project is not None else None
        if not isinstance(assemblies, list):
            return []
        return [
            assembly
            for assembly in assemblies
            if isinstance(assembly, dict) and assembly.get("type") == _ASSEMBLY_TYPE
        ]

    def _find_assembly(self, assembly_id: str) -> dict[str, Any] | None:
        return next(
            (
                assembly
                for assembly in self._propulsion_assemblies()
                if str(assembly.get("id") or "") == assembly_id
            ),
            None,
        )

    def _find_component(self, component_id: str) -> dict[str, Any] | None:
        project = self._api.current_project
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
