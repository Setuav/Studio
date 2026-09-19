from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt

from setuav_studio.ui.editor import (
    EnvelopeEditor,
    MassPropertiesEditor,
    TransformEditor,
)
from setuav_studio.ui.panels.project_explorer import ProjectExplorerPanel
from setuav_studio.ui.panels.properties import PropertiesPanel
from setuav_studio_sdk import (
    ComponentTreeNodeContribution,
    PanelContribution,
)

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
    if component.get("type") != "org.setuav.core:point-mass":
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
    from setuav_studio.ui.viewport import StudioViewport
    from setuav_studio_sdk import ToolbarContribution

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
    api.register_kind_editor(
        "transform",
        lambda selection: TransformEditor(api, selection),
    )
    api.register_kind_editor(
        "envelope",
        lambda selection: EnvelopeEditor(api, selection),
    )
    api.register_kind_editor(
        "mass-properties",
        lambda selection: MassPropertiesEditor(api, selection),
    )
