"""PropulsionSceneController — Synchronizes electrical propulsion entities with StudioViewport."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from setuav_studio.ui.viewport import RingPrimitive, SceneObject
from setuav_studio.utilities.transform import resolve_world_transform, rotate_vector

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

PROPULSION_LAYER = "electrical_propulsion"
PROPULSION_LAYER_NAME = "Electrical Propulsion"

# Component types managed for 3D propeller disc visualization
PROPULSOR_TYPES = frozenset(
    {
        "org.setuav.core:propeller",
        "org.setuav.core:rotor",
    }
)


class PropulsionSceneController:
    """Manages 3D visualization of propellers and rotors in the central StudioViewport."""

    def __init__(self, api: StudioAPI) -> None:
        self._api = api

    def sync(self, project: Any = None) -> None:
        """Rebuild propeller disk wire loop visualization in the central viewport."""
        viewport = self._api.viewport
        if viewport is None:
            return

        # Ensure the layer is registered and visible
        if not viewport.has_layer(PROPULSION_LAYER):
            viewport.add_layer(PROPULSION_LAYER, name=PROPULSION_LAYER_NAME, visible=True)

        doc = project if project is not None else self._api.project
        if doc is None:
            viewport.clear(layer=PROPULSION_LAYER)
            return

        comps = doc.data.get("components", [])
        if not isinstance(comps, list):
            viewport.clear(layer=PROPULSION_LAYER)
            return

        active_ids: set[str] = set()

        for comp in comps:
            if not isinstance(comp, dict):
                continue
            ctype = str(comp.get("type") or "")
            if ctype not in PROPULSOR_TYPES:
                continue

            comp_id = str(comp.get("id") or "")
            if not comp_id:
                continue

            active_ids.add(comp_id)
            comp_name = str(comp.get("name") or comp_id)

            # Resolve world position and rotation along the parent chain
            world_pos, world_rot = resolve_world_transform(comp, doc)

            diameter = comp["parameters"]["diameter"]
            if isinstance(diameter, bool) or not isinstance(diameter, (int, float)):
                raise ValueError(f"Propulsor '{comp_name}' has no numeric 'diameter' parameter.")
            radius = float(diameter) / 2.0

            # Propeller disk normal vector: local axis (1.0, 0.0, 0.0) rotated by world rotation
            normal = rotate_vector((1.0, 0.0, 0.0), world_rot)

            ring = RingPrimitive(
                center=world_pos,
                normal=normal,
                radius=radius,
                color=(1.0, 1.0, 1.0, 1.0),
                segments=48,
            )

            obj = SceneObject(
                object_id=comp_id,
                layer=PROPULSION_LAYER,
                name=comp_name,
                primitives=[ring],
            )
            viewport.add_object(obj)

        existing_ids = set(viewport.object_ids(layer=PROPULSION_LAYER))
        for removed_id in existing_ids - active_ids:
            viewport.remove(removed_id)

    def on_project_changed(self, project: Any) -> None:
        self.sync(project)

    def on_project_content_changed(self, project: Any) -> None:
        self.sync(project)

    def dispose(self) -> None:
        """Clean up propulsion objects from viewport."""
        viewport = self._api.viewport
        if viewport is not None:
            viewport.clear(layer=PROPULSION_LAYER)
