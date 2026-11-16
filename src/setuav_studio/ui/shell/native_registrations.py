from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt

from setuav_studio.api import (
    ComponentTypeContribution,
    PanelContribution,
)
from setuav_studio.ui.editor.component import BaseComponentEditor
from setuav_studio.ui.panels.project_explorer import ProjectExplorerPanel
from setuav_studio.ui.panels.properties import PropertiesPanel

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


def _can_edit_project(api: StudioAPI) -> bool:
    project = api.project
    return project is not None and not project.read_only


def _on_add_constant_triggered(api: StudioAPI) -> None:
    from setuav_studio.ui.panels.project_explorer.dialog_actions import (
        add_parameter_action,
    )

    add_parameter_action(api, is_constant=True)


def _on_add_constraint_triggered(api: StudioAPI) -> None:
    from setuav_studio.ui.panels.project_explorer.dialog_actions import (
        add_constraint_action,
    )

    add_constraint_action(api)


def _can_open_expression_assistant(api: StudioAPI) -> bool:
    if not _can_edit_project(api):
        return False
    from setuav_studio.ui.widget.table import ExpressionFocusTracker

    return ExpressionFocusTracker.has_active_editor()


def _on_open_expression_assistant(api: StudioAPI) -> None:
    from setuav_studio.ui.widget.table import ExpressionFocusTracker

    editor = ExpressionFocusTracker.get_active_editor()
    if editor is not None:
        editor.open_assistant()
    else:
        from PySide6.QtWidgets import QApplication

        from setuav_studio.ui.dialog.expression_dialog import AdvancedExpressionDialog

        dlg = AdvancedExpressionDialog(
            api=api,
            initial_expression="",
            title="Formula Assistant",
            is_boolean_constraint=False,
            parent=QApplication.activeWindow(),
        )
        dlg.exec()


def _on_run_analysis_triggered(api: StudioAPI) -> None:
    """Trigger execution of the currently active analysis configuration."""
    active_config = api.get_current_solver_config()
    if active_config is None:
        all_configs = api.get_solver_configs()
        if all_configs:
            active_config = next(iter(all_configs.values()))
            api.set_current_solver_config(active_config.config_id)

    if active_config is None:
        api.show_status("No analysis configuration available to run.", "warning")
        return

    solver_cls = api.solvers.get_solver_class(active_config.solver_id)
    if solver_cls is None:
        api.show_status(
            f"No registered solver found for '{active_config.solver_id}'.",
            "error",
        )
        return

    try:
        solver = solver_cls(active_config)
        api.show_status(f"Starting analysis '{active_config.name}'...", "info")
        api.run_solver(
            solver,
            on_complete=lambda res: api.show_status(
                f"Analysis '{active_config.name}' completed ({res.execution_time_ms:.1f} ms).",
                "success",
            ),
            on_error=lambda err: api.show_status(
                f"Analysis '{active_config.name}' failed: {err}",
                "error",
            ),
        )
    except Exception as exc:
        api.show_status(f"Failed to launch analysis: {exc}", "error")


POINT_MASS_TYPE = "org.setuav.core:point-mass"


def _on_add_point_mass_triggered(api: StudioAPI) -> None:
    """Add a point mass at the vehicle origin and select it."""
    project = api.project
    if project is None or project.read_only:
        return
    components = project.data["components"]
    ids = {str(c.get("id") or "") for c in components if isinstance(c, dict)}
    names = {str(c.get("name") or "") for c in components if isinstance(c, dict)}
    component_id, name = "point-mass", "Point Mass"
    suffix = 2
    while component_id in ids or name in names:
        component_id, name = f"point-mass-{suffix}", f"Point Mass {suffix}"
        suffix += 1
    component = {
        "kind": "component",
        "id": component_id,
        "name": name,
        "type": POINT_MASS_TYPE,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "mass": 50.0,
    }
    api.edit_project(f"Add {name}", lambda: project.data["components"].append(component))
    api.set_selection(component)


def _on_toggle_aircraft_cg(api: StudioAPI) -> None:
    """Toggle visibility of the aircraft aggregate Center of Gravity marker in the Viewport."""
    viewport = api.viewport
    if viewport is not None:
        current = bool(viewport.is_show_aircraft_cg())
        viewport.set_show_aircraft_cg(not current)
        state_label = "enabled" if not current else "disabled"
        api.show_status(f"Aircraft CG visualization {state_label}.", "info", 2000)
    else:
        api.show_status("3D Viewport is not ready.", "info", 2000)


