"""StudioViewport — Core 3D viewport widget with plugin-facing API.

This module wraps the existing OpenGL viewer and exposes a clean,
plugin-friendly interface for adding lofts, primitives, and overlay
objects organised by layers.  Plugins should never touch the underlying
``OpenGLViewer`` directly; all interaction goes through this class.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, Literal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QKeyEvent
from PySide6.QtWidgets import QGridLayout, QWidget

from setuav_studio_sdk.primitives import (
    BoxPrimitive,
    ColorRGBA,
    CylinderPrimitive,
    LineSegmentsPrimitive,
    LoftPrimitive,
    PlanePrimitive,
    Point3D,
    RingPrimitive,
    TrianglesPrimitive,
    VisualPrimitive,
)

from .layer import Layer
from .scene_object import SceneObject

logger = logging.getLogger(__name__)

WIRE_FEATURE = "feature"
WIRE_FULL = "full"
FACE_COLORED = "colored"
FACE_MONOCHROME = "monochrome"

VIEW_PRESETS: dict[str, tuple[float, float]] = {
    "top": (0.0, 90.0),
    "bottom": (0.0, -90.0),
    "front": (270.0, 0.0),
    "side": (180.0, 0.0),
    "iso": (210.0, 20.0),
}


def _call_method(target: object, name: str, *args: Any) -> None:
    fn = getattr(target, name, None)
    if callable(fn):
        fn(*args)


class StudioViewport(QWidget):
    """Central 3D viewport widget.

    Provides the public ``add_*`` / ``remove`` / ``clear`` API that plugins use
    to populate the 3D scene.  Internally delegates all OpenGL rendering to the
    existing ``OpenGLViewer`` from the geometry plugin (which will be migrated
    to this package in a later step).

    Layer visibility can be toggled independently so that, for example, a
    manufacturing overlay can be shown or hidden without affecting the main
    geometry layer.
    """

    object_picked = Signal(str)
    selection_changed = Signal(object)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        parent: QWidget | None = None,
        api: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self._api: Any | None = None

        # Selection state
        self._selected_object_id: str | None = None
        self._selected_section: tuple[str, int, int] | None = None

        # Camera & Display state
        self._azimuth: float = 210.0
        self._elevation: float = 20.0
        self._orthographic: bool = True
        self._show_solid: bool = True
        self._show_wireframe: bool = True
        self._wire_mode: str = WIRE_FEATURE
        self._show_grid: bool = True
        self._transparent: bool = False
        self._face_style: str = FACE_COLORED

        # Scene graph: object_id -> SceneObject
        self._objects: dict[str, SceneObject] = {}

        # Lazy reference to the low-level OpenGL widget.  Assigned via
        # ``attach_renderer`` once the geometry plugin (or Core) provides it.
        self._renderer: QWidget | None = None

        self._grid_layout = QGridLayout(self)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(0)

        # Layers: layer_id -> Layer
        self._layers: dict[str, Layer] = {}
        self.add_layer("default", name="Default")
        self.add_layer("geometry", name="Geometry")

        if api is not None:
            self.bind_api(api)

    # ------------------------------------------------------------------
    # Renderer & API binding
    # ------------------------------------------------------------------

    def attach_renderer(self, renderer: QWidget) -> None:
        """Embed the low-level OpenGL viewer widget.

        Called once during application startup to connect the actual renderer.
        """
        self._renderer = renderer
        self._grid_layout.addWidget(renderer, 0, 0)

        # Apply initial display state to the renderer
        _call_method(renderer, "set_orthographic", self._orthographic)
        _call_method(renderer, "set_show_solid", self._show_solid)
        _call_method(renderer, "set_show_wireframe", self._show_wireframe)
        _call_method(renderer, "set_wire_mode", self._wire_mode)
        _call_method(renderer, "set_show_grid", self._show_grid)
        _call_method(renderer, "set_transparent", self._transparent)
        _call_method(renderer, "set_face_style", self._face_style)
        _call_method(renderer, "set_view", self._azimuth, self._elevation)

        # Connect renderer picking signal if present
        comp_picked = getattr(renderer, "componentPicked", None)
        if comp_picked is not None and hasattr(comp_picked, "connect"):
            comp_picked.connect(self._on_renderer_component_picked)

    @property
    def renderer(self) -> QWidget | None:
        """Return the attached renderer widget, or *None*."""
        return self._renderer

    def bind_api(self, api: Any) -> None:
        """Bind StudioAPI to synchronize selections bi-directionally with the app."""
        self._api = api
        api._viewport = self
        if hasattr(api, "on_selection_changed"):
            api.on_selection_changed(self._on_api_selection_changed)
        if hasattr(api, "on_section_selection_changed"):
            api.on_section_selection_changed(self._on_api_section_selection_changed)
        self.object_picked.connect(self._on_object_picked_to_api)

    # ------------------------------------------------------------------
    # Layer management
    # ------------------------------------------------------------------

    def add_layer(
        self,
        layer_id: str,
        *,
        name: str = "",
        visible: bool = True,
    ) -> Layer:
        """Register a new layer or update an existing one.

        Args:
            layer_id: Unique identifier for the layer (e.g. 'manufacturing').
            name: Human-readable display name. Defaults to *layer_id*.
            visible: Initial visibility state. Defaults to True.

        Returns:
            The created or updated :class:`Layer` instance.
        """
        if layer_id in self._layers:
            layer = self._layers[layer_id]
            if name:
                layer.name = name
            layer.visible = visible
        else:
            layer = Layer(layer_id=layer_id, name=name or layer_id, visible=visible)
            self._layers[layer_id] = layer
        self._sync_renderer()
        return layer

    def remove_layer(self, layer_id: str) -> bool:
        """Remove a registered layer and all objects belonging to it.

        Args:
            layer_id: Identifier of the layer to remove.

        Returns:
            True if the layer existed and was removed, False otherwise.
        """
        if layer_id not in self._layers:
            return False
        del self._layers[layer_id]
        self._objects = {oid: obj for oid, obj in self._objects.items() if obj.layer != layer_id}
        self._sync_renderer()
        return True

    def has_layer(self, layer_id: str) -> bool:
        """Return True if *layer_id* is registered."""
        return layer_id in self._layers

    def get_layer(self, layer_id: str) -> Layer | None:
        """Retrieve a layer by ID, or None if not registered."""
        return self._layers.get(layer_id)

    def layers(self) -> list[str]:
        """Return a sorted list of all registered layer IDs."""
        return sorted(self._layers.keys())

    def set_layer_visible(self, layer: str, visible: bool) -> None:
        """Show or hide all objects belonging to *layer*."""
        if layer in self._layers:
            self._layers[layer].visible = visible
        else:
            self.add_layer(layer, visible=visible)
        self._sync_renderer()

    def is_layer_visible(self, layer: str) -> bool:
        """Return whether *layer* is currently visible (default True)."""
        layer_obj = self._layers.get(layer)
        return layer_obj.visible if layer_obj is not None else True

    # ------------------------------------------------------------------
    # Generic add / remove / query
    # ------------------------------------------------------------------

    def add_object(self, obj: SceneObject) -> SceneObject:
        """Insert or replace a scene object by its ``object_id``.

        If the object belongs to an unregistered layer, that layer is
        registered automatically.
        """
        if obj.layer not in self._layers:
            self.add_layer(obj.layer)
        self._objects[obj.object_id] = obj
        self._sync_renderer()
        return obj

    def remove(self, object_id: str) -> bool:
        """Remove a single object.  Returns ``True`` if it existed."""
        removed = self._objects.pop(object_id, None) is not None
        if removed:
            self._sync_renderer()
        return removed

    def get_object(self, object_id: str) -> SceneObject | None:
        """Look up an object by ID."""
        return self._objects.get(object_id)

    def clear(self, *, layer: str | None = None) -> None:
        """Remove all objects, or all objects on a specific *layer*."""
        if layer is None:
            self._objects.clear()
        else:
            self._objects = {oid: obj for oid, obj in self._objects.items() if obj.layer != layer}
        self._sync_renderer()

    def clear_layer(self, layer: str) -> None:
        """Convenience alias for ``clear(layer=...)``."""
        self.clear(layer=layer)

    def object_ids(self, *, layer: str | None = None) -> list[str]:
        """Return IDs of all objects, optionally filtered by *layer*."""
        if layer is None:
            return list(self._objects)
        return [oid for oid, obj in self._objects.items() if obj.layer == layer]

    # ------------------------------------------------------------------
    # Selection management
    # ------------------------------------------------------------------

    def set_selected(self, object_id: str | None) -> None:
        """Set the active selected object ID and update viewport highlighting."""
        if self._selected_object_id == object_id:
            return
        self._selected_object_id = object_id
        if self._renderer is not None:
            set_sel = getattr(self._renderer, "set_selected_component", None)
            if callable(set_sel):
                set_sel(object_id)
        self.selection_changed.emit(object_id)

    def selected_object_id(self) -> str | None:
        """Return the currently selected object ID, or None."""
        return self._selected_object_id

    def set_selected_section(
        self,
        component_id: str | None,
        segment_index: int | None = None,
        section_index: int | None = None,
    ) -> None:
        """Set the selected section or station highlight."""
        if component_id is not None and segment_index is not None and section_index is not None:
            self._selected_section = (component_id, segment_index, section_index)
        else:
            self._selected_section = None
        if self._renderer is not None:
            set_sec = getattr(self._renderer, "set_selected_section", None)
            if callable(set_sec):
                set_sec(component_id, segment_index, section_index)

    def selected_section(self) -> tuple[str, int, int] | None:
        """Return the currently selected section tuple, or None."""
        return self._selected_section

    # ------------------------------------------------------------------
    # Camera and display controls
    # ------------------------------------------------------------------

    def fit_view(self) -> None:
        """Fit the camera to frame all visible objects in the viewport."""
        if self._renderer is not None:
            fit_fn = getattr(self._renderer, "fit_view", None)
            if callable(fit_fn):
                fit_fn()

    def set_view(self, azimuth: float, elevation: float) -> None:
        """Set the camera orbit angles in degrees."""
        self._azimuth = azimuth
        self._elevation = max(-89.0, min(89.0, elevation))
        if self._renderer is not None:
            view_fn = getattr(self._renderer, "set_view", None)
            if callable(view_fn):
                view_fn(self._azimuth, self._elevation)

    def view_angles(self) -> tuple[float, float]:
        """Return the current camera (azimuth, elevation) angles."""
        return self._azimuth, self._elevation

    def set_view_preset(self, preset: Literal["top", "bottom", "front", "side", "iso"]) -> None:
        """Set camera to a standard viewpoint ('top', 'bottom', 'front', 'side', 'iso')."""
        if preset not in VIEW_PRESETS:
            raise ValueError(
                f"Unknown view preset: {preset}. Valid presets: {list(VIEW_PRESETS.keys())}"
            )
        az, el = VIEW_PRESETS[preset]
        self.set_view(az, el)

    def set_orthographic(self, enabled: bool) -> None:
        """Switch between orthographic (True) and perspective (False) projection."""
        self._orthographic = bool(enabled)
        if self._renderer is not None:
            ortho_fn = getattr(self._renderer, "set_orthographic", None)
            if callable(ortho_fn):
                ortho_fn(self._orthographic)

    def is_orthographic(self) -> bool:
        """Return whether orthographic projection is active."""
        return self._orthographic

    def set_show_solid(self, show: bool) -> None:
        """Toggle solid surface rendering."""
        self._show_solid = bool(show)
        if self._renderer is not None:
            solid_fn = getattr(self._renderer, "set_show_solid", None)
            if callable(solid_fn):
                solid_fn(self._show_solid)

    def is_show_solid(self) -> bool:
        """Return whether solid surfaces are visible."""
        return self._show_solid

    def set_show_wireframe(self, show: bool) -> None:
        """Toggle wireframe lines."""
        self._show_wireframe = bool(show)
        if self._renderer is not None:
            wire_fn = getattr(self._renderer, "set_show_wireframe", None)
            if callable(wire_fn):
                wire_fn(self._show_wireframe)

    def is_show_wireframe(self) -> bool:
        """Return whether wireframes are visible."""
        return self._show_wireframe

    def set_wire_mode(self, mode: Literal["feature", "full"]) -> None:
        """Set wireframe display mode ('feature' or 'full')."""
        if mode not in (WIRE_FEATURE, WIRE_FULL):
            raise ValueError(f"Unknown wire mode: {mode}. Must be 'feature' or 'full'.")
        self._wire_mode = mode
        if self._renderer is not None:
            mode_fn = getattr(self._renderer, "set_wire_mode", None)
            if callable(mode_fn):
                mode_fn(mode)

    def wire_mode(self) -> str:
        """Return the current wireframe mode."""
        return self._wire_mode

    def set_show_grid(self, show: bool) -> None:
        """Toggle 3D ground reference grid."""
        self._show_grid = bool(show)
        if self._renderer is not None:
            grid_fn = getattr(self._renderer, "set_show_grid", None)
            if callable(grid_fn):
                grid_fn(self._show_grid)

    def is_show_grid(self) -> bool:
        """Return whether the ground grid is visible."""
        return self._show_grid

    def set_transparent(self, transparent: bool) -> None:
        """Toggle transparency / X-ray mode."""
        self._transparent = bool(transparent)
        if self._renderer is not None:
            trans_fn = getattr(self._renderer, "set_transparent", None)
            if callable(trans_fn):
                trans_fn(self._transparent)

    def is_transparent(self) -> bool:
        """Return whether transparency mode is active."""
        return self._transparent

    def set_face_style(self, style: Literal["colored", "monochrome"]) -> None:
        """Set surface shading style ('colored' or 'monochrome')."""
        if style not in (FACE_COLORED, FACE_MONOCHROME):
            raise ValueError(f"Unknown face style: {style}. Must be 'colored' or 'monochrome'.")
        self._face_style = style
        if self._renderer is not None:
            style_fn = getattr(self._renderer, "set_face_style", None)
            if callable(style_fn):
                style_fn(style)

    def face_style(self) -> str:
        """Return the current face style."""
        return self._face_style

    def capture_screenshot(
        self,
        width: int,
        height: int,
        transparent_background: bool = False,
    ) -> QImage | None:
        """Capture an off-screen screenshot at the specified resolution."""
        if self._renderer is not None:
            capture_fn = getattr(self._renderer, "capture_screenshot", None)
            if callable(capture_fn):
                result = capture_fn(width, height, transparent_background=transparent_background)
                if isinstance(result, QImage):
                    return result
        return None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard shortcuts (e.g. 'F' to fit view)."""
        if event.key() == Qt.Key.Key_F:
            self.fit_view()
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Typed convenience helpers  (add_*)
    # ------------------------------------------------------------------

    def add_loft(
        self,
        object_id: str,
        sections: Sequence[Sequence[Point3D]],
        *,
        name: str = "",
        layer: str = "geometry",
        color: ColorRGBA = (1.0, 0.82, 0.10, 1.0),
        interpolation: Literal["linear", "smooth"] = "smooth",
        parameterization: Literal["uniform", "chord_length", "centripetal"] = "centripetal",
        station_spacing: float = 10.0,
        closed_ends: bool = True,
        wireframe: bool = True,
        solid: bool = True,
    ) -> SceneObject:
        """Add a lofted surface defined by ordered section loops."""
        # Normalise nested lists to tuples for the frozen dataclass
        norm_sections: tuple[tuple[Point3D, ...], ...] = tuple(
            tuple(pt for pt in sec) for sec in sections
        )
        prim = LoftPrimitive(
            sections=norm_sections,
            color=color,
            interpolation=interpolation,
            parameterization=parameterization,
            station_spacing=station_spacing,
            closed_ends=closed_ends,
            wireframe=wireframe,
            solid=solid,
        )
        obj = SceneObject(
            object_id=object_id,
            layer=layer,
            name=name or object_id,
            primitives=[prim],
        )
        return self.add_object(obj)

    def add_box(
        self,
        object_id: str,
        center: Point3D,
        size: Point3D,
        *,
        name: str = "",
        layer: str = "default",
        color: ColorRGBA = (0.2, 0.6, 1.0, 0.4),
        rotation: Point3D = (0.0, 0.0, 0.0),
        wireframe: bool = True,
        solid: bool = True,
    ) -> SceneObject:
        """Add an axis-aligned (or oriented) box."""
        prim = BoxPrimitive(
            center=center,
            size=size,
            color=color,
            rotation=rotation,
            wireframe=wireframe,
            solid=solid,
        )
        obj = SceneObject(
            object_id=object_id, layer=layer, name=name or object_id, primitives=[prim]
        )
        return self.add_object(obj)

    def add_cylinder(
        self,
        object_id: str,
        start: Point3D,
        end: Point3D,
        radius: float,
        *,
        name: str = "",
        layer: str = "default",
        color: ColorRGBA = (0.2, 0.2, 0.2, 0.9),
        wireframe: bool = False,
        solid: bool = True,
        segments: int = 24,
    ) -> SceneObject:
        """Add a cylinder between two endpoints."""
        prim = CylinderPrimitive(
            start=start,
            end=end,
            radius=radius,
            color=color,
            wireframe=wireframe,
            solid=solid,
            segments=segments,
        )
        obj = SceneObject(
            object_id=object_id, layer=layer, name=name or object_id, primitives=[prim]
        )
        return self.add_object(obj)

    def add_ring(
        self,
        object_id: str,
        center: Point3D,
        *,
        name: str = "",
        layer: str = "default",
        normal: Point3D = (1.0, 0.0, 0.0),
        radius: float = 50.0,
        color: ColorRGBA = (1.0, 0.5, 0.0, 1.0),
        segments: int = 36,
    ) -> SceneObject:
        """Add a circular ring (wire loop)."""
        prim = RingPrimitive(
            center=center,
            normal=normal,
            radius=radius,
            color=color,
            segments=segments,
        )
        obj = SceneObject(
            object_id=object_id, layer=layer, name=name or object_id, primitives=[prim]
        )
        return self.add_object(obj)

    def add_plane(
        self,
        object_id: str,
        center: Point3D,
        *,
        name: str = "",
        layer: str = "default",
        normal: Point3D = (1.0, 0.0, 0.0),
        width: float = 200.0,
        height: float = 200.0,
        color: ColorRGBA = (1.0, 0.5, 0.0, 0.4),
        wireframe: bool = True,
        solid: bool = True,
    ) -> SceneObject:
        """Add a bounded flat plane."""
        prim = PlanePrimitive(
            center=center,
            normal=normal,
            width=width,
            height=height,
            color=color,
            wireframe=wireframe,
            solid=solid,
        )
        obj = SceneObject(
            object_id=object_id, layer=layer, name=name or object_id, primitives=[prim]
        )
        return self.add_object(obj)

    def add_lines(
        self,
        object_id: str,
        lines: Sequence[tuple[Point3D, Point3D]],
        *,
        name: str = "",
        layer: str = "default",
        color: ColorRGBA = (1.0, 1.0, 1.0, 1.0),
    ) -> SceneObject:
        """Add a set of line segments."""
        prim = LineSegmentsPrimitive(
            lines=tuple(lines),
            color=color,
        )
        obj = SceneObject(
            object_id=object_id, layer=layer, name=name or object_id, primitives=[prim]
        )
        return self.add_object(obj)

    def add_triangles(
        self,
        object_id: str,
        triangles: Sequence[tuple[Point3D, Point3D, Point3D]],
        *,
        name: str = "",
        layer: str = "default",
        color: ColorRGBA = (0.7, 0.75, 0.8, 0.7),
        solid: bool = True,
    ) -> SceneObject:
        """Add arbitrary triangles forming a solid surface."""
        prim = TrianglesPrimitive(
            triangles=tuple(triangles),
            color=color,
            solid=solid,
        )
        obj = SceneObject(
            object_id=object_id, layer=layer, name=name or object_id, primitives=[prim]
        )
        return self.add_object(obj)

    def add_points(
        self,
        object_id: str,
        points: Sequence[Point3D],
        *,
        name: str = "",
        layer: str = "default",
        color: ColorRGBA = (1.0, 0.3, 0.1, 1.0),
        size: float = 4.0,
    ) -> SceneObject:
        """Add a point cloud visualised as small crosses.

        Each point is rendered as three short orthogonal line segments
        centred on the point coordinate.
        """
        half = size * 0.5
        segments: list[tuple[Point3D, Point3D]] = []
        for px, py, pz in points:
            segments.append(((px - half, py, pz), (px + half, py, pz)))
            segments.append(((px, py - half, pz), (px, py + half, pz)))
            segments.append(((px, py, pz - half), (px, py, pz + half)))
        prim = LineSegmentsPrimitive(lines=tuple(segments), color=color)
        obj = SceneObject(
            object_id=object_id, layer=layer, name=name or object_id, primitives=[prim]
        )
        return self.add_object(obj)

    def add_arrows(
        self,
        object_id: str,
        arrows: Sequence[tuple[Point3D, Point3D]],
        *,
        name: str = "",
        layer: str = "default",
        color: ColorRGBA = (0.2, 0.8, 0.2, 1.0),
    ) -> SceneObject:
        """Add directional arrows (line from start to end).

        Arrow heads are not yet implemented; arrows are rendered as plain
        line segments for now.
        """
        prim = LineSegmentsPrimitive(lines=tuple(arrows), color=color)
        obj = SceneObject(
            object_id=object_id, layer=layer, name=name or object_id, primitives=[prim]
        )
        return self.add_object(obj)

    def add_primitive(
        self,
        object_id: str,
        primitive: VisualPrimitive,
        *,
        name: str = "",
        layer: str = "default",
    ) -> SceneObject:
        """Add a raw SDK visual primitive directly."""
        obj = SceneObject(
            object_id=object_id, layer=layer, name=name or object_id, primitives=[primitive]
        )
        return self.add_object(obj)

    # ------------------------------------------------------------------
    # Internal renderer synchronisation
    # ------------------------------------------------------------------

    def _collect_visible_primitives(self) -> list[VisualPrimitive]:
        """Gather all primitives from visible objects on visible layers."""
        result: list[VisualPrimitive] = []
        for obj in self._objects.values():
            if not obj.visible:
                continue
            if not self.is_layer_visible(obj.layer):
                continue
            result.extend(obj.primitives)
        return result

    def _sync_renderer(self) -> None:
        """Push the current scene state to the attached OpenGL renderer."""
        if self._renderer is None:
            return
        primitives = self._collect_visible_primitives()
        # The OpenGLViewer exposes set_overlays(layer_id, primitives).
        # We use a single consolidated overlay layer named "_viewport_api"
        # so that objects managed through this API don't clash with overlays
        # managed through the legacy event bus.
        set_overlays = getattr(self._renderer, "set_overlays", None)
        if callable(set_overlays):
            set_overlays("_viewport_api", primitives)

    # ------------------------------------------------------------------
    # Selection event handlers
    # ------------------------------------------------------------------

    def _on_renderer_component_picked(self, component_id: Any) -> None:
        """Handle pick event emitted by the low-level OpenGL widget."""
        if not isinstance(component_id, str) or not component_id:
            self.set_selected(None)
            self.object_picked.emit("")
            return
        self.set_selected(component_id)
        self.object_picked.emit(component_id)

    def _on_api_selection_changed(self, selection: Any | None) -> None:
        """Respond to selection events from StudioAPI (e.g. ProjectExplorer tree click)."""
        if isinstance(selection, dict):
            if selection.get("kind") == "envelope":
                comp_id = selection.get("component_id")
                envelope_id = comp_id if isinstance(comp_id, str) else None
                component_id = None
            else:
                raw_id = selection.get("id")
                component_id = str(raw_id) if raw_id is not None else None
                envelope_id = None
        elif isinstance(selection, str):
            component_id = selection
            envelope_id = None
        else:
            component_id = None
            envelope_id = None

        self.set_selected(component_id)
        if self._renderer is not None:
            set_env = getattr(self._renderer, "set_selected_envelope", None)
            if callable(set_env):
                set_env(envelope_id)

    def _on_api_section_selection_changed(self, selection: tuple[str, int, int] | None) -> None:
        """Respond to section selection events from StudioAPI."""
        if selection is None:
            self.set_selected_section(None)
            return
        comp_id, seg_idx, sec_idx = selection
        self.set_selected_section(comp_id, seg_idx, sec_idx)

    def _on_object_picked_to_api(self, object_id: str) -> None:
        """Bridge a 3D click event to StudioAPI so the Tree and Properties panel update."""
        if self._api is None or not hasattr(self._api, "set_selection"):
            return
        if not object_id:
            self._api.set_selection(None)
            return
        project = getattr(self._api, "current_project", None)
        if project is None or not hasattr(project, "data") or not isinstance(project.data, dict):
            return
        components = project.data.get("components", [])
        raw_components = [c for c in components if isinstance(c, dict)]

        # 1. Direct match with component ID
        for component in raw_components:
            if str(component.get("id") or "") == object_id:
                self._api.set_selection(component)
                return

        # 2. Match control surface sub-tag or child component (e.g. "main-wing:control_1")
        parts = object_id.split(":")
        sub_tag = parts[-1]
        base_id = parts[0]
        for component in raw_components:
            cid = str(component.get("id") or "")
            raw_params = component.get("parameters")
            params = raw_params if isinstance(raw_params, dict) else {}
            raw_geom = params.get("geometry")
            geom = raw_geom if isinstance(raw_geom, dict) else {}
            tag = str(geom.get("tag") or component.get("name") or cid)
            if (
                cid in (sub_tag, f"{base_id}-{sub_tag}", f"{base_id}_{sub_tag}")
                or tag == sub_tag
                or sub_tag.endswith(cid)
            ):
                self._api.set_selection(component)
                return

        # 3. Match base component if mirrored or sub-tagged (e.g. "main-wing:mirror" -> "main-wing")
        for component in raw_components:
            if str(component.get("id") or "") == base_id:
                self._api.set_selection(component)
                return
