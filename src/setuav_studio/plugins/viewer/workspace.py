import logging

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QToolButton, QVBoxLayout, QWidget

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.project import ProjectDocument
from setuav_studio.plugins.viewer.widget import (
    SOLID,
    SOLID_WIRE,
    WIREFRAME,
    OpenGLViewer,
)
from setuav_studio.plugins.viewer.mesh import (
    FACE_COLORED,
    FACE_MONOCHROME,
    FACE_TRANSPARENT,
)


logger = logging.getLogger(__name__)


class ViewerWorkspace(QWidget):
    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self._api = api
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        controls = QWidget(self)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(4, 3, 4, 3)
        controls_layout.setSpacing(4)
        controls_layout.addStretch()

        mode = QComboBox(controls)
        mode.addItem("Wireframe", WIREFRAME)
        mode.addItem("Solid", SOLID)
        mode.addItem("Solid + Wireframe", SOLID_WIRE)
        mode.setCurrentIndex(2)
        controls_layout.addWidget(mode)

        face_style = QComboBox(controls)
        face_style.addItem("Colored", FACE_COLORED)
        face_style.addItem("Monochrome", FACE_MONOCHROME)
        face_style.addItem("Transparent", FACE_TRANSPARENT)
        controls_layout.addWidget(face_style)

        fit_button = QToolButton(controls)
        fit_button.setText("Fit")
        controls_layout.addWidget(fit_button)
        layout.addWidget(controls)

        self.viewer = OpenGLViewer(self)
        layout.addWidget(self.viewer, 1)
        mode.currentIndexChanged.connect(
            lambda index: self.viewer.set_mode(str(mode.itemData(index)))
        )
        face_style.currentIndexChanged.connect(
            lambda index: self.viewer.set_face_style(str(face_style.itemData(index)))
        )
        fit_button.clicked.connect(self.viewer.fit_view)

        api.on_project_changed(self._on_project_changed)
        api.on_project_content_changed(self._on_project_content_changed)
        api.on_selection_changed(self._on_selection_changed)
        self.destroyed.connect(self._detach)

    def _on_project_changed(self, project: ProjectDocument) -> None:
        self._refresh(project, fit=True)

    def _on_project_content_changed(self, project: ProjectDocument) -> None:
        self._refresh(project, fit=False)

    def _on_selection_changed(self, selection: object | None) -> None:
        component_id = selection.get("id") if isinstance(selection, dict) else None
        self.viewer.set_selected_component(
            component_id if isinstance(component_id, str) else None
        )

    def _refresh(self, project: ProjectDocument, fit: bool) -> None:
        try:
            self.viewer.set_geometry(self._api.build_geometry_data(project), fit=fit)
        except (TypeError, ValueError):
            logger.exception("Could not build viewer geometry")

    def _detach(self, *_args: object) -> None:
        self._api.remove_project_listener(self._on_project_changed)
        self._api.remove_project_content_listener(self._on_project_content_changed)
        self._api.remove_selection_listener(self._on_selection_changed)