def register_native_contributions(api: StudioAPI) -> None:
    """Register built-in native panels, tree providers, and kind editors into the StudioAPI."""
    from setuav_studio.api import ToolbarContribution
    from setuav_studio.ui.viewport import StudioViewport

    # 1. Native Panels
    api.register_panel(
        PanelContribution(
            id="studio:project-explorer",
            title="Project Explorer",
            factory=lambda: ProjectExplorerPanel(api),
            area=Qt.DockWidgetArea.LeftDockWidgetArea,
            icon="fa6s.folder-tree",
        )
    )
    api.register_panel(
        PanelContribution(
            id="studio:viewer-3d",
            title="3D Viewer",
            factory=lambda: StudioViewport(api=api),
            area=Qt.DockWidgetArea.RightDockWidgetArea,
            icon="viewer_3d",
        )
    )
    api.register_panel(
        PanelContribution(
            id="studio:properties",
            title="Properties",
            factory=lambda: PropertiesPanel(api),
            area=Qt.DockWidgetArea.RightDockWidgetArea,
            icon="fa6s.sliders",
        )
    )
    from setuav_studio.ui.panels.results import ResultPanel

    api.register_panel(
        PanelContribution(
            id="studio:result",
            title="Result",
            factory=lambda: ResultPanel(api),
            area=Qt.DockWidgetArea.RightDockWidgetArea,
            icon="fa6s.square-poll-vertical",
        )
    )

    # 2. Native Toolbar Contributions
    api.register_toolbar_item(
        ToolbarContribution(
            id="org.setuav.studio.toolbar.add_constant",
            title="Add Constant",
            callback=lambda: _on_add_constant_triggered(api),
            icon="constant",
            enabled_when=lambda: _can_edit_project(api),
            group="parameters",
            order=10,
        )
    )
    api.register_toolbar_item(
        ToolbarContribution(
            id="org.setuav.studio.toolbar.expression_assistant",
            title="Formula Assistant",
            callback=lambda: _on_open_expression_assistant(api),
            icon="formula",
            enabled_when=lambda: _can_open_expression_assistant(api),
            group="parameters",
            order=15,
        )
    )
    api.register_toolbar_item(
        ToolbarContribution(
            id="org.setuav.studio.toolbar.add_constraint",
            title="Add Constraint",
            callback=lambda: _on_add_constraint_triggered(api),
            icon="constraint",
            enabled_when=lambda: _can_edit_project(api),
            group="parameters",
            order=20,
        )
    )
    api.register_toolbar_item(
        ToolbarContribution(
            id="org.setuav.studio.toolbar.add_point_mass",
            title="Add Point Mass",
            callback=lambda: _on_add_point_mass_triggered(api),
            icon="add_point_mass",
            enabled_when=lambda: _can_edit_project(api),
            group="mass",
            order=30,
        )
    )
    api.register_toolbar_item(
        ToolbarContribution(
            id="org.setuav.studio.toolbar.run_analysis",
            title="Run Analysis",
            callback=lambda: _on_run_analysis_triggered(api),
            icon="fa6s.play",
            group="analysis",
            order=10,
        )
    )
    api.register_toolbar_item(
        ToolbarContribution(
            id="org.setuav.studio.toolbar.toggle_aircraft_cg",
            title="Toggle Aircraft CG",
            callback=lambda: _on_toggle_aircraft_cg(api),
            icon="point_mass",
            checkable=True,
            checked_when=lambda: bool(
                api.viewport is not None and api.viewport.is_show_aircraft_cg()
            ),
            group="view",
            order=50,
        )
    )

    # 3. Native Kind Editors
    register_native_kind_editors(api)

    # 5. Native Component Types
    register_native_component_types(api)


def register_native_component_types(api: StudioAPI) -> None:
    """Register built-in component types, labels and icons."""
    native_types = [
        ComponentTypeContribution(
            id="org.setuav.core:fuselage",
            name="Fuselage",
            icon="geometry_add_fuselage",
            category="Aerodynamics",
        ),
        ComponentTypeContribution(
            id="org.setuav.core:lifting-surface",
            name="Lifting Surface",
            icon="geometry_add_lifting_surface",
            category="Aerodynamics",
        ),
        ComponentTypeContribution(
            id="org.setuav.core:control-surface",
            name="Control Surface",
            icon="geometry_add_control_surface",
            category="Aerodynamics",
            subpart=True,
        ),
        ComponentTypeContribution(
            id=POINT_MASS_TYPE,
            name="Point Mass",
            icon="component",
            editor=lambda component: BaseComponentEditor(api, component),
            category="Structure",
        ),
        ComponentTypeContribution(
            id="org.setuav.core:propulsor",
            name="Propulsor",
            icon="component",
            category="Propulsion",
        ),
        ComponentTypeContribution(
            id="org.setuav.core:battery",
            name="Battery",
            icon="component",
            category="Electrical",
        ),
        ComponentTypeContribution(id="org.setuav.debug:box", name="Box", category="Debug"),
        ComponentTypeContribution(
            id="org.setuav.debug:cylinder", name="Cylinder", category="Debug"
        ),
        ComponentTypeContribution(id="org.setuav.debug:ring", name="Ring", category="Debug"),
        ComponentTypeContribution(id="org.setuav.debug:plane", name="Plane", category="Debug"),
        ComponentTypeContribution(id="org.setuav.debug:line", name="Line", category="Debug"),
        ComponentTypeContribution(
            id="org.setuav.debug:triangle", name="Triangle", category="Debug"
        ),
        ComponentTypeContribution(id="org.setuav.debug:loft", name="Loft", category="Debug"),
        ComponentTypeContribution(id="org.setuav.debug:point", name="Point", category="Debug"),
        ComponentTypeContribution(id="org.setuav.debug:arrow", name="Arrow", category="Debug"),
    ]
    for contrib in native_types:
        if contrib.id not in api._component_types:
            api.register_component_type(contrib)


def register_native_kind_editors(api: StudioAPI) -> None:
    """Register built-in fallback editors for standard component and document kinds."""
    from setuav_studio.ui.editor import (
        AnalysisPlotPropertyEditor,
        AnalysisTablePropertyEditor,
        ConstraintPropertyEditor,
        ParameterPropertyEditor,
        SolverConfigPropertyEditor,
        VehicleSummaryEditor,
    )

    defaults = {
        "vehicle": lambda _selection: VehicleSummaryEditor(api),
        "parameter": lambda selection: ParameterPropertyEditor(api, selection),
        "constraint": lambda selection: ConstraintPropertyEditor(api, selection),
        "analysis_config": lambda selection: SolverConfigPropertyEditor(api, selection),
        "analysis_plot": lambda selection: AnalysisPlotPropertyEditor(api, selection),
        "analysis_table": lambda selection: AnalysisTablePropertyEditor(api, selection),
    }
    for kind, factory in defaults.items():
        if kind not in api._kind_editors:
            api.register_kind_editor(kind, factory)
