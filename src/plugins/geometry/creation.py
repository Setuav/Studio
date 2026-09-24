"""Geometry component creation commands exposed by the Geometry plugin."""

from __future__ import annotations

from typing import Any

from setuav_studio.api import (
    StudioAPI,
    ToolbarContribution,
    ToolbarMenuItemContribution,
)

from .engine.fuselage_geometry import create_default_section

_FUSELAGE_TYPE = "org.setuav.core:fuselage"
_LIFTING_SURFACE_TYPE = "org.setuav.core:lifting-surface"
_CONTROL_SURFACE_TYPE = "org.setuav.core:control-surface"
_AIRFRAME_TYPE = "org.setuav.core:airframe"
_AIRFRAME_ID = "airframe"
_AIRFRAME_NAME = "Airframe"


def create_default_airframe_component() -> dict[str, Any]:
    return {
        "kind": "component",
        "id": _AIRFRAME_ID,
        "name": _AIRFRAME_NAME,
        "type": _AIRFRAME_TYPE,
        "parent": None,
        "parameters": {},
    }


def ensure_airframe_component(project: Any) -> dict[str, Any]:
    """Ensure the fixed Airframe root component exists in the project and reparent top-level geometry."""
    data = getattr(project, "data", project) if project is not None else {}
    components = data.setdefault("components", [])
    if not isinstance(components, list):
        components = []
        data["components"] = components

    airframe: dict[str, Any] | None = None
    for comp in components:
        if isinstance(comp, dict) and (
            comp.get("id") == _AIRFRAME_ID or comp.get("type") == _AIRFRAME_TYPE
        ):
            airframe = comp
            break

    if airframe is None:
        airframe = create_default_airframe_component()
        components.insert(0, airframe)
    else:
        airframe.setdefault("kind", "component")
        airframe["id"] = _AIRFRAME_ID
        airframe["type"] = _AIRFRAME_TYPE
        airframe["parent"] = None
        if not airframe.get("name"):
            airframe["name"] = _AIRFRAME_NAME

    # Ensure all fuselages and lifting surfaces with no parent default to airframe
    for comp in components:
        if not isinstance(comp, dict) or comp is airframe:
            continue
        comp_type = comp.get("type")
        if comp_type in (_FUSELAGE_TYPE, _LIFTING_SURFACE_TYPE):
            parent = comp.get("parent")
            if (
                not parent
                or parent.startswith("airframe-structure")
                or parent.startswith("airframe-main")
            ):
                comp["parent"] = _AIRFRAME_ID

    # Purge obsolete structural-system assemblies if present
    assemblies = data.get("assemblies")
    if isinstance(assemblies, list):
        data["assemblies"] = [
            asm
            for asm in assemblies
            if not (
                isinstance(asm, dict) and asm.get("type") == "org.setuav.core:structural-system"
            )
        ]

    return airframe


