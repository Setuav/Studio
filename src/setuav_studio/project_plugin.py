from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from setuav_studio.plugins import PanelContribution, StudioAPI
from setuav_studio.project import ProjectDocument


class ProjectExplorer(QTreeWidget):
    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self.setHeaderLabels(["Component", "Type"])
        api.on_project_changed(self.set_project)

    def set_project(self, project: ProjectDocument) -> None:
        self.clear()
        for component in project.data.get("components", []):
            name = str(component.get("name") or component.get("id") or "Unnamed")
            component_type = str(component.get("type") or component.get("kind") or "")
            self.addTopLevelItem(QTreeWidgetItem([name, component_type]))


class ProjectPlugin:
    id = "org.setuav.studio.project"

    def activate(self, api: StudioAPI) -> None:
        api.add_panel(
            PanelContribution(
                id="project.explorer",
                title="Project Explorer",
                factory=lambda: ProjectExplorer(api),
            )
        )
