"""Geometry component creation commands exposed by the Geometry plugin."""

from __future__ import annotations

import math
from typing import Any

from setuav_studio.api import (
    StudioAPI,
    ToolbarContribution,
    ToolbarMenuItemContribution,
)

from .engine.fuselage_geometry import create_default_section
from .engine.lifting_surface_layout import DEFAULT_ACTIVE_DRIVERS, build_profiles

_FUSELAGE_TYPE = "org.setuav.core:fuselage"
_LIFTING_SURFACE_TYPE = "org.setuav.core:lifting-surface"
_CONTROL_SURFACE_TYPE = "org.setuav.core:control-surface"


class AirframeCreationController:
    """Create valid starter geometry and publish it through the Studio API."""

    toolbar_ids = (
        "airframe.create-fuselage",
        "airframe.create-lifting-surface",
        "airframe.create-control-surface",
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
                group="airframe-creation",
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
                group="airframe-creation",
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
                        enabled_when=self._can_add_control_surface,
                    )
                    for surface_type, title in (
                        ("aileron", "Aileron"),
                        ("elevator", "Elevator"),
                        ("rudder", "Rudder"),
                        ("flap", "Flap"),
                    )
                ),
                enabled_when=self._can_add_control_surface,
                group="airframe-creation",
                order=120,
            ),
        )

    def add_fuselage(self) -> None:
        if not self._require_editable_project():
            return
        project = self._api.project
        if project is None:
            return
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
                                "profile_correspondence": "cardinal_quadrants",
                            },
                            "sections": sections,
                        }
                    ]
                }
            },
        }
        self._append_component(component, "Add fuselage")

    def add_lifting_surface(self, preset: str) -> None:
        if not self._require_editable_project():
            return
        project = self._api.project
        if project is None:
            return
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
            **({"attach_to": attach_to} if attach_to else {}),
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
                "geometry": self._wing_geometry(mirrored, span, root_chord, tip_chord, airfoil)
            },
        }
        self._append_component(component, f"Add {base_name.lower()}")

    def add_control_surface(self, surface_type: str) -> None:
        if not self._require_editable_project():
            return
        surface = self._selected_lifting_surface()
        if surface is None:
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
        surface_id = str(surface["id"])
        component_id, name = self._unique_identity(
            f"{surface_id}-{surface_type}",
            base_name,
        )
        semi_span, root_chord = self._lifting_surface_size(surface)
        eta_start = 0.4
        eta_end = 0.85
        chord_fraction = 0.25
        component = {
            "kind": "component",
            "id": component_id,
            "name": name,
            "type": _CONTROL_SURFACE_TYPE,
            "attach_to": surface_id,
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
                    "type": surface_type,
                    "sizing_mode": "ratio",
                    "span_start": round(semi_span * eta_start, 1),
                    "span_end": round(semi_span * eta_end, 1),
                    "eta_start": eta_start,
                    "eta_end": eta_end,
                    "chord_fraction": chord_fraction,
                    "chord": round(root_chord * chord_fraction, 1),
                    "hinge_sweep": 0.0,
                    "deflection": 0.0,
                    "symmetry_mode": "auto",
                }
            },
        }
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
            enabled_when=self._can_edit_project,
        )

    def _can_edit_project(self) -> bool:
        project = self._api.project
        return project is not None and not project.read_only

    def _can_add_control_surface(self) -> bool:
        return self._can_edit_project() and self._selected_lifting_surface() is not None

    def _require_editable_project(self) -> bool:
        project = self._api.project
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
        project = self._api.project
        if project is None:
            return

        def change() -> None:
            components = project.data.get("components")
            if isinstance(components, list):
                components.append(component)

        self._api.edit_project(description, change)
        created = self._find_component(str(component["id"]))
        if created is not None:
            self._api.set_selection(created)
            self._api.show_status(f"Created {component['name']}", "success", 3000)

    def _unique_identity(
        self,
        base_id: str,
        base_name: str,
    ) -> tuple[str, str]:
        elements = self._components()
        ids = {str(item["id"]) for item in elements}
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

    def _find_component(self, component_id: str) -> dict[str, Any] | None:
        return next(
            (item for item in self._components() if item.get("id") == component_id),
            None,
        )

    def _components(self) -> list[dict[str, Any]]:
        project = self._api.project
        if project is None:
            return []
        components = project.data.get("components")
        if not isinstance(components, list):
            return []
        return [item for item in components if isinstance(item, dict)]

    @staticmethod
    def _wing_geometry(
        mirrored: bool, span: float, root_chord: float, tip_chord: float, airfoil: str
    ) -> dict[str, Any]:
        """One straight-leading-edge section from the root to the tip."""
        sweep_location = 0.25
        # The leading edge stays straight, so the sweep-location line follows the taper.
        sweep = math.degrees(math.atan(sweep_location * (tip_chord - root_chord) / span))
        root = {"chord": root_chord, "airfoil": airfoil}
        sections = [
            {
                "span": span,
                "sweep": sweep,
                "dihedral": 0.0,
                "twist": 0.0,
                "tip": {"chord": tip_chord, "airfoil": airfoil},
            }
        ]
        return {
            "mirror": mirrored,
            "sweep_location": sweep_location,
            "twist_location": 0.25,
            "section_align": "xz",
            "planform": {"active_drivers": list(DEFAULT_ACTIVE_DRIVERS)},
            "root": root,
            "sections": sections,
            "tip_treatment": {"type": "flat"},
            "profiles": build_profiles(root, sections, sweep_location),
        }

    @staticmethod
    def _lifting_surface_size(component: dict[str, Any]) -> tuple[float, float]:
        """Return the semi-span and root chord of a lifting surface's profile stations."""
        profiles = component["parameters"]["geometry"]["profiles"]
        if len(profiles) < 2:
            raise ValueError(
                f"Lifting surface '{component['id']}' needs two profile stations, "
                f"got {len(profiles)}."
            )
        spans = [float(profile["position"]["y"]) for profile in profiles]
        return max(spans) - min(spans), float(profiles[0]["chord"])


__all__ = [
    "AirframeCreationController",
]
