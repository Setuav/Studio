from PySide6.QtCore import Qt

from setuav_studio.plugin_system import PanelContribution, StudioAPI
from setuav_studio.plugins.core.properties import PropertiesPanel
from setuav_studio.plugins.core.project import ProjectExplorer


class CorePlugin:
    id = "org.setuav.studio.core"

    def activate(self, api: StudioAPI) -> None:
        api.add_panel(
            PanelContribution(
                id="project.explorer",
                title="Project Explorer",
                factory=lambda: ProjectExplorer(api),
            )
        )
        api.add_panel(
            PanelContribution(
                id="studio.properties",
                title="Properties",
                factory=lambda: PropertiesPanel(api),
                area=Qt.DockWidgetArea.RightDockWidgetArea,
            )
        )
