from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt

from setuav_studio.ui.editors import (
    EnvelopeEditor,
    InstanceEditor,
    TransformEditor,
)
from setuav_studio.ui.parameters import ProjectParametersPanel
from setuav_studio.ui.project_explorer import ProjectExplorerPanel
from setuav_studio.ui.properties import PropertiesPanel
from setuav_studio_sdk import (
    ComponentTreeNodeContribution,
    PanelContribution,
)

if TYPE_CHECKING:
    from setuav_studio.plugin_system import StudioAPI


def _transform_tree_nodes(
    component: dict[str, Any],
) -> tuple[ComponentTreeNodeContribution, ...]:
    component_id = str(component.get("id") or "")
    if not component_id:
        return ()
    transform_node_id = f"{component_id}:transform"
    envelope_node_id = f"{component_id}:physical-envelope"
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
            icon="mdi6.axis-arrow",
            tooltip="Position and rotation relative to the parent frame",
        ),
    ]
    # A point mass has no physical volume; its only geometric property is
    # the transform origin. Do not expose a meaningless Envelope node.
    if component.get("type") != "org.setuav.core:point-mass":
        nodes.append(
            ComponentTreeNodeContribution(
                id=envelope_node_id,
                title="Envelope",
                selection={
                    "id": envelope_node_id,
                    "name": "Envelope",
                    "kind": "physical-envelope",
                    "component_id": component_id,
                },
                icon="fa6s.ruler-combined",
                tooltip="Local dimensions, offset and occupied volume",
            )
        )
    return tuple(nodes)


def register_native_contributions(api: StudioAPI) -> None:
    """Register built-in native panels, tree providers, and kind editors into the StudioAPI."""
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
            id="core:properties",
            title="Properties",
            factory=lambda: PropertiesPanel(api),
            area=Qt.DockWidgetArea.RightDockWidgetArea,
            icon="fa6s.sliders",
        )
    )
    api.add_panel(
        PanelContribution(
            id="core:parameters",
            title="Project Parameters",
            factory=lambda: ProjectParametersPanel(api),
            area=Qt.DockWidgetArea.BottomDockWidgetArea,
            icon="constant",
        )
    )

    # 2. Native Tree Providers
    api.register_component_tree_provider(
        "org.setuav.studio.core.transform",
        _transform_tree_nodes,
    )

    # 3. Native Kind Editors
    api.register_kind_editor(
        "instance",
        lambda instance: InstanceEditor(api, instance),
    )
    api.register_kind_editor(
        "transform",
        lambda selection: TransformEditor(api, selection),
    )
    api.register_kind_editor(
        "physical-envelope",
        lambda selection: EnvelopeEditor(api, selection),
    )
