from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.project import ProjectDocument


class ProjectExplorerPanel(QWidget):
    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(ProjectExplorer(api))


class ProjectExplorer(QTableWidget):
    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(["Component", "Type"])
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(22)
        self.horizontalHeader().setFixedHeight(23)
        self.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.currentCellChanged.connect(self._publish_selection)
        self._api = api
        self._components: list[dict[str, object]] = []
        api.on_project_changed(self.set_project)
        api.on_project_content_changed(self.refresh_project)

    def set_project(self, project: ProjectDocument) -> None:
        components = project.data.get("components", [])
        self._components = [item for item in components if isinstance(item, dict)]
        self.setRowCount(len(self._components))
        for row, component in enumerate(self._components):
            name = str(component.get("name") or component.get("id") or "Unnamed")
            component_type = self._component_type_text(component, self._components)
            self.setItem(row, 0, QTableWidgetItem(name))
            self.setItem(row, 1, QTableWidgetItem(component_type))

    def refresh_project(self, project: ProjectDocument) -> None:
        components = project.data.get("components", [])
        current_components = [item for item in components if isinstance(item, dict)]
        if len(current_components) != len(self._components):
            self.set_project(project)
            return

        self._components = current_components
        for row, component in enumerate(self._components):
            name_item = self.item(row, 0)
            type_item = self.item(row, 1)
            if name_item is not None:
                name_item.setText(
                    str(component.get("name") or component.get("id") or "Unnamed")
                )
            if type_item is not None:
                type_item.setText(
                    self._component_type_text(component, self._components)
                )

    @staticmethod
    def _component_type_text(
        component: dict[str, object],
        components: list[dict[str, object]],
    ) -> str:
        if component.get("kind") != "instance":
            return str(component.get("type") or component.get("kind") or "")

        source_id = str(component.get("source") or "")
        source_name = source_id
        for candidate in components:
            if str(candidate.get("id") or "") == source_id:
                source_name = str(candidate.get("name") or source_id)
                break
        return f"Instance of {source_name}" if source_name else "Instance"

    def _publish_selection(
        self,
        row: int,
        _column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        component = None
        if 0 <= row < len(self._components):
            component = self._components[row]
        self._api.set_selection(component)
