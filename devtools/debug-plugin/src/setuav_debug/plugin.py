"""Debug Plugin for Setuav Studio."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from setuav_studio.api import (
    ComponentTypeContribution,
    PanelContribution,
    StudioAPI,
    ToolbarContribution,
    ToolbarMenuItemContribution,
    ToolContribution,
)
from setuav_studio.ui.style.icons import register_plugin_icons, unregister_plugin_icons
from setuav_studio.ui.viewport import StudioViewport

from .components import (
    DEBUG_LAYER,
    TYPE_DEBUG_ARROW,
    TYPE_DEBUG_BOX,
    TYPE_DEBUG_CYLINDER,
    TYPE_DEBUG_LINE,
    TYPE_DEBUG_LOFT,
    TYPE_DEBUG_PLANE,
    TYPE_DEBUG_POINT,
    TYPE_DEBUG_RING,
    TYPE_DEBUG_TRIANGLE,
    ArrowComponent,
    ArrowComponentEditor,
    BoxComponent,
    BoxComponentEditor,
    CylinderComponent,
    CylinderComponentEditor,
    LineComponent,
    LineComponentEditor,
    LoftComponent,
    LoftComponentEditor,
    PlaneComponent,
    PlaneComponentEditor,
    PointComponent,
    PointComponentEditor,
    RingComponent,
    RingComponentEditor,
    TriangleComponent,
    TriangleComponentEditor,
    add_debug_component,
    clear_debug_components,
    create_arrow_component,
    create_box_component,
    create_cylinder_component,
    create_line_component,
    create_loft_component,
    create_plane_component,
    create_point_component,
    create_ring_component,
    create_triangle_component,
    debug_envelope_types,
    sync_debug_components_to_viewport,
    sync_debug_envelope,
)
from .solver import SOLVER_ID_MOCK_GENERATOR, MockGeneratorSolver

logger = logging.getLogger(__name__)

TOOLBAR_ADD_PRIMITIVE_ID = "debug.toolbar.add_primitive"
TOOLBAR_MOCK_ANALYSIS_ID = "debug.toolbar.mock_analysis"
PANEL_ID_DEBUG = "debug:panel"


class DebugPlugin:
    """Plugin for debugging and end-to-end verification of Setuav Studio core features."""

    id = "org.setuav.studio.debug"
    name = "Debug"
    version = "0.1.0"

    def __init__(self) -> None:
        self._api: StudioAPI | None = None
        self._tool_contributions: list[ToolContribution] = []
        self._component_type_ids: list[str] = []

    def activate(self, api: StudioAPI) -> None:
        """Activate the debug plugin."""
        register_plugin_icons(self.id, Path(__file__).parent / "assets" / "icons")
        self._api = api
        self._register_panel(api)
        self._register_component_types(api)
        self._register_toolbar_tools(api)
        self._register_solvers(api)

        for type_id in debug_envelope_types():
            api.register_component_deriver(type_id, _derive_envelope)
        api.derive_components()
        api.on_project_changed(self._on_project_changed)
        api.on_project_content_changed(self._on_project_content_changed)

        if api.project is not None:
            self._sync_viewport(api.project)

        logger.info("DebugPlugin activated")

    def deactivate(self, api: StudioAPI) -> None:
        """Deactivate the debug plugin."""
        unregister_plugin_icons(self.id)
        api.unregister_toolbar_item(TOOLBAR_ADD_PRIMITIVE_ID)
        api.unregister_toolbar_item(TOOLBAR_MOCK_ANALYSIS_ID)
        for tool in self._tool_contributions:
            api.unregister_tool(tool)
        self._tool_contributions.clear()
        self._unregister_solvers(api)
        api.remove_project_listener(self._on_project_changed)
        api.remove_project_content_listener(self._on_project_content_changed)
        for type_id in debug_envelope_types():
            api.unregister_component_deriver(type_id)
        self._unregister_component_types(api)
        self._unregister_panel(api)

        if api.viewport is not None:
            api.viewport.remove_layer(DEBUG_LAYER)

        self._api = None
        logger.info("DebugPlugin deactivated")

    # ------------------------------------------------------------------
    # Component Types Registration
    # ------------------------------------------------------------------

    def _register_component_types(self, api: StudioAPI) -> None:
        """Register the primitive component types with their editors and models."""
        types: list[tuple[str, str, str, Any, Any]] = [
            (TYPE_DEBUG_BOX, "Box", "fa6s.cube", BoxComponent, BoxComponentEditor),
            (
                TYPE_DEBUG_CYLINDER,
                "Cylinder",
                "fa6s.database",
                CylinderComponent,
                CylinderComponentEditor,
            ),
            (TYPE_DEBUG_RING, "Ring", "fa6s.circle-notch", RingComponent, RingComponentEditor),
            (TYPE_DEBUG_PLANE, "Plane", "fa6s.square", PlaneComponent, PlaneComponentEditor),
            (
                TYPE_DEBUG_LINE,
                "Line",
                "fa6s.arrows-up-down-left-right",
                LineComponent,
                LineComponentEditor,
            ),
            (
                TYPE_DEBUG_TRIANGLE,
                "Triangle",
                "fa6s.draw-polygon",
                TriangleComponent,
                TriangleComponentEditor,
            ),
            (TYPE_DEBUG_LOFT, "Loft", "fa6s.plane", LoftComponent, LoftComponentEditor),
            (TYPE_DEBUG_POINT, "Point", "mdi6.dots-hexagon", PointComponent, PointComponentEditor),
            (
                TYPE_DEBUG_ARROW,
                "Arrow",
                "fa6s.location-arrow",
                ArrowComponent,
                ArrowComponentEditor,
            ),
        ]
        self._component_type_ids = [type_id for type_id, *_rest in types]
        for type_id, name, icon, model, editor_class in types:
            api.register_component_type(
                ComponentTypeContribution(
                    id=type_id,
                    name=name,
                    icon=icon,
                    model=model,
                    editor=lambda component, cls=editor_class: cls(api, component),
                    category="Debug",
                )
            )

    def _unregister_component_types(self, api: StudioAPI) -> None:
        for type_id in self._component_type_ids:
            api.unregister_component_type(type_id)

    # ------------------------------------------------------------------
    # Project & Viewport Synchronization
    # ------------------------------------------------------------------

    def _on_project_changed(self, project: Any) -> None:
        self._sync_viewport(project)

    def _on_project_content_changed(self, project: Any) -> None:
        self._sync_viewport(project)

    def _sync_viewport(self, project: Any) -> None:
        vp = self._get_viewport()
        if vp is not None:
            if not vp.has_layer(DEBUG_LAYER):
                vp.add_layer(DEBUG_LAYER, name="Debug")
            sync_debug_components_to_viewport(vp, project)

    def _get_viewport(self) -> StudioViewport | None:
        """Get the StudioViewport instance, showing the panel if necessary."""
        if self._api is None:
            return None
        vp = self._api.viewport
        if vp is None:
            self._api.show_panel("studio:viewer-3d")
            vp = self._api.viewport
        return vp

    def _add_component(self, factory_fn: Any, base_id: str, base_name: str) -> None:
        """Add a primitive component to the active project and frame viewport."""
        if self._api is None:
            return
        comp = add_debug_component(self._api, factory_fn, base_id, base_name)
        if comp is not None:
            vp = self._get_viewport()
            if vp is not None:
                vp.fit_view()

    # ------------------------------------------------------------------
    # Toolbar Tools
    # ------------------------------------------------------------------

    def _register_toolbar_tools(self, api: StudioAPI) -> None:
        """Register debug component tools to the toolbar."""
        menu_items = (
            ToolbarMenuItemContribution(
                title="Box",
                callback=lambda: self._add_component(create_box_component, "box", "Box"),
                icon="fa6s.cube",
            ),
            ToolbarMenuItemContribution(
                title="Cylinder",
                callback=lambda: self._add_component(
                    create_cylinder_component, "cylinder", "Cylinder"
                ),
                icon="fa6s.database",
            ),
            ToolbarMenuItemContribution(
                title="Ring",
                callback=lambda: self._add_component(create_ring_component, "ring", "Ring"),
                icon="fa6s.circle-notch",
            ),
            ToolbarMenuItemContribution(
                title="Plane",
                callback=lambda: self._add_component(create_plane_component, "plane", "Plane"),
                icon="fa6s.square",
            ),
            ToolbarMenuItemContribution(
                title="Line",
                callback=lambda: self._add_component(create_line_component, "line", "Line"),
                icon="fa6s.arrows-up-down-left-right",
            ),
            ToolbarMenuItemContribution(
                title="Triangle",
                callback=lambda: self._add_component(
                    create_triangle_component, "triangle", "Triangle"
                ),
                icon="fa6s.draw-polygon",
            ),
            ToolbarMenuItemContribution(
                title="Loft",
                callback=lambda: self._add_component(create_loft_component, "loft", "Loft"),
                icon="fa6s.plane",
            ),
            ToolbarMenuItemContribution(
                title="Point",
                callback=lambda: self._add_component(create_point_component, "point", "Point"),
                icon="mdi6.dots-hexagon",
            ),
            ToolbarMenuItemContribution(
                title="Arrow",
                callback=lambda: self._add_component(create_arrow_component, "arrow", "Arrow"),
                icon="fa6s.location-arrow",
            ),
            ToolbarMenuItemContribution(
                title="Clear All",
                callback=lambda: clear_debug_components(api),
                icon="fa6s.trash-can",
            ),
        )

        contribution = ToolbarContribution(
            id=TOOLBAR_ADD_PRIMITIVE_ID,
            title="Primitives",
            icon="fa6s.cube",
            menu_items=menu_items,
            group="debug",
            order=10,
        )
        api.register_toolbar_item(contribution)

        # Mock Analysis Toolbar & Menu Tools
        api.register_toolbar_item(
            ToolbarContribution(
                id=TOOLBAR_MOCK_ANALYSIS_ID,
                title="Add Mock Analysis",
                callback=self._add_mock_analysis_config,
                icon="fa6s.chart-line",
                group="debug",
                order=20,
            )
        )

        tool_panel = ToolContribution(
            title="Open Debug Panel",
            callback=lambda: api.show_panel(PANEL_ID_DEBUG),
            group="Debug",
            icon="debug_panel",
        )
        api.register_tool(tool_panel)
        self._tool_contributions.append(tool_panel)

    # ------------------------------------------------------------------
    # Panel Registration
    # ------------------------------------------------------------------

    def _register_panel(self, api: StudioAPI) -> None:
        """Register the debug dock panel (hidden by default)."""
        from PySide6.QtCore import Qt

        from .panel import DebugPanel

        api.register_panel(
            PanelContribution(
                id=PANEL_ID_DEBUG,
                title="Debug",
                factory=lambda: DebugPanel(api),
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                icon="debug_panel",
                default_visible=False,
            )
        )

    def _unregister_panel(self, api: StudioAPI) -> None:
        """Unregister the debug dock panel."""
        api.unregister_panel(PANEL_ID_DEBUG)

    # ------------------------------------------------------------------
    # Solvers Registration & Execution
    # ------------------------------------------------------------------

    def _register_solvers(self, api: StudioAPI) -> None:
        """Register the debug mock analysis solver."""
        api.register_solver(SOLVER_ID_MOCK_GENERATOR, MockGeneratorSolver)

    def _unregister_solvers(self, api: StudioAPI) -> None:
        """Unregister the debug mock analysis solver."""
        api.unregister_solver(SOLVER_ID_MOCK_GENERATOR)

    def _add_mock_analysis_config(self) -> None:
        """Add a configurable mock analysis to the active project."""
        if self._api is None or self._api.project is None:
            if self._api is not None:
                self._api.show_status("Open or create a project first.", "warning", 3000)
            return

        from setuav_studio.solver import SolverConfig

        config = SolverConfig(
            solver_id=SOLVER_ID_MOCK_GENERATOR,
            name="Mock",
            parameters=MockGeneratorSolver.default_parameters(),
        )
        self._api.add_solver_config(config)
        self._api.show_status("Added Mock configuration.", "success", 3000)


def _derive_envelope(component: dict[str, Any], _components: Mapping[str, dict[str, Any]]) -> None:
    sync_debug_envelope(component)
