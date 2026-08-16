from PySide6.QtCore import Qt

from setuav_studio.plugin_system import PanelContribution, StudioAPI
from setuav_studio.plugins.core.instance import InstanceEditor
from setuav_studio.plugins.core.properties import PropertiesPanel
from setuav_studio.plugins.core.project import ProjectExplorerPanel


class CorePlugin:
    id = "org.setuav.studio.core"

    def activate(self, api: StudioAPI) -> None:
        api.register_kind_editor(
            "instance",
            lambda instance: InstanceEditor(api, instance),
        )
        api.add_panel(
            PanelContribution(
                id="project.explorer",
                title="Project Explorer",
                factory=lambda: ProjectExplorerPanel(api),
                workspace_id=["studio.workspace.design", "studio.workspace.propulsion"],
                icon="project_explorer",
            )
        )
        api.add_panel(
            PanelContribution(
                id="studio.properties",
                title="Properties",
                factory=lambda: PropertiesPanel(api),
                area=Qt.DockWidgetArea.RightDockWidgetArea,
                workspace_id=["studio.workspace.design", "studio.workspace.propulsion"],
                icon="properties",
            )
        )
