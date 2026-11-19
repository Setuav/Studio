"""AirframeSceneController — Synchronizes geometry engine output with StudioViewport."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from setuav_studio.ui.viewport import (
    LoftPrimitive,
    SceneObject,
    VisualPrimitive,
)

GEOMETRY_LAYER = "geometry"
GEOMETRY_LAYER_NAME = "Geometry"

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

    from .engine.scene import GeometryProvider


def _to_rgba(c: Any) -> tuple[float, float, float, float]:
    if isinstance(c, (tuple, list)):
        if len(c) >= 4:
            return (float(c[0]), float(c[1]), float(c[2]), float(c[3]))
        if len(c) == 3:
            return (float(c[0]), float(c[1]), float(c[2]), 1.0)
    return (0.65, 0.68, 0.72, 1.0)


def _extract_component_names(comps: Any) -> dict[str, str]:
    if not isinstance(comps, list):
        return {}
    return {
        str(c.get("id")): str(c.get("name") or c.get("id"))
        for c in comps
        if isinstance(c, dict) and c.get("id")
    }


def _collect_primitives(lofts: Any) -> dict[str, list[VisualPrimitive]]:
    comp_primitives: dict[str, list[VisualPrimitive]] = {}
    for loft in lofts:
        if ":stations" in loft.component_id:
            continue
        sections_pts = tuple(tuple(pt for pt in sec.points) for sec in loft.sections)
        if len(sections_pts) < 2:
            continue
        prim = LoftPrimitive(
            sections=sections_pts,
            color=_to_rgba(loft.color),
            interpolation=getattr(loft, "interpolation", "smooth"),
            station_spacing=getattr(loft, "station_spacing", 10.0),
            closed_ends=getattr(loft, "closed_ends", True),
            wireframe=True,
            solid=True,
        )
        comp_primitives.setdefault(loft.component_id, []).append(prim)
    return comp_primitives


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

        comp_names = _extract_component_names(doc.data.get("components"))
        comp_primitives = _collect_primitives(geom.lofts)

        comp_envelopes: dict[str, Any] = {
            env.component_id: env for env in geom.envelopes if env.lines
        }

        active_ids = set(comp_primitives.keys()) | set(comp_envelopes.keys())
        existing_ids = set(viewport.object_ids(layer=GEOMETRY_LAYER))

        for removed_id in existing_ids - active_ids:
            viewport.remove(removed_id)

        for comp_id in active_ids:
            prims = comp_primitives.get(comp_id, [])
            env = comp_envelopes.get(comp_id)
            name = comp_names.get(comp_id, comp_id)
            obj = SceneObject(
                object_id=comp_id,
                layer=GEOMETRY_LAYER,
                name=name,
                primitives=prims,
                envelope=env,
            )
            viewport.add_object(obj)

    def on_project_changed(self, project: Any) -> None:
        self.sync(project)

    def on_project_content_changed(self, project: Any) -> None:
        self.sync(project)

    def dispose(self) -> None:
        """Clean up geometry objects from viewport."""
        viewport = self._api.viewport
        if viewport is not None:
            viewport.clear(layer=GEOMETRY_LAYER)