class GeometryCreationController:
    """Create valid starter geometry and publish it through the Studio API."""

    toolbar_ids = (
        "geometry.create-fuselage",
        "geometry.create-lifting-surface",
        "geometry.create-control-surface",
    )

    def __init__(self, api: StudioAPI) -> None:
        self._api = api

    def contributions(self) -> tuple[ToolbarContribution, ...]:
        return (
            ToolbarContribution(
                id=self.toolbar_ids[0],
                title="Add Fuselage",
                callback=self.add_fuselage,
                icon="geometry_add_fuselage",
                enabled_when=self._can_edit_project,
                group="geometry-creation",
                order=100,
            ),
            ToolbarContribution(
                id=self.toolbar_ids[1],
                title="Add Lifting Surface",
                icon="geometry_add_lifting_surface",
                menu_items=(
                    self._lifting_surface_item("Main Wing", "main-wing"),
                    self._lifting_surface_item(
                        "Horizontal Tail",
                        "horizontal-tail",
                    ),
                    self._lifting_surface_item("Vertical Tail", "vertical-tail"),
                    self._lifting_surface_item(
                        "Generic Lifting Surface",
                        "generic",
                    ),
                ),
                enabled_when=self._can_edit_project,
                group="geometry-creation",
                order=110,
            ),
            ToolbarContribution(
                id=self.toolbar_ids[2],
                title="Add Control Surface",
                icon="geometry_add_control_surface",
                menu_items=tuple(
                    ToolbarMenuItemContribution(
                        title=title,
                        callback=lambda surface_type=surface_type: self.add_control_surface(
                            surface_type
                        ),
                        icon="geometry_add_control_surface",
                    )
                    for surface_type, title in (
                        ("aileron", "Aileron"),
                        ("elevator", "Elevator"),
                        ("rudder", "Rudder"),
                        ("flap", "Flap"),
                    )
                ),
                enabled_when=self._can_add_control_surface,
                group="geometry-creation",
                order=120,
            ),
        )

    def add_fuselage(self) -> None:
        if not self._require_editable_project():
            return
        project = self._api.current_project
        if project is not None:
            ensure_airframe_component(project)
        component_id, name = self._unique_identity("fuselage", "Fuselage")
        sections = [
            create_default_section(0.0, "circle"),
            create_default_section(140.0, "circle"),
            create_default_section(600.0, "circle"),
        ]
        for section, diameter in zip(sections, (25.0, 120.0, 35.0), strict=True):
            section["profile"]["diameter"] = diameter
        component = {
            "kind": "component",
            "id": component_id,
            "name": name,
            "type": _FUSELAGE_TYPE,
            "parent": _AIRFRAME_ID,
            "mass": 350.0,
            "transform": {
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            },
            "envelope": {
                "shape": "trapezoid",
                "size_mm": {"x": 600.0, "y": 120.0, "z": 120.0},
                "offset_mm": {"x": 300.0, "y": 0.0, "z": 0.0},
            },
            "parameters": {
                "geometry": {
                    "segments": [
                        {
                            "tag": "main",
                            "loft": {
                                "method": "smooth",
                                "parameterization": "centripetal",
                                "profile_correspondence": "cardinal_quadrants",
                            },
                            "sections": sections,
                        }
                    ]
                }
            },
        }
        from .engine.envelope import sync_component_envelope

        sync_component_envelope(component)
        self._append_component(component, "Add fuselage")

    def add_lifting_surface(self, preset: str) -> None:
        if not self._require_editable_project():
            return
        project = self._api.current_project
        if project is not None:
            ensure_airframe_component(project)
        # (base_id, base_name, span, root_chord, tip_chord, mirrored, roll, airfoil, mass, thickness)
        presets: dict[str, tuple[str, str, float, float, float, bool, float, str, float, float]] = {
            "main-wing": (
                "main-wing",
                "Main Wing",
                500.0,
                220.0,
                110.0,
                True,
                0.0,
                "2412",
                250.0,
                26.0,
            ),
            "horizontal-tail": (
                "horizontal-tail",
                "Horizontal Tail",
                250.0,
                130.0,
                65.0,
                True,
                0.0,
                "0012",
                80.0,
                16.0,
            ),
            "vertical-tail": (
                "vertical-tail",
                "Vertical Tail",
                250.0,
                150.0,
                60.0,
                False,
                90.0,
                "0012",
                50.0,
                18.0,
            ),
            "generic": (
                "lifting-surface",
                "Lifting Surface",
                300.0,
                160.0,
                80.0,
                False,
                0.0,
                "0012",
                100.0,
                20.0,
            ),
        }
        values = presets.get(preset, presets["generic"])
        (
            base_id,
            base_name,
            span,
            root_chord,
            tip_chord,
            mirrored,
            roll,
            airfoil,
            mass,
            thickness,
        ) = values
        component_id, name = self._unique_identity(base_id, base_name)
        attach_to = self._first_component_id(_FUSELAGE_TYPE)
        x_position = 0.0 if preset in {"main-wing", "generic"} else 500.0
        total_span = span * 2.0 if mirrored else span
        span_offset = 0.0 if mirrored else span / 2.0
        component = {
            "kind": "component",
            "id": component_id,
            "name": name,
            "type": _LIFTING_SURFACE_TYPE,
            "parent": _AIRFRAME_ID,
            "attach_to": attach_to,
            "mass": mass,
            "transform": {
                "position": {"x": x_position, "y": 0.0, "z": 0.0},
                "rotation": {"roll": roll, "pitch": 0.0, "yaw": 0.0},
            },
            "envelope": {
                "shape": "box",
                "size_mm": {"x": root_chord, "y": total_span, "z": thickness},
                "offset_mm": {"x": root_chord / 2.0, "y": span_offset, "z": 0.0},
            },
            "parameters": {
                "geometry": {
                    "mirror": mirrored,
                    "symmetric": mirrored,
                    "profiles": [
                        self._wing_profile(0.0, root_chord, airfoil),
                        self._wing_profile(span, tip_chord, airfoil),
                    ],
                    "tip_treatment": {"type": "flat"},
                }
            },
        }
        from .engine.envelope import sync_component_envelope

        sync_component_envelope(component)
        self._append_component(component, f"Add {base_name.lower()}")

    def add_control_surface(self, surface_type: str) -> None:
        if not self._require_editable_project():
            return
        parent = self._selected_lifting_surface()
        if parent is None:
            self._api.show_status(
                "Select a lifting surface before adding a control surface",
                "warning",
                4000,
            )
            return

        labels = {
            "aileron": "Aileron",
            "elevator": "Elevator",
            "rudder": "Rudder",
            "flap": "Flap",
        }
        base_name = labels.get(surface_type, "Control Surface")
        parent_id = str(parent.get("id") or "lifting-surface")
        component_id, name = self._unique_identity(
            f"{parent_id}-{surface_type}",
            base_name,
        )
        semi_span, root_chord = self._lifting_surface_size(parent)
        eta_start = 0.4
        eta_end = 0.85
        chord_fraction = 0.25
        component = {
            "kind": "component",
            "id": component_id,
            "name": name,
            "type": _CONTROL_SURFACE_TYPE,
            "parent": parent_id,
            "attach_to": parent_id,
            "mass": 25.0,
            "transform": {
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            },
            "envelope": {
                "shape": "box",
                "size_mm": {
                    "x": round(max(root_chord * chord_fraction, 10.0), 1),
                    "y": round(max(semi_span * (eta_end - eta_start), 20.0), 1),
                    "z": 15.0,
                },
                "offset_mm": {
                    "x": round(root_chord * (1.0 - chord_fraction / 2.0), 1),
                    "y": round(semi_span * (eta_start + eta_end) / 2.0, 1),
                    "z": 0.0,
                },
            },
            "parameters": {
                "geometry": {
                    "tag": component_id.removeprefix(f"{parent_id}-"),
                    "type": surface_type,
                    "span_mode": "ratio",
                    "span_start": round(semi_span * eta_start, 1),
                    "span_end": round(semi_span * eta_end, 1),
                    "eta_start": eta_start,
                    "eta_end": eta_end,
                    "chord_mode": "ratio",
                    "chord_fraction": chord_fraction,
                    "chord": round(root_chord * chord_fraction, 1),
                    "hinge_sweep": 0.0,
                    "deflection": 0.0,
                    "symmetry_mode": "auto",
                }
            },
        }
        from .engine.envelope import sync_component_envelope

        sync_component_envelope(component, parent)
        self._append_component(component, f"Add {base_name.lower()}")

    def _lifting_surface_item(
        self,
        title: str,
        preset: str,
    ) -> ToolbarMenuItemContribution:
        return ToolbarMenuItemContribution(
            title=title,
            callback=lambda preset=preset: self.add_lifting_surface(preset),
            icon="geometry_add_lifting_surface",
        )

    def _can_edit_project(self) -> bool:
        project = self._api.current_project
        return project is not None and not project.read_only

    def _can_add_control_surface(self) -> bool:
        return self._can_edit_project() and self._selected_lifting_surface() is not None

    def _require_editable_project(self) -> bool:
        project = self._api.current_project
        if project is None:
            self._api.show_status("Open a project before adding geometry", "warning")
            return False
        if project.read_only:
            self._api.show_status("The project is read-only", "warning")
            return False
        components = project.data.get("components")
        if not isinstance(components, list):
            self._api.show_status("Project components are invalid", "error")
            return False
        return True

    def _append_component(
        self,
        component: dict[str, Any],
        description: str,
    ) -> None:
        project = self._api.current_project
        if project is None:
            return

        def change() -> None:
            components = project.data.get("components")
            if isinstance(components, list):
                components.append(component)

        self._api.edit_project(description, change)
        created = next(
            (
                item
                for item in project.data.get("components", [])
                if isinstance(item, dict) and item.get("id") == component["id"]
            ),
            None,
        )
        if created is not None:
            self._api.set_selection(created)
            self._api.show_status(f"Created {component['name']}", "success", 3000)

    def _unique_identity(
        self,
        base_id: str,
        base_name: str,
        *,
        include_assemblies: bool = False,
    ) -> tuple[str, str]:
        elements: list[dict[str, Any]] = list(self._components())
        if include_assemblies:
            project = self._api.current_project
            if project is not None:
                asms = project.data.get("assemblies", [])
                if isinstance(asms, list):
                    elements.extend(item for item in asms if isinstance(item, dict))
        ids = {str(item.get("id") or "") for item in elements}
        names = {str(item.get("name") or "") for item in elements}
        if base_id not in ids and base_name not in names:
            return base_id, base_name
        suffix = 2
        while f"{base_id}-{suffix}" in ids or f"{base_name} {suffix}" in names:
            suffix += 1
        return f"{base_id}-{suffix}", f"{base_name} {suffix}"

    def _first_component_id(self, component_type: str) -> str | None:
        for component in self._components():
            if component.get("type") == component_type:
                component_id = component.get("id")
                if isinstance(component_id, str) and component_id:
                    return component_id
        return None

    def _selected_lifting_surface(self) -> dict[str, Any] | None:
        selection = self._api.current_selection
        if not isinstance(selection, dict) or selection.get("type") != _LIFTING_SURFACE_TYPE:
            return None
        selection_id = selection.get("id")
        for component in self._components():
            if component.get("id") == selection_id:
                return component
        return None

    def _components(self) -> list[dict[str, Any]]:
        project = self._api.current_project
        if project is None:
            return []
        components = project.data.get("components")
        if not isinstance(components, list):
            return []
        return [item for item in components if isinstance(item, dict)]

    @staticmethod
    def _wing_profile(
        span_position: float,
        chord: float,
        airfoil: str,
    ) -> dict[str, Any]:
        return {
            "position": {"x": 0.0, "y": span_position, "z": 0.0},
            "chord": chord,
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
            "airfoil": airfoil,
        }

    @staticmethod
    def _lifting_surface_size(component: dict[str, Any]) -> tuple[float, float]:
        parameters = component.get("parameters")
        parameters = parameters if isinstance(parameters, dict) else {}
        geometry = parameters.get("geometry")
        geometry = geometry if isinstance(geometry, dict) else {}
        profiles = geometry.get("profiles")
        profiles = profiles if isinstance(profiles, list) else []
        positions: list[float] = []
        chords: list[float] = []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            position = profile.get("position")
            if isinstance(position, dict):
                positions.append(float(position.get("y") or 0.0))
            chords.append(float(profile.get("chord") or 100.0))
        semi_span = max(positions, default=500.0) - min(positions, default=0.0)
        return max(abs(semi_span), 1.0), max(chords[0] if chords else 100.0, 1.0)


__all__ = [
    "GeometryCreationController",
    "create_default_airframe_component",
    "ensure_airframe_component",
]
