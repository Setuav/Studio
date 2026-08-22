import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import get_icon
from setuav_studio.plugin_system import StudioAPI
from setuav_studio.project import ProjectDocument
from .viewport.palettes import (
    active_palette,
    palette_names,
    set_active_palette,
)
from .viewport.widget import OpenGLViewer
from setuav_studio.ui.theme import accent_color, rgba, tokens
from .viewport.mesh import (
    FACE_COLORED,
    FACE_MONOCHROME,
)


logger = logging.getLogger(__name__)

_HUD_STYLE = f"""
QWidget#viewerHUD {{
    background-color: {rgba(tokens()["window"], 0.88)};
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 6px;
}}
QWidget#viewerHUD QToolButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 0px;
    margin: 0px;
}}
QWidget#viewerHUD QToolButton:hover {{
    background-color: rgba(255, 255, 255, 0.12);
    border: 1px solid rgba(255, 255, 255, 0.18);
}}
QWidget#viewerHUD QToolButton:checked {{
    background-color: {rgba(accent_color(), 0.22)};
    border: 1px solid {accent_color()};
}}
QWidget#viewerHUD QToolButton:checked:hover {{
    background-color: {rgba(accent_color(), 0.32)};
}}
QWidget#viewerHUD QFrame#hudSep {{
    background-color: rgba(255, 255, 255, 0.14);
    max-width: 1px;
    margin: 3px 2px;
}}
"""


