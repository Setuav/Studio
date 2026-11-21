"""StudioViewport — Core 3D viewport widget with plugin-facing API.

This module wraps the existing OpenGL viewer and exposes a clean,
plugin-friendly interface for adding lofts, primitives, and overlay
objects organised by layers.  Plugins should never touch the underlying
``OpenGLViewer`` directly; all interaction goes through this class.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, Literal, Protocol

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QKeyEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QGridLayout, QWidget

from setuav_studio.model.appearance import component_color, hex_to_rgb

from .constants import (
    FACE_COLORED,
    FACE_MONOCHROME,
    VIEW_PRESETS,
    WIRE_FEATURE,
    WIRE_FULL,
    ViewPreset,
    WireMode,
)
from .hud import StudioViewportHUD
from .layer import DEFAULT_LAYER, MASS_LAYER, Layer
from .primitives import (
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
from .scene_object import SceneObject
from .types import EnvelopeWireGeometry
from .widget import OpenGLViewer

logger = logging.getLogger(__name__)


_SETTING_PREFIX = "studio_viewport"
_SETTING_ORTHO = f"{_SETTING_PREFIX}_orthographic"
_SETTING_SOLID = f"{_SETTING_PREFIX}_show_solid"
_SETTING_WIRE = f"{_SETTING_PREFIX}_show_wireframe"
_SETTING_WIRE_MODE = f"{_SETTING_PREFIX}_wire_mode"
_SETTING_GRID = f"{_SETTING_PREFIX}_show_grid"
_SETTING_FACE_STYLE = f"{_SETTING_PREFIX}_face_style"


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


class ViewportRenderer(Protocol):
    """The widget that draws a :class:`StudioViewport` (``OpenGLViewer``)."""

    # A Qt ``Signal(object)``; pyright cannot match signal descriptors structurally.
    componentPicked: Any

    def update_theme_style(self) -> None: ...
    def set_scene_objects(self, objects: dict[str, SceneObject]) -> None: ...
    def set_component_colors(self, colors: dict[str, tuple[float, float, float]]) -> None: ...
    def set_overlays(
        self,
        overlay_id: str,
        primitives: list[VisualPrimitive] | tuple[VisualPrimitive, ...],
        on_top: bool = False,
    ) -> None: ...
    def clear_overlays(self, overlay_id: str) -> None: ...
    def set_selected_component(self, component_id: str | None) -> None: ...
    def set_selected_section(
        self,
        component_id: str | None,
        segment_index: int | None = None,
        section_index: int | None = None,
        color: tuple[float, float, float] | str | None = None,
    ) -> None: ...
    def set_selected_envelope(self, component_id: str | None) -> None: ...
    def fit_view(self) -> None: ...
    def set_view(self, azimuth: float, elevation: float) -> None: ...
    def set_orthographic(self, enabled: bool) -> None: ...
    def set_show_solid(self, show: bool) -> None: ...
    def set_show_wireframe(self, show: bool) -> None: ...
    def set_wire_mode(self, mode: str) -> None: ...
    def set_show_grid(self, show: bool) -> None: ...
    def set_transparent(self, transparent: bool) -> None: ...
    def set_face_style(self, face_style: str) -> None: ...
    def capture_screenshot(
        self, width: int, height: int, transparent_background: bool = False
    ) -> QImage | None: ...


def _renderer_widget(renderer: ViewportRenderer) -> QWidget:
    if not isinstance(renderer, QWidget):
        raise TypeError(f"A viewport renderer must be a QWidget, not {type(renderer).__name__}.")
    return renderer


class StudioViewport(QWidget):
    """Central 3D viewport widget.

    Provides the public ``add_*`` / ``remove`` / ``clear`` API that plugins use
    to populate the 3D scene.  Internally delegates all OpenGL rendering to the
    underlying viewer implementation.

    Layer visibility can be toggled independently so that, for example, a
    structures overlay can be shown or hidden without affecting the main
    geometry layer.
    """

    component_picked = Signal(str)
    selection_changed = Signal(object)
    layer_visibility_changed = Signal(str, bool)
    layers_changed = Signal()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        parent: QWidget | None = None,
        api: Any | None = None,
        renderer: ViewportRenderer | None = None,
    ) -> None:
        super().__init__(parent)
        self._api: Any | None = None

        # Selection state
        self._selected_component_id: str | None = None
        self._selected_section: tuple[str, int, int] | None = None
        self._selected_cg_component_id: str | None = None
        self._selected_envelope_component_id: str | None = None

        # Camera & Display state
        settings = QSettings()
        self._azimuth: float = 210.0
        self._elevation: float = 20.0
        self._orthographic: bool = _as_bool(settings.value(_SETTING_ORTHO, True), True)
        self._show_solid: bool = _as_bool(settings.value(_SETTING_SOLID, True), True)
        self._show_wireframe: bool = _as_bool(settings.value(_SETTING_WIRE, True), True)
        raw_wire_mode = str(settings.value(_SETTING_WIRE_MODE, WIRE_FEATURE)).lower()
        self._wire_mode: WireMode = WIRE_FULL if raw_wire_mode == WIRE_FULL else WIRE_FEATURE
        self._show_grid: bool = _as_bool(settings.value(_SETTING_GRID, True), True)
        self._transparent: bool = False
        raw_face = str(settings.value(_SETTING_FACE_STYLE, FACE_COLORED)).lower()
        self._face_style: str = (
            raw_face if raw_face in (FACE_COLORED, FACE_MONOCHROME) else FACE_COLORED
        )

        # Scene graph: object_id -> SceneObject
        self._objects: dict[str, SceneObject] = {}
        # Overlays drawn directly by the renderer: overlay_id -> (layer, primitives)
        self._overlays: dict[str, tuple[str, list[VisualPrimitive]]] = {}

        # Layers: layer_id -> Layer
        self._layers: dict[str, Layer] = {}

        self._grid_layout = QGridLayout(self)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(0)

        self._renderer: ViewportRenderer = renderer if renderer is not None else OpenGLViewer(self)
        self._install_renderer()

        self.add_layer(DEFAULT_LAYER, name="Default")
        self.add_layer(MASS_LAYER, name="Center of Gravity", on_top=True)

        # Floating bottom HUD bar
        self.hud = StudioViewportHUD(self)
        self._reposition_hud()

        if api is not None:
            self.bind_api(api)

    # ------------------------------------------------------------------
    # Lifecycle & Theme
    # ------------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._reposition_hud()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._reposition_hud()
        QTimer.singleShot(0, self._reposition_hud)

    def _reposition_hud(self) -> None:
        hint = self.hud.sizeHint()
        margin_bottom = 12  # Floating offset from bottom edge
        w = hint.width()
        h = hint.height()
        x = max(0, (self.width() - w) // 2)
        y = max(0, self.height() - h - margin_bottom)
        self.hud.setGeometry(x, y, w, h)
        self.hud.raise_()

    def update_theme_style(self) -> None:
        """Propagate theme styling to the HUD bar and attached renderer."""
        self.hud.update_theme_style()
        self._reposition_hud()
        self._renderer.update_theme_style()

    # ------------------------------------------------------------------
    # Renderer & API binding
    # ------------------------------------------------------------------

    def attach_renderer(self, renderer: ViewportRenderer) -> None:
        """Replace the renderer widget that draws the viewport."""
        old = _renderer_widget(self._renderer)
        self._grid_layout.removeWidget(old)
        old.setParent(None)
        old.deleteLater()
        self._renderer = renderer
        self._install_renderer()
        self._sync_renderer()
        for overlay_id in self._overlays:
            self._push_overlay(overlay_id)
        self._reposition_hud()

    def _install_renderer(self) -> None:
        """Embed the renderer and give it the current display state."""
        renderer = self._renderer
        self._grid_layout.addWidget(_renderer_widget(renderer), 0, 0)
        renderer.set_orthographic(self._orthographic)
        renderer.set_show_solid(self._show_solid)
        renderer.set_show_wireframe(self._show_wireframe)
        renderer.set_wire_mode(self._wire_mode)
        renderer.set_show_grid(self._show_grid)
        renderer.set_transparent(self._transparent)
        renderer.set_face_style(self._face_style)
        renderer.set_view(self._azimuth, self._elevation)
        renderer.componentPicked.connect(self._on_renderer_component_picked)

    @property
    def renderer(self) -> ViewportRenderer:
        """Return the attached renderer widget."""
        return self._renderer

    @property
    def viewer(self) -> OpenGLViewer | None:
        """Return the underlying OpenGLViewer instance, or None."""
        return self._renderer if isinstance(self._renderer, OpenGLViewer) else None

    def bind_api(self, api: Any) -> None:
        """Bind StudioAPI to synchronize selections bi-directionally with the app."""
        self._api = api
        api._host.bind_viewport(self)
        api.on_selection_changed(self._on_api_selection_changed)
        api.on_section_selection_changed(self._on_api_section_selection_changed)
        self.component_picked.connect(self._on_component_picked_to_api)
        self.layer_visibility_changed.connect(lambda _layer, _visible: api.refresh_toolbar_states())
        api.on_project_content_changed(lambda _doc: self._on_project_content_changed())
        # A newly opened project has no content change yet; its markers are built here.
        api.on_project_changed(lambda _doc: self._on_project_content_changed())

    def _on_project_content_changed(self) -> None:
        self.update_component_colors()
        self.update_component_cg()
        self.update_aircraft_cg()

    def update_component_colors(self) -> None:
        """Give the renderer the color of every component of the project."""
        project = self._api.project if self._api is not None else None
        components = project.data.get("components", []) if project is not None else []
        by_id = {str(c["id"]): c for c in components if isinstance(c, dict) and c.get("id")}
        self._renderer.set_component_colors(
            {
                component_id: hex_to_rgb(component_color(component, by_id))
                for component_id, component in by_id.items()
            }
        )

    # ------------------------------------------------------------------
    # Layer management
    # ------------------------------------------------------------------

    def add_layer(
        self,
        layer_id: str,
        *,
        name: str = "",
        visible: bool = True,
        on_top: bool = False,
    ) -> Layer:
        """Register a new layer or update an existing one.

        Args:
            layer_id: Unique identifier for the layer (e.g. 'structures').
            name: Human-readable display name. Defaults to *layer_id*.
            visible: Initial visibility state. Defaults to True.
            on_top: Draw the layer's overlay lines over the model. Defaults to False.

        Returns:
            The created or updated :class:`Layer` instance.
        """
        is_new = layer_id not in self._layers
        if not is_new:
            layer = self._layers[layer_id]
            if name:
                layer.name = name
            layer.visible = visible
            layer.on_top = on_top
        else:
            layer = Layer(layer_id=layer_id, name=name or layer_id, visible=visible, on_top=on_top)
            self._layers[layer_id] = layer
        self._sync_renderer()
        if is_new:
            self.layers_changed.emit()
        return layer

    def remove_layer(self, layer_id: str) -> bool:
        """Remove a registered layer and all objects and overlays belonging to it.

        Args:
            layer_id: Identifier of the layer to remove.

        Returns:
            True if the layer existed and was removed, False otherwise.
        """
        if layer_id not in self._layers:
            return False
        del self._layers[layer_id]
        self._objects = {oid: obj for oid, obj in self._objects.items() if obj.layer != layer_id}
        for overlay_id in [oid for oid, (layer, _p) in self._overlays.items() if layer == layer_id]:
            self.clear_overlays(overlay_id)
        self._sync_renderer()
        self.layers_changed.emit()
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

    def _registered_layer(self, layer_id: str) -> Layer:
        """The registered layer *layer_id*; layers are registered with :meth:`add_layer`."""
        if layer_id not in self._layers:
            raise ValueError(f"Viewport layer {layer_id!r} is not registered.")
        return self._layers[layer_id]

    def set_layer_visible(self, layer: str, visible: bool) -> None:
        """Show or hide all objects and overlays belonging to *layer*."""
        self._registered_layer(layer).visible = visible
        self._sync_renderer()
        for overlay_id, (overlay_layer, _primitives) in self._overlays.items():
            if overlay_layer == layer:
                self._push_overlay(overlay_id)
        self.layer_visibility_changed.emit(layer, visible)

    def is_layer_visible(self, layer: str) -> bool:
        """Return whether *layer* is currently visible."""
        return self._registered_layer(layer).visible

    # ------------------------------------------------------------------
    # Generic add / remove / query
    # ------------------------------------------------------------------

    def add_object(self, obj: SceneObject) -> SceneObject:
        """Insert or replace a scene object by its ``object_id``.

        The object's layer must be registered with :meth:`add_layer`.
        """
        self._registered_layer(obj.layer)
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

    def object_ids(self, *, layer: str | None = None) -> list[str]:
        """Return IDs of all objects, optionally filtered by *layer*."""
        if layer is None:
            return list(self._objects)
        return [oid for oid, obj in self._objects.items() if obj.layer == layer]

    # ------------------------------------------------------------------
    # Selection management
    # ------------------------------------------------------------------

    def set_selected(self, component_id: str | None) -> None:
        """Highlight the objects that draw the component ``component_id``."""
        if self._selected_component_id == component_id:
            return
        self._selected_component_id = component_id
        self._renderer.set_selected_component(component_id)
        self.selection_changed.emit(component_id)

    def selected_component_id(self) -> str | None:
        """Return the selected component id, or None."""
        return self._selected_component_id

    def set_selected_section(
        self,
        component_id: str | None,
        segment_index: int | None = None,
        section_index: int | None = None,
        color: tuple[float, float, float] | str | None = None,
    ) -> None:
        """Set the selected section or station highlight."""
        if component_id is not None and section_index is not None:
            seg = segment_index if segment_index is not None else 0
            self._selected_section = (component_id, seg, section_index)
        else:
            self._selected_section = None
        self._renderer.set_selected_section(component_id, segment_index, section_index, color=color)

    def selected_section(self) -> tuple[str, int, int] | None:
        """Return the currently selected section tuple, or None."""
        return self._selected_section

    # ------------------------------------------------------------------
    # Camera and display controls
    # ------------------------------------------------------------------

    def fit_view(self) -> None:
        """Fit the camera to frame all visible objects in the viewport."""
        self._renderer.fit_view()

    def set_view(self, azimuth: float, elevation: float) -> None:
        """Set the camera orbit angles in degrees."""
        self._azimuth = azimuth
        self._elevation = max(-89.0, min(89.0, elevation))
        self._renderer.set_view(self._azimuth, self._elevation)

    def view_angles(self) -> tuple[float, float]:
        """Return the current camera (azimuth, elevation) angles."""
        return self._azimuth, self._elevation

    def set_view_preset(self, preset: ViewPreset) -> None:
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
        QSettings().setValue(_SETTING_ORTHO, self._orthographic)
        self._renderer.set_orthographic(self._orthographic)

    def is_orthographic(self) -> bool:
        """Return whether orthographic projection is active."""
        return self._orthographic

    def set_show_solid(self, show: bool) -> None:
        """Toggle solid surface rendering."""
        self._show_solid = bool(show)
        QSettings().setValue(_SETTING_SOLID, self._show_solid)
        self._renderer.set_show_solid(self._show_solid)

    def is_show_solid(self) -> bool:
        """Return whether solid surfaces are visible."""
        return self._show_solid

    def set_show_wireframe(self, show: bool) -> None:
        """Toggle wireframe lines."""
        self._show_wireframe = bool(show)
        QSettings().setValue(_SETTING_WIRE, self._show_wireframe)
        self._renderer.set_show_wireframe(self._show_wireframe)

    def is_show_wireframe(self) -> bool:
        """Return whether wireframes are visible."""
        return self._show_wireframe

    def set_wire_mode(self, mode: WireMode) -> None:
        """Set wireframe display mode ('feature' or 'full')."""
        if mode not in (WIRE_FEATURE, WIRE_FULL):
            raise ValueError(f"Unknown wire mode: {mode}. Must be 'feature' or 'full'.")
        self._wire_mode = mode
        QSettings().setValue(_SETTING_WIRE_MODE, self._wire_mode)
        self._renderer.set_wire_mode(mode)

    def wire_mode(self) -> WireMode:
        """Return the current wireframe mode."""
        return self._wire_mode

    def set_show_grid(self, show: bool) -> None:
        """Toggle 3D ground reference grid."""
        self._show_grid = bool(show)
        QSettings().setValue(_SETTING_GRID, self._show_grid)
        self._renderer.set_show_grid(self._show_grid)

    def is_show_grid(self) -> bool:
        """Return whether the ground grid is visible."""
        return self._show_grid

    def set_transparent(self, transparent: bool) -> None:
        """Toggle transparency / X-ray mode."""
        self._transparent = bool(transparent)
        self._renderer.set_transparent(self._transparent)

    def is_transparent(self) -> bool:
        """Return whether transparency mode is active."""
        return self._transparent

    def set_face_style(self, style: Literal["colored", "monochrome"]) -> None:
        """Set surface shading style ('colored' or 'monochrome')."""
        if style not in (FACE_COLORED, FACE_MONOCHROME):
            raise ValueError(f"Unknown face style: {style}. Must be 'colored' or 'monochrome'.")
        self._face_style = style
        QSettings().setValue(_SETTING_FACE_STYLE, self._face_style)
        self._renderer.set_face_style(style)

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
        return self._renderer.capture_screenshot(
            width, height, transparent_background=transparent_background
        )

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
        component_id: str | None,
        name: str = "",
        layer: str = "geometry",
        color: ColorRGBA = (1.0, 0.82, 0.10, 1.0),
        interpolation: Literal["linear", "smooth"] = "smooth",
        station_spacing: float = 10.0,
        closed_ends: bool = True,
        wireframe: bool = True,
        solid: bool = True,
        envelope: EnvelopeWireGeometry | dict[str, Any] | None = None,
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
            station_spacing=station_spacing,
            closed_ends=closed_ends,
            wireframe=wireframe,
            solid=solid,
        )
        obj = SceneObject(
            object_id=object_id,
            component_id=component_id,
            layer=layer,
            name=name or object_id,
            primitives=[prim],
            envelope=envelope,
        )
        return self.add_object(obj)

    def add_box(
        self,
        object_id: str,
        center: Point3D,
        size: Point3D,
        *,
        component_id: str | None,
        name: str = "",
        layer: str = DEFAULT_LAYER,
        color: ColorRGBA = (0.2, 0.6, 1.0, 0.4),
        rotation: Point3D = (0.0, 0.0, 0.0),
        wireframe: bool = True,
        solid: bool = True,
        envelope: EnvelopeWireGeometry | dict[str, Any] | None = None,
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
            object_id=object_id,
            component_id=component_id,
            layer=layer,
            name=name or object_id,
            primitives=[prim],
            envelope=envelope,
        )
        return self.add_object(obj)

    def add_cylinder(
        self,
        object_id: str,
        start: Point3D,
        end: Point3D,
        radius: float,
        *,
        component_id: str | None,
        name: str = "",
        layer: str = DEFAULT_LAYER,
        color: ColorRGBA = (0.2, 0.2, 0.2, 0.9),
        wireframe: bool = True,
        solid: bool = True,
        segments: int = 24,
        envelope: EnvelopeWireGeometry | dict[str, Any] | None = None,
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
            object_id=object_id,
            component_id=component_id,
            layer=layer,
            name=name or object_id,
            primitives=[prim],
            envelope=envelope,
        )
        return self.add_object(obj)

    def add_ring(
        self,
        object_id: str,
        center: Point3D,
        *,
        component_id: str | None,
        name: str = "",
        layer: str = DEFAULT_LAYER,
        normal: Point3D = (1.0, 0.0, 0.0),
        radius: float = 50.0,
        color: ColorRGBA = (1.0, 0.5, 0.0, 1.0),
        segments: int = 36,
        envelope: EnvelopeWireGeometry | dict[str, Any] | None = None,
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
            object_id=object_id,
            component_id=component_id,
            layer=layer,
            name=name or object_id,
            primitives=[prim],
            envelope=envelope,
        )
        return self.add_object(obj)

    def add_plane(
        self,
        object_id: str,
        center: Point3D,
        *,
        component_id: str | None,
        name: str = "",
        layer: str = DEFAULT_LAYER,
        normal: Point3D = (1.0, 0.0, 0.0),
        width: float = 200.0,
        height: float = 200.0,
        color: ColorRGBA = (1.0, 0.5, 0.0, 0.4),
        wireframe: bool = True,
        solid: bool = True,
        envelope: EnvelopeWireGeometry | dict[str, Any] | None = None,
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
            object_id=object_id,
            component_id=component_id,
            layer=layer,
            name=name or object_id,
            primitives=[prim],
            envelope=envelope,
        )
        return self.add_object(obj)

    def add_lines(
        self,
        object_id: str,
        lines: Sequence[tuple[Point3D, Point3D]],
        *,
        component_id: str | None,
        name: str = "",
        layer: str = DEFAULT_LAYER,
        color: ColorRGBA = (1.0, 1.0, 1.0, 1.0),
        envelope: EnvelopeWireGeometry | dict[str, Any] | None = None,
    ) -> SceneObject:
        """Add a set of line segments."""
        prim = LineSegmentsPrimitive(
            lines=tuple(lines),
            color=color,
        )
        obj = SceneObject(
            object_id=object_id,
            component_id=component_id,
            layer=layer,
            name=name or object_id,
            primitives=[prim],
            envelope=envelope,
        )
        return self.add_object(obj)

    def add_triangles(
        self,
        object_id: str,
        triangles: Sequence[tuple[Point3D, Point3D, Point3D]],
        *,
        component_id: str | None,
        name: str = "",
        layer: str = DEFAULT_LAYER,
        color: ColorRGBA = (0.7, 0.75, 0.8, 0.7),
        solid: bool = True,
        envelope: EnvelopeWireGeometry | dict[str, Any] | None = None,
    ) -> SceneObject:
        """Add arbitrary triangles forming a solid surface."""
        prim = TrianglesPrimitive(
            triangles=tuple(triangles),
            color=color,
            solid=solid,
        )
        obj = SceneObject(
            object_id=object_id,
            component_id=component_id,
            layer=layer,
            name=name or object_id,
            primitives=[prim],
            envelope=envelope,
        )
        return self.add_object(obj)

    def add_points(
        self,
        object_id: str,
        points: Sequence[Point3D],
        *,
        component_id: str | None,
        name: str = "",
        layer: str = DEFAULT_LAYER,
        color: ColorRGBA = (1.0, 0.3, 0.1, 1.0),
        size: float = 4.0,
        envelope: EnvelopeWireGeometry | dict[str, Any] | None = None,
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
            object_id=object_id,
            component_id=component_id,
            layer=layer,
            name=name or object_id,
            primitives=[prim],
            envelope=envelope,
        )
        return self.add_object(obj)

    def add_arrows(
        self,
        object_id: str,
        arrows: Sequence[tuple[Point3D, Point3D]],
        *,
        component_id: str | None,
        name: str = "",
        layer: str = DEFAULT_LAYER,
        color: ColorRGBA = (0.2, 0.8, 0.2, 1.0),
        envelope: EnvelopeWireGeometry | dict[str, Any] | None = None,
    ) -> SceneObject:
        """Add directional arrows (line from start to end).

        Arrow heads are not yet implemented; arrows are rendered as plain
        line segments for now.
        """
        prim = LineSegmentsPrimitive(lines=tuple(arrows), color=color)
        obj = SceneObject(
            object_id=object_id,
            component_id=component_id,
            layer=layer,
            name=name or object_id,
            primitives=[prim],
            envelope=envelope,
        )
        return self.add_object(obj)

    def add_primitive(
        self,
        object_id: str,
        primitive: VisualPrimitive,
        *,
        component_id: str | None,
        name: str = "",
        layer: str = DEFAULT_LAYER,
        envelope: EnvelopeWireGeometry | dict[str, Any] | None = None,
    ) -> SceneObject:
        """Add a raw SDK visual primitive directly."""
        obj = SceneObject(
            object_id=object_id,
            component_id=component_id,
            layer=layer,
            name=name or object_id,
            primitives=[primitive],
            envelope=envelope,
        )
        return self.add_object(obj)

    # ------------------------------------------------------------------
    # Internal renderer synchronisation
    # ------------------------------------------------------------------

    def _sync_renderer(self) -> None:
        """Push the visible scene objects to the renderer."""
        self._renderer.set_scene_objects(
            {
                oid: obj
                for oid, obj in self._objects.items()
                if obj.visible and self.is_layer_visible(obj.layer)
            }
        )

    def set_overlays(
        self, overlay_id: str, primitives: Sequence[VisualPrimitive], *, layer: str
    ) -> None:
        """Set the primitives the renderer draws as overlay *overlay_id*.

        The overlay belongs to *layer*, which its owner registers with
        :meth:`add_layer`; it is drawn only while that layer is visible.
        """
        self._registered_layer(layer)
        self._overlays[overlay_id] = (layer, list(primitives))
        self._push_overlay(overlay_id)

    def clear_overlays(self, overlay_id: str) -> None:
        """Remove overlay *overlay_id*."""
        self._overlays.pop(overlay_id, None)
        self._renderer.clear_overlays(overlay_id)

    def _push_overlay(self, overlay_id: str) -> None:
        layer, primitives = self._overlays[overlay_id]
        if self.is_layer_visible(layer):
            on_top = self._registered_layer(layer).on_top
            self._renderer.set_overlays(overlay_id, primitives, on_top=on_top)
        else:
            self._renderer.clear_overlays(overlay_id)

    def set_selected_cg(self, component_id: str | None) -> None:
        """Update 3D CG marker overlay for the selected component."""
        self._selected_cg_component_id = component_id
        if component_id is None or self._api is None:
            self.clear_overlays("component_cg")
            return
        project = self._api.project
        if project is None:
            self.clear_overlays("component_cg")
            return
        from .cg_marker import build_component_cg_primitives

        prims = build_component_cg_primitives(component_id, project, self._api.subpart_types)
        if prims:
            self.set_overlays("component_cg", prims, layer=MASS_LAYER)
        else:
            self.clear_overlays("component_cg")

    def update_component_cg(self) -> None:
        """Refresh the active component CG marker (e.g. after mass/geometry edit)."""
        if self._selected_cg_component_id:
            self.set_selected_cg(self._selected_cg_component_id)

    def set_selected_envelope(self, component_id: str | None) -> None:
        """Show the envelope wireframe of the selected component."""
        self._selected_envelope_component_id = component_id
        self._renderer.set_selected_envelope(component_id)

    def update_aircraft_cg(self) -> None:
        """Refresh the aircraft total CG marker overlay."""
        if self._api is None:
            self.clear_overlays("aircraft_cg")
            return
        project = self._api.project
        if project is None:
            self.clear_overlays("aircraft_cg")
            return
        from .cg_marker import build_aircraft_cg_primitives

        prims = build_aircraft_cg_primitives(project)
        if prims:
            self.set_overlays("aircraft_cg", prims, layer=MASS_LAYER)
        else:
            self.clear_overlays("aircraft_cg")

    # ------------------------------------------------------------------
    # Selection event handlers
    # ------------------------------------------------------------------

    def _on_renderer_component_picked(self, component_id: Any) -> None:
        """Handle pick event emitted by the low-level OpenGL widget."""
        if not isinstance(component_id, str) or not component_id:
            self.set_selected(None)
            self.component_picked.emit("")
            return
        self.set_selected(component_id)
        self.component_picked.emit(component_id)

    def _on_api_selection_changed(self, selection: Any | None) -> None:
        """Highlight the selected element; an active envelope or CG view follows it.

        Selections are element payloads keyed by ``id``.
        """
        if selection is None:
            self.set_selected(None)
            self.set_selected_cg(None)
            self.set_selected_envelope(None)
            return
        component_id = str(selection["id"])
        self.set_selected(component_id)
        if self._selected_envelope_component_id:
            self.set_selected_envelope(component_id)
        elif self._selected_cg_component_id:
            self.set_selected_cg(component_id)

    def _on_api_section_selection_changed(
        self,
        selection: tuple[str, int, int] | tuple[str, int, int, Any] | None,
    ) -> None:
        """Respond to section selection events from StudioAPI."""
        if selection is None:
            self.set_selected_section(None)
            return
        if len(selection) == 4:
            comp_id, seg_idx, sec_idx, color = selection
            self.set_selected_section(comp_id, seg_idx, sec_idx, color=color)
        else:
            comp_id, seg_idx, sec_idx = selection
            self.set_selected_section(comp_id, seg_idx, sec_idx)

    def _on_component_picked_to_api(self, component_id: str) -> None:
        """Select the picked component in StudioAPI so the tree and properties follow."""
        if self._api is None:
            return
        if not component_id:
            self._api.set_selection(None)
            return
        project = self._api.project
        if project is None:
            return
        component = project.get_component(component_id)
        if component is None:
            raise ValueError(
                f"The viewport draws component {component_id!r}, which the project lacks"
            )
        self._api.set_selection(component)
