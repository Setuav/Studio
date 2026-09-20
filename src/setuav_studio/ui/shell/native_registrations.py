from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt

from setuav_studio.api import (
    ComponentTreeNodeContribution,
    ComponentTypeContribution,
    PanelContribution,
)
from setuav_studio.ui.panels.project_explorer import ProjectExplorerPanel
from setuav_studio.ui.panels.properties import PropertiesPanel

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


def _transform_tree_nodes(
    component: dict[str, Any],
) -> tuple[ComponentTreeNodeContribution, ...]:
    component_id = str(component.get("id") or "")
    if not component_id:
        return ()
    transform_node_id = f"{component_id}:transform"
    envelope_node_id = f"{component_id}:envelope"
    nodes = [
        ComponentTreeNodeContribution(
            id=transform_node_id,
            title="Transform",
            selection={
                "id": transform_node_id,
                "name": "Transform",
                "kind": "transform",
                "component_id": component_id,
            },
            icon="transform",
            tooltip="Position and rotation relative to the parent frame",
        ),
    ]
    comp_type = str(component.get("type") or "").lower()
    has_explicit_envelope = bool(component.get("envelope"))
    is_non_geometric = any(
        k in comp_type
        for k in ("generic", "payload", "avionics", "battery", "equipment", "internal", "debug")
    )
    if (is_non_geometric or has_explicit_envelope) and comp_type != "org.setuav.core:point-mass":
        nodes.append(
            ComponentTreeNodeContribution(
                id=envelope_node_id,
                title="Envelope",
                selection={
                    "id": envelope_node_id,
                    "name": "Envelope",
                    "kind": "envelope",
                    "component_id": component_id,
                },
                icon="envelope",
                tooltip="Local dimensions, offset and occupied volume",
            )
        )
    return tuple(nodes)


def _mass_tree_nodes(
    component: dict[str, Any],
) -> tuple[ComponentTreeNodeContribution, ...]:
    component_id = str(component.get("id") or "")
    if not component_id:
        return ()
    node_id = f"{component_id}:mass-properties"
    return (
        ComponentTreeNodeContribution(
            id=node_id,
            title="Mass",
            selection={
                "id": node_id,
                "name": "Mass",
                "kind": "mass-properties",
                "component_id": component_id,
            },
            icon="mass",
            tooltip=f"Mass, local CG and inertia for {component.get('name') or component_id}",
        ),
    )


def _can_edit_project(api: StudioAPI) -> bool:
    project = api.current_project
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


def _on_run_analysis_triggered(api: StudioAPI) -> None:
    """Trigger execution of the currently active analysis configuration."""
    active_config = api.get_current_analysis_config()
    if active_config is None:
        all_configs = api.get_analysis_configs()
        if all_configs:
            active_config = next(iter(all_configs.values()))
            api.set_current_analysis_config(active_config.config_id)

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
        solver_config = active_config.to_solver_config()
        solver = solver_cls(solver_config)
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


def register_native_contributions(api: StudioAPI) -> None:
    """Register built-in native panels, tree providers, and kind editors into the StudioAPI."""
    from setuav_studio.api import ToolbarContribution
    from setuav_studio.ui.viewport import StudioViewport

    # 1. Native Panels
    api.add_panel(
        PanelContribution(
            id="core:project-explorer",
            title="Project Explorer",
            factory=lambda: ProjectExplorerPanel(api),
            area=Qt.DockWidgetArea.LeftDockWidgetArea,
            icon="fa6s.folder-tree",
        )
    )
    api.add_panel(
        PanelContribution(
            id="studio.viewer.opengl",
            title="3D Viewer",
            factory=lambda: StudioViewport(api=api),
            area=Qt.DockWidgetArea.RightDockWidgetArea,
            icon="viewer_3d",
        )
    )
    api.add_panel(
        PanelContribution(
            id="core:properties",
            title="Properties",
            factory=lambda: PropertiesPanel(api),
            area=Qt.DockWidgetArea.RightDockWidgetArea,
            icon="fa6s.sliders",
        )
    )
    from setuav_studio.ui.panels.results import ResultPanel

    api.add_panel(
        PanelContribution(
            id="core:result",
            title="Result",
            factory=lambda: ResultPanel(api),
            area=Qt.DockWidgetArea.RightDockWidgetArea,
            icon="fa6s.square-poll-vertical",
        )
    )

    # 2. Native Toolbar Contributions
    api.add_toolbar_item(
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
    api.add_toolbar_item(
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
    api.add_toolbar_item(
        ToolbarContribution(
            id="org.setuav.studio.toolbar.run_analysis",
            title="Run Analysis",
            callback=lambda: _on_run_analysis_triggered(api),
            icon="fa6s.play",
            group="analysis",
            order=10,
        )
    )

    # 3. Native Tree Providers
    api.register_component_tree_provider(
        "org.setuav.studio.core.transform",
        _transform_tree_nodes,
    )
    api.register_component_tree_provider(
        "org.setuav.studio.core.mass",
        _mass_tree_nodes,
    )

    # 4. Native Kind Editors
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
        ),
        ComponentTypeContribution(
            id="org.setuav.core:motor",
            name="Electric Motor",
            icon="component",
            category="Propulsion",
        ),
        ComponentTypeContribution(
            id="org.setuav.core:propeller",
            name="Propeller",
            icon="component",
            category="Propulsion",
        ),
        ComponentTypeContribution(
            id="org.setuav.core:rotor",
            name="Rotor",
            icon="component",
            category="Propulsion",
        ),
        ComponentTypeContribution(
            id="org.setuav.core:esc",
            name="ESC (Speed Controller)",
            icon="component",
            category="Propulsion",
        ),
        ComponentTypeContribution(
            id="org.setuav.core:battery",
            name="Battery",
            icon="component",
            category="Electrical",
        ),
        ComponentTypeContribution(
            id="org.setuav.core:electric-propulsion-system",
            name="Electric Propulsion System",
            icon="component_propulsion_system",
            category="Propulsion",
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
        if contrib.id not in getattr(api, "_component_types", {}):
            api.register_component_type(contrib)


def register_native_kind_editors(api: StudioAPI) -> None:
    """Register built-in fallback editors for standard component and document kinds."""
    from setuav_studio.ui.editor import (
        AnalysisConfigPropertyEditor,
        ConstraintPropertyEditor,
        EnvelopeEditor,
        MassPropertiesEditor,
        ParameterPropertyEditor,
        TransformEditor,
    )

    defaults = {
        "transform": lambda selection: TransformEditor(api, selection),
        "envelope": lambda selection: EnvelopeEditor(api, selection),
        "mass-properties": lambda selection: MassPropertiesEditor(api, selection),
        "parameter": lambda selection: ParameterPropertyEditor(api, selection),
        "constraint": lambda selection: ConstraintPropertyEditor(api, selection),
        "analysis_config": lambda selection: AnalysisConfigPropertyEditor(api, selection),
        "analysis_result": lambda selection: AnalysisConfigPropertyEditor(api, selection),
    }
    for kind, factory in defaults.items():
        if kind not in getattr(api, "_kind_editors", {}):
            api.register_kind_editor(kind, factory)
