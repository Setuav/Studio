from PySide6.QtCore import Qt

from setuav_studio.plugin_system import (
    PanelContribution,
    StudioAPI,
    ToolbarContribution,
)
from setuav_studio.plugins.core.instance import InstanceEditor
from setuav_studio.plugins.core.properties import PropertiesPanel
from setuav_studio.plugins.core.ui.project_explorer import ProjectExplorerPanel


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
        api.add_panel(
            PanelContribution(
                id="project.explorer",
                title="Project Explorer",
                factory=lambda: ProjectExplorerPanel(api),
                workspace_id=[
                    "studio.workspace.design",
                    "studio.workspace.propulsion",
                    "studio.workspace.aerodynamics",
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
                    "studio.workspace.propulsion",
                    "studio.workspace.aerodynamics",
                ],
                icon="properties",
            )
        )

    def deactivate(self, api: StudioAPI) -> None:
        for contribution in self._TOOLBAR_ITEMS:
            api.remove_toolbar_item(contribution.id)
        api.remove_kind_editor("instance")
        api.remove_panel("project.explorer")
        api.remove_panel("studio.properties")
