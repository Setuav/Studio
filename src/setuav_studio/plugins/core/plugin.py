from PySide6.QtCore import Qt

from setuav_studio.plugins.core.envelope import EnvelopeEditor
from setuav_studio.plugins.core.instance import InstanceEditor
from setuav_studio.plugins.core.properties import PropertiesPanel
from setuav_studio.plugins.core.transform import TransformEditor
from setuav_studio.plugins.core.ui.project_explorer import ProjectExplorerPanel
from setuav_studio_sdk import (
    ComponentTreeNodeContribution,
    PanelContribution,
    StudioAPI,
    ToolbarContribution,
)


class CorePlugin:
    id = "org.setuav.studio.core"

    _TOOLBAR_ITEMS = (
        ToolbarContribution(
            id="core.open-project-file",
            title="Open Project File…",
            command="core.project.open-file",
            icon="file_open",
            group="project",
            order=10,
        ),
        ToolbarContribution(
            id="core.open-project-folder",
            title="Open Project Folder…",
            command="core.project.open-folder",
            icon="folder_open",
            group="project",
            order=20,
        ),
        ToolbarContribution(
            id="core.save-project",
            title="Save Project",
            command="core.project.save",
            icon="save",
            group="project",
            order=30,
        ),
        ToolbarContribution(
            id="core.save-project-as",
            title="Save Project As…",
            command="core.project.save-as",
            icon="save_as",
            group="project",
            order=40,
        ),
        ToolbarContribution(
            id="core.undo",
            title="Undo",
            command="core.edit.undo",
            icon="undo",
            group="edit",
            order=50,
        ),
        ToolbarContribution(
            id="core.redo",
            title="Redo",
            command="core.edit.redo",
            icon="redo",
            group="edit",
            order=60,
        ),
    )

    def activate(self, api: StudioAPI) -> None:
        for contribution in self._TOOLBAR_ITEMS:
            api.add_toolbar_item(contribution)

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
        api.register_component_tree_provider(
            "org.setuav.studio.core.transform",
            self._transform_tree_nodes,
        )
        api.add_panel(
            PanelContribution(
                id="project.explorer",
                title="Project Explorer",
                factory=lambda: ProjectExplorerPanel(api),
                workspace_id=[
                    "studio.workspace.design",
                    "studio.workspace.weight_balance",
                    "studio.workspace.propulsion",
                    "studio.workspace.aerodynamics",
                    "studio.workspace.flight_performance",
                ],
                icon="project_explorer",
            )
        )
        api.add_panel(
            PanelContribution(
                id="studio.properties",
                title="Properties",
                factory=lambda: PropertiesPanel(api),
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                workspace_id=[
                    "studio.workspace.design",
                    "studio.workspace.weight_balance",
                    "studio.workspace.propulsion",
                    "studio.workspace.aerodynamics",
                    "studio.workspace.flight_performance",
                ],
                icon="properties",
            )
        )

    def deactivate(self, api: StudioAPI) -> None:
        for contribution in self._TOOLBAR_ITEMS:
            api.remove_toolbar_item(contribution.id)
        api.remove_kind_editor("instance")
        api.remove_kind_editor("transform")
        api.remove_kind_editor("physical-envelope")
        api.remove_component_tree_provider("org.setuav.studio.core.transform")
        api.remove_panel("project.explorer")
        api.remove_panel("studio.properties")

    @staticmethod
    def _transform_tree_nodes(
        component: dict,
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
        # the transform origin.  Do not expose a meaningless Envelope node.
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
