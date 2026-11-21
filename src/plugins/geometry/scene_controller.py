"""AirframeSceneController — Synchronizes geometry engine output with StudioViewport."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from setuav_studio.ui.viewport import (
    LoftGeometry,
    LoftPrimitive,
    SceneObject,
    VisualPrimitive,
)

GEOMETRY_LAYER = "geometry"
GEOMETRY_LAYER_NAME = "Geometry"

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

    from .engine.scene import GeometryProvider


def _collect_primitives(
    lofts: Iterable[LoftGeometry],
) -> tuple[dict[str, list[VisualPrimitive]], dict[str, str]]:
    """The loft primitives of each scene object, and the component each object draws."""
    primitives: dict[str, list[VisualPrimitive]] = {}
    owners: dict[str, str] = {}
    for loft in lofts:
        if len(loft.sections) < 2:
            continue
        primitives.setdefault(loft.component_id, []).append(
            LoftPrimitive(
                sections=tuple(section.points for section in loft.sections),
                interpolation=loft.interpolation,
                station_spacing=loft.station_spacing,
                closed_ends=loft.closed_ends,
                wireframe=True,
                solid=True,
                feature_wire=loft.feature_wire,
            )
        )
        owners[loft.component_id] = loft.owner_id
    return primitives, owners


class AirframeSceneController:
    """Manages 3D visualization of aircraft geometry in the central StudioViewport."""

    def __init__(self, api: StudioAPI, providers: dict[str, GeometryProvider]) -> None:
        self._api = api
        self._providers = providers

    def sync(self, project: Any = None) -> None:
        """Rebuild geometry representation in the central viewport."""
        viewport = self._api.viewport
        if viewport is None:
            return

        if not viewport.has_layer(GEOMETRY_LAYER):
            viewport.add_layer(GEOMETRY_LAYER, name=GEOMETRY_LAYER_NAME, visible=True)

        doc = project if project is not None else self._api.project
        if doc is None:
            viewport.clear(layer=GEOMETRY_LAYER)
            return

        from .engine.scene import build_project_geometry

        try:
            geom = build_project_geometry(doc, self._providers)
        except ValueError as exc:
            # Invalid geometry data in the project: drop the stale airframe and tell
            # the user why it is not drawn.
            viewport.clear(layer=GEOMETRY_LAYER)
            self._api.show_status(f"Airframe geometry error: {exc}", "error", 6000)
            return

        names = {str(c["id"]): str(c.get("name") or c["id"]) for c in doc.data["components"]}
        primitives, owners = _collect_primitives(geom.lofts)
        envelopes = {env.component_id: env for env in geom.envelopes if env.lines}
        # An envelope belongs to the scene object of its own component.
        owners.update({component_id: component_id for component_id in envelopes})

        existing_ids = set(viewport.object_ids(layer=GEOMETRY_LAYER))
        for removed_id in existing_ids - owners.keys():
            viewport.remove(removed_id)

        for object_id, component_id in owners.items():
            viewport.add_object(
                SceneObject(
                    object_id=object_id,
                    component_id=component_id,
                    layer=GEOMETRY_LAYER,
                    name=names[component_id],
                    primitives=primitives.get(object_id, []),
                    envelope=envelopes.get(object_id),
                )
            )

    def on_project_changed(self, project: Any) -> None:
        self.sync(project)

    def on_project_content_changed(self, project: Any) -> None:
        self.sync(project)

    def dispose(self) -> None:
        """Remove the geometry layer and its objects from the viewport."""
        viewport = self._api.viewport
        if viewport is not None:
            viewport.remove_layer(GEOMETRY_LAYER)
