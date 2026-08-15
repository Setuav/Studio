from PySide6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.project import ProjectDocument


class ProjectExplorer(QTreeWidget):
    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self.setHeaderLabels(["Component", "Type"])
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.currentItemChanged.connect(self._publish_selection)
        self._api = api
        self._components: list[dict[str, object]] = []
        api.on_project_changed(self.set_project)

    def set_project(self, project: ProjectDocument) -> None:
        self.clear()
        components = project.data.get("components", [])
        self._components = [item for item in components if isinstance(item, dict)]
        for index, component in enumerate(self._components):
            name = str(component.get("name") or component.get("id") or "Unnamed")
            component_type = str(component.get("type") or component.get("kind") or "")
            item = QTreeWidgetItem([name, component_type])
            item.setData(0, 256, index)
            self.addTopLevelItem(item)

    def _publish_selection(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        component = None
        if current is not None:
            index = current.data(0, 256)
            if isinstance(index, int) and 0 <= index < len(self._components):
                component = self._components[index]
        self._api.set_selection(component)
