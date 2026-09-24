"""GeometrySceneController — Synchronizes geometry engine output with StudioViewport."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from setuav_studio.ui.viewport import (
    LoftPrimitive,
    SceneObject,
    VisualPrimitive,
)

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

    from .engine.scene import GeometryProvider

logger = logging.getLogger(__name__)

GEOMETRY_LAYER = "geometry"


def _to_rgba(c: Any) -> tuple[float, float, float, float]:
    if isinstance(c, (tuple, list)):
        if len(c) >= 4:
            return (float(c[0]), float(c[1]), float(c[2]), float(c[3]))
        if len(c) == 3:
            return (float(c[0]), float(c[1]), float(c[2]), 1.0)
    return (0.65, 0.68, 0.72, 1.0)


class GeometrySceneController:
    """Manages 3D visualization of aircraft geometry in the central StudioViewport."""

    def __init__(self, api: StudioAPI, providers: dict[str, GeometryProvider]) -> None:
        self._api = api
        self._providers = providers

    def sync(self, project: Any = None) -> None:
        """Rebuild geometry representation in the central viewport."""
        viewport = getattr(self._api, "viewport", None)
        if viewport is None:
            return

        doc = project if project is not None else getattr(self._api, "current_project", None)
        if doc is None or not hasattr(doc, "data") or not isinstance(doc.data, dict):
            viewport.clear(layer=GEOMETRY_LAYER)
            return

        from .engine.scene import build_project_geometry

        try:
            geom = build_project_geometry(doc, self._providers)
        except Exception as exc:
            logger.warning("Failed to build geometry for viewport: %s", exc)
            return

        comps = doc.data.get("components", [])
        comp_names: dict[str, str] = {}
        if isinstance(comps, list):
            for c in comps:
                if isinstance(c, dict):
                    cid = str(c.get("id") or "")
                    if cid:
                        comp_names[cid] = str(c.get("name") or cid)

        comp_primitives: dict[str, list[VisualPrimitive]] = {}

        # 1. Loft Geometries (wings, fuselages, control surfaces, wing root stubs)
        for loft in geom.lofts:
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

        # 2. Envelope Geometries (stored on SceneObject.envelope, rendered only when envelope is selected)
        comp_envelopes: dict[str, Any] = {}
        for env in geom.envelopes:
            if env.lines:
                comp_envelopes[env.component_id] = env

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
        viewport = getattr(self._api, "viewport", None)
        if viewport is not None:
            viewport.clear(layer=GEOMETRY_LAYER)