class ViewerWorkspace(QWidget):
    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self._api = api
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.viewer = OpenGLViewer(self)
        layout.addWidget(self.viewer, 1)

        # Floating HUD Capsule over the 3D Viewport
        self.hud = QWidget(self)
        self.hud.setObjectName("viewerHUD")
        self.hud.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hud.setStyleSheet(_HUD_STYLE)

        hud_layout = QHBoxLayout(self.hud)
        hud_layout.setContentsMargins(4, 3, 4, 3)
        hud_layout.setSpacing(3)

        # Display Toggles (Solid & Wireframe active/passive toggles)
        self.solid_button = QToolButton(self.hud)
        self.solid_button.setCheckable(True)
        self.solid_button.setChecked(True)
        self.solid_button.setIcon(get_icon("fa6s.cube"))
        self.solid_button.setToolTip("Toggle Solid Surface")
        self.solid_button.setFixedSize(24, 24)
        self.solid_button.setAutoRaise(True)
        self.solid_button.toggled.connect(self._on_display_toggled)
        hud_layout.addWidget(self.solid_button)

        self.wire_button = QToolButton(self.hud)
        self.wire_button.setCheckable(True)
        self.wire_button.setChecked(True)
        self.wire_button.setIcon(get_icon("mdi6.vector-square"))
        self.wire_button.setToolTip("Toggle Wireframe Mesh")
        self.wire_button.setFixedSize(24, 24)
        self.wire_button.setAutoRaise(True)
        self.wire_button.toggled.connect(self._on_display_toggled)
        hud_layout.addWidget(self.wire_button)

        sep1 = QFrame(self.hud)
        sep1.setObjectName("hudSep")
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setFrameShadow(QFrame.Shadow.Plain)
        hud_layout.addWidget(sep1)

        # Shading / Surface Style Group (Exclusive: Colored / Monochrome / Transparent)
        self.style_group = QButtonGroup(self)
        self.style_group.setExclusive(True)

        self.colored_button = QToolButton(self.hud)
        self.colored_button.setCheckable(True)
        self.colored_button.setChecked(True)
        self.colored_button.setIcon(get_icon("fa6s.palette"))
        self.colored_button.setToolTip("Component Colors")
        self.colored_button.setFixedSize(24, 24)
        self.colored_button.setAutoRaise(True)
        self.style_group.addButton(self.colored_button)
        hud_layout.addWidget(self.colored_button)

        self.mono_button = QToolButton(self.hud)
        self.mono_button.setCheckable(True)
        self.mono_button.setIcon(get_icon("fa6s.circle-half-stroke"))
        self.mono_button.setToolTip("Monochrome / Neutral")
        self.mono_button.setFixedSize(24, 24)
        self.mono_button.setAutoRaise(True)
        self.style_group.addButton(self.mono_button)
        hud_layout.addWidget(self.mono_button)

        sep2 = QFrame(self.hud)
        sep2.setObjectName("hudSep")
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setFrameShadow(QFrame.Shadow.Plain)
        hud_layout.addWidget(sep2)

        # Transparency Toggle (Independent)
        self.trans_button = QToolButton(self.hud)
        self.trans_button.setCheckable(True)
        self.trans_button.setChecked(False)
        self.trans_button.setIcon(get_icon("mdi6.opacity"))
        self.trans_button.setToolTip("Toggle Transparency (X-Ray)")
        self.trans_button.setFixedSize(24, 24)
        self.trans_button.setAutoRaise(True)
        self.trans_button.toggled.connect(self.viewer.set_transparent)
        hud_layout.addWidget(self.trans_button)

        self.grid_button = QToolButton(self.hud)
        self.grid_button.setCheckable(True)
        self.grid_button.setChecked(True)
        self.grid_button.setIcon(get_icon("mdi6.grid"))
        self.grid_button.setToolTip("Toggle Reference Grid")
        self.grid_button.setFixedSize(24, 24)
        self.grid_button.setAutoRaise(True)
        self.grid_button.toggled.connect(self.viewer.set_show_grid)
        hud_layout.addWidget(self.grid_button)

        sep3 = QFrame(self.hud)
        sep3.setObjectName("hudSep")
        sep3.setFrameShape(QFrame.Shape.VLine)
        sep3.setFrameShadow(QFrame.Shadow.Plain)
        hud_layout.addWidget(sep3)

        # Color Palette Selector
        self.palette_button = QToolButton(self.hud)
        self.palette_button.setIcon(get_icon("fa6s.brush"))
        self.palette_button.setToolTip("Color Palette")
        self.palette_button.setFixedSize(24, 24)
        self.palette_button.setAutoRaise(True)
        self.palette_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self._palette_menu = QMenu(self.palette_button)
        self.palette_button.setMenu(self._palette_menu)
        self._build_palette_menu()
        hud_layout.addWidget(self.palette_button)

        sep4 = QFrame(self.hud)
        sep4.setObjectName("hudSep")
        sep4.setFrameShape(QFrame.Shape.VLine)
        sep4.setFrameShadow(QFrame.Shadow.Plain)
        hud_layout.addWidget(sep4)

        # Standard View Presets
        view_buttons = (
            ("fa6s.arrow-up", "Top View", 0.0, 90.0),
            ("fa6s.arrow-down", "Bottom View", 0.0, -90.0),
            ("fa6s.arrow-right", "Front View", 270.0, 0.0),
            ("fa6s.arrow-left", "Side View", 180.0, 0.0),
            ("fa6s.cubes", "Isometric View", 210.0, 20.0),
        )
        for icon, tooltip, azimuth, elevation in view_buttons:
            button = QToolButton(self.hud)
            button.setIcon(get_icon(icon))
            button.setToolTip(tooltip)
            button.setFixedSize(24, 24)
            button.setAutoRaise(True)
            button.clicked.connect(
                lambda _checked=False, az=azimuth, el=elevation: self.viewer.set_view(
                    az, el
                )
            )
            hud_layout.addWidget(button)

        # Camera Fit Button
        fit_button = QToolButton(self.hud)
        fit_button.setIcon(get_icon("fit"))
        fit_button.setToolTip("Fit View (Reset Camera)")
        fit_button.setFixedSize(24, 24)
        fit_button.setAutoRaise(True)
        hud_layout.addWidget(fit_button)

        self.colored_button.clicked.connect(
            lambda: self.viewer.set_face_style(FACE_COLORED)
        )
        self.mono_button.clicked.connect(
            lambda: self.viewer.set_face_style(FACE_MONOCHROME)
        )
        fit_button.clicked.connect(self.viewer.fit_view)

        api.on_project_changed(self._on_project_changed)
        api.on_project_content_changed(self._on_project_content_changed)
        api.on_selection_changed(self._on_selection_changed)
        api.on_section_selection_changed(self._on_section_selection_changed)
        self.viewer.componentPicked.connect(self._on_component_picked)
        self.destroyed.connect(self._detach)

        self.hud.adjustSize()
        self._reposition_hud()

    def _build_palette_menu(self) -> None:
        self._palette_menu.clear()
        group = QActionGroup(self)
        group.setExclusive(True)
        for name in palette_names():
            action = QAction(name.capitalize(), self)
            action.setCheckable(True)
            action.setChecked(name == active_palette())
            action.triggered.connect(
                lambda _checked=False, palette_name=name: self._on_palette_selected(
                    palette_name
                )
            )
            group.addAction(action)
            self._palette_menu.addAction(action)

    def _on_palette_selected(self, name: str) -> None:
        try:
            set_active_palette(name)
        except ValueError:
            return
        self._build_palette_menu()
        project = self._api.current_project
        if project is not None:
            self._refresh(project, fit=False)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._reposition_hud()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._reposition_hud()

    def _reposition_hud(self) -> None:
        margin = 12
        x = self.width() - self.hud.width() - margin
        y = margin
        self.hud.move(max(margin, x), y)
        self.hud.raise_()

    def _on_display_toggled(self) -> None:
        if not self.solid_button.isChecked() and not self.wire_button.isChecked():
            sender = self.sender()
            if sender == self.solid_button:
                self.wire_button.setChecked(True)
            else:
                self.solid_button.setChecked(True)
        self.viewer.set_show_solid(self.solid_button.isChecked())
        self.viewer.set_show_wireframe(self.wire_button.isChecked())

    def _on_project_changed(self, project: ProjectDocument) -> None:
        self._refresh(project, fit=True)

    def _on_project_content_changed(self, project: ProjectDocument) -> None:
        self._refresh(project, fit=False)

    def _on_selection_changed(self, selection: object | None) -> None:
        component_id = selection.get("id") if isinstance(selection, dict) else None
        self.viewer.set_selected_component(
            component_id if isinstance(component_id, str) else None
        )
        current = self._api.current_section_selection
        if current is not None and current[0] != component_id:
            self._api.set_section_selection(None)

    def _on_section_selection_changed(
        self,
        selection: tuple[str, int, int] | None,
    ) -> None:
        if selection is None:
            self.viewer.set_selected_section(None, None, None)
            return
        component_id, segment_index, section_index = selection
        self.viewer.set_selected_section(
            component_id,
            segment_index,
            section_index,
        )

    def _on_component_picked(self, component_id: object | None) -> None:
        if not isinstance(component_id, str):
            self._api.set_selection(None)
            return
        project = self._api.current_project
        if project is None:
            return
        components = project.data.get("components", [])
        raw_components = [c for c in components if isinstance(c, dict)]

        # 1. Direct match with component ID
        for component in raw_components:
            if str(component.get("id") or "") == component_id:
                self._api.set_selection(component)
                return

        # 2. Match control surface sub-tag or child component (e.g. "main-wing:aileron", "main-wing:mirror:aileron")
        parts = component_id.split(":")
        sub_tag = parts[-1]
        for component in raw_components:
            cid = str(component.get("id") or "")
            params = component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
            geom = params.get("geometry") if isinstance(params.get("geometry"), dict) else {}
            tag = str(geom.get("tag") or component.get("name") or cid)
            if cid == sub_tag or tag == sub_tag:
                self._api.set_selection(component)
                return

        # 3. Match base component if mirrored or sub-tagged (e.g. "main-wing:mirror" -> "main-wing")
        base_id = parts[0]
        for component in raw_components:
            if str(component.get("id") or "") == base_id:
                self._api.set_selection(component)
                return

    def _refresh(self, project: ProjectDocument, fit: bool) -> None:
        try:
            self.viewer.set_geometry(self._api.build_geometry_data(project), fit=fit)
        except (TypeError, ValueError):
            logger.exception("Could not build viewer geometry")

    def _detach(self, *_args: object) -> None:
        self._api.remove_project_listener(self._on_project_changed)
        self._api.remove_project_content_listener(self._on_project_content_changed)
        self._api.remove_selection_listener(self._on_selection_changed)
        self._api.remove_section_selection_listener(self._on_section_selection_changed)
