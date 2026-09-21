"""Debug Plugin for Setuav Studio."""

from __future__ import annotations

import logging
from typing import Any

from setuav_studio.api import (
    StudioAPI,
    ToolbarContribution,
    ToolbarMenuItemContribution,
    ToolContribution,
)
from setuav_studio.ui.viewport import ViewportProtocol

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
    sync_debug_components_to_viewport,
)
from .solver import SOLVER_ID_MOCK_GENERATOR, MockGeneratorSolver

logger = logging.getLogger(__name__)

TOOLBAR_ADD_PRIMITIVE_ID = "debug.toolbar.add_primitive"
TOOLBAR_MOCK_ANALYSIS_ID = "debug.toolbar.mock_analysis"


class DebugPlugin:
    """Plugin for debugging and end-to-end verification of Setuav Studio core features."""

    id = "org.setuav.studio.debug"
    name = "Debug"
    version = "0.1.0"
    priority = 100

    def __init__(self) -> None:
        self._api: StudioAPI | None = None
        self._tool_contributions: list[ToolContribution] = []

    def activate(self, api: StudioAPI) -> None:
        """Activate the debug plugin."""
        self._api = api
        self._register_component_types(api)
        self._register_toolbar_tools(api)
        self._register_solvers(api)

        api.on_project_changed(self._on_project_changed)
        api.on_project_content_changed(self._on_project_content_changed)

        if api.current_project is not None:
            self._sync_viewport(api.current_project)

        logger.info("DebugPlugin activated")

    def deactivate(self, api: StudioAPI) -> None:
        """Deactivate the debug plugin."""
        api.unregister_toolbar_item(TOOLBAR_ADD_PRIMITIVE_ID)
        api.unregister_toolbar_item(TOOLBAR_MOCK_ANALYSIS_ID)
        for tool in self._tool_contributions:
            api.unregister_tool(tool)
        self._tool_contributions.clear()
        self._unregister_solvers(api)
        api.remove_project_listener(self._on_project_changed)
        api.remove_project_content_listener(self._on_project_content_changed)
        self._unregister_component_types(api)

        vp = self._get_viewport()
        if vp is not None:
            vp.clear(layer=DEBUG_LAYER)

        self._api = None
        logger.info("DebugPlugin deactivated")

    # ------------------------------------------------------------------
    # Component Types Registration
    # ------------------------------------------------------------------

    def _register_component_types(self, api: StudioAPI) -> None:
        """Register editors and icons for all primitive component types."""
        # 1. Component Editors
        api.register_component_editor(
            TYPE_DEBUG_BOX,
            lambda comp: BoxComponentEditor(api, comp),
        )
        api.register_component_editor(
            TYPE_DEBUG_CYLINDER,
            lambda comp: CylinderComponentEditor(api, comp),
        )
        api.register_component_editor(
            TYPE_DEBUG_RING,
            lambda comp: RingComponentEditor(api, comp),
        )
        api.register_component_editor(
            TYPE_DEBUG_PLANE,
            lambda comp: PlaneComponentEditor(api, comp),
        )
        api.register_component_editor(
            TYPE_DEBUG_LINE,
            lambda comp: LineComponentEditor(api, comp),
        )
        api.register_component_editor(
            TYPE_DEBUG_TRIANGLE,
            lambda comp: TriangleComponentEditor(api, comp),
        )
        api.register_component_editor(
            TYPE_DEBUG_LOFT,
            lambda comp: LoftComponentEditor(api, comp),
        )
        api.register_component_editor(
            TYPE_DEBUG_POINT,
            lambda comp: PointComponentEditor(api, comp),
        )
        api.register_component_editor(
            TYPE_DEBUG_ARROW,
            lambda comp: ArrowComponentEditor(api, comp),
        )

        # 2. Component Icons
        api.register_component_icon(TYPE_DEBUG_BOX, "fa6s.cube")
        api.register_component_icon(TYPE_DEBUG_CYLINDER, "fa6s.database")
        api.register_component_icon(TYPE_DEBUG_RING, "fa6s.circle-notch")
        api.register_component_icon(TYPE_DEBUG_PLANE, "fa6s.square")
        api.register_component_icon(TYPE_DEBUG_LINE, "fa6s.arrows-up-down-left-right")
        api.register_component_icon(TYPE_DEBUG_TRIANGLE, "fa6s.draw-polygon")
        api.register_component_icon(TYPE_DEBUG_LOFT, "fa6s.plane")
        api.register_component_icon(TYPE_DEBUG_POINT, "mdi6.dots-hexagon")
        api.register_component_icon(TYPE_DEBUG_ARROW, "fa6s.location-arrow")

        # 3. Component Domain Models
        api.register_component_model(TYPE_DEBUG_BOX, BoxComponent)
        api.register_component_model(TYPE_DEBUG_CYLINDER, CylinderComponent)
        api.register_component_model(TYPE_DEBUG_RING, RingComponent)
        api.register_component_model(TYPE_DEBUG_PLANE, PlaneComponent)
        api.register_component_model(TYPE_DEBUG_LINE, LineComponent)
        api.register_component_model(TYPE_DEBUG_TRIANGLE, TriangleComponent)
        api.register_component_model(TYPE_DEBUG_LOFT, LoftComponent)
        api.register_component_model(TYPE_DEBUG_POINT, PointComponent)
        api.register_component_model(TYPE_DEBUG_ARROW, ArrowComponent)

    def _unregister_component_types(self, api: StudioAPI) -> None:
        """Unregister component editors, icons, and models."""
        types = (
            TYPE_DEBUG_BOX,
            TYPE_DEBUG_CYLINDER,
            TYPE_DEBUG_RING,
            TYPE_DEBUG_PLANE,
            TYPE_DEBUG_LINE,
            TYPE_DEBUG_TRIANGLE,
            TYPE_DEBUG_LOFT,
            TYPE_DEBUG_POINT,
            TYPE_DEBUG_ARROW,
        )
        for t in types:
            api.unregister_component_editor(t)
            api.unregister_component_icon(t)
            api.unregister_component_model(t)

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
            sync_debug_components_to_viewport(vp, project)

    def _get_viewport(self) -> ViewportProtocol | None:
        """Get the StudioViewport instance, showing the panel if necessary."""
        if self._api is None:
            return None
        vp = self._api.viewport
        if vp is None:
            self._api.show_panel("studio.viewer.opengl")
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

        tool_add = ToolContribution(
            title="Add Mock Analysis",
            callback=self._add_mock_analysis_config,
            group="Debug",
            icon="fa6s.plus",
        )
        api.register_tool(tool_add)
        self._tool_contributions.append(tool_add)

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
        if self._api is None or self._api.current_project is None:
            if self._api is not None:
                self._api.show_status("Open or create a project first.", "warning", 3000)
            return

        from setuav_studio.model.analysis_config import AnalysisConfig

        config = AnalysisConfig(
            solver_id=SOLVER_ID_MOCK_GENERATOR,
            name="Mock Analysis",
            parameters={
                "duration": 3.0,
                "rows": 50,
                "columns": 4,
            },
        )
        self._api.add_analysis_config(config)
        self._api.show_status("Added Mock Analysis configuration.", "success", 3000)
