import logging

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QMenu,
    QToolButton,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.project import ProjectDocument
from setuav_studio.ui.icons import get_icon

from .settings import (
    _VIEWER_GRID_KEY,
    _VIEWER_PALETTE_KEY,
    _VIEWER_PROJECTION_KEY,
    _VIEWER_SOLID_KEY,
    _VIEWER_WIRE_KEY,
    viewer_setting,
)
from .viewport.mesh import (
    FACE_COLORED,
    FACE_MONOCHROME,
)
from .viewport.palettes import (
    active_palette,
    palette_names,
    set_active_palette,
)
from .viewport.widget import OpenGLViewer

logger = logging.getLogger(__name__)


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


class ViewerWorkspace(QWidget):
    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self._api = api
        self._api.subscribe(
            "geometry.viewer.settings.changed",
            self._on_viewer_settings_changed,
        )
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.viewer = OpenGLViewer(self)
        self._load_viewer_defaults()
        layout.setRowStretch(0, 1)
        layout.setRowMinimumHeight(1, 12)
        layout.addWidget(self.viewer, 0, 0, 2, 1)

        # Floating HUD Capsule over the 3D Viewport
        self.hud = QFrame(self)
        self.hud.setObjectName("viewerHUD")
        self.hud.setFrameShape(QFrame.Shape.StyledPanel)
        self.hud.setFrameShadow(QFrame.Shadow.Raised)
        self.hud.setAutoFillBackground(True)

        hud_layout = QHBoxLayout(self.hud)
        hud_layout.setContentsMargins(4, 3, 4, 3)
        hud_layout.setSpacing(3)

        # Display Toggles (Solid & Wireframe active/passive toggles)
        self.solid_button = QToolButton(self.hud)
        self.solid_button.setCheckable(True)
        self.solid_button.setChecked(self._default_show_solid)
        self.solid_button.setIcon(get_icon("view_solid"))
        self.solid_button.setToolTip("Toggle Solid Surface")
        self.solid_button.setFixedSize(24, 24)
        self.solid_button.setAutoRaise(True)
        self.solid_button.toggled.connect(self._on_display_toggled)
        hud_layout.addWidget(self.solid_button)

        self.wire_button = QToolButton(self.hud)
        self.wire_button.setCheckable(True)
        self.wire_button.setChecked(self._default_show_wire)
        self.wire_button.setIcon(get_icon("view_wireframe"))
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
        self.colored_button.setIcon(get_icon("view_colored"))
        self.colored_button.setToolTip("Component Colors")
        self.colored_button.setFixedSize(24, 24)
        self.colored_button.setAutoRaise(True)
        self.style_group.addButton(self.colored_button)
        hud_layout.addWidget(self.colored_button)

        self.mono_button = QToolButton(self.hud)
        self.mono_button.setCheckable(True)
        self.mono_button.setIcon(get_icon("view_monochrome"))
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
        self.trans_button.setIcon(get_icon("view_transparent"))
        self.trans_button.setToolTip("Toggle Transparency (X-Ray)")
        self.trans_button.setFixedSize(24, 24)
        self.trans_button.setAutoRaise(True)
        self.trans_button.toggled.connect(self.viewer.set_transparent)
        hud_layout.addWidget(self.trans_button)

        self.grid_button = QToolButton(self.hud)
        self.grid_button.setCheckable(True)
        self.grid_button.setChecked(self._default_show_grid)
        self.grid_button.setIcon(get_icon("view_grid"))
        self.grid_button.setToolTip("Toggle Reference Grid")
        self.grid_button.setFixedSize(24, 24)
        self.grid_button.setAutoRaise(True)
        self.grid_button.toggled.connect(self._on_grid_toggled)
        hud_layout.addWidget(self.grid_button)

        self.projection_button = QToolButton(self.hud)
        self.projection_button.setCheckable(True)
        self.projection_button.setChecked(self._default_orthographic)
        self.projection_button.setIcon(get_icon("fa6s.ruler-combined"))
        self.projection_button.setFixedSize(24, 24)
        self.projection_button.setAutoRaise(True)
        self.projection_button.toggled.connect(self._on_projection_toggled)
        hud_layout.addWidget(self.projection_button)
        self._update_projection_tooltip()

        sep3 = QFrame(self.hud)
        sep3.setObjectName("hudSep")
        sep3.setFrameShape(QFrame.Shape.VLine)
        sep3.setFrameShadow(QFrame.Shadow.Plain)
        hud_layout.addWidget(sep3)

        # Color Palette Selector
        self.palette_button = QToolButton(self.hud)
        self.palette_button.setIcon(get_icon("view_palette"))
        self.palette_button.setToolTip("Color Palette")
        self.palette_button.setFixedSize(24, 24)
        self.palette_button.setAutoRaise(True)
        self.palette_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
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
        self._cam_buttons: list[tuple[QToolButton, str]] = []
        view_buttons = (
            ("camera_top", "Top View", 0.0, 90.0),
            ("camera_bottom", "Bottom View", 0.0, -90.0),
            ("camera_front", "Front View", 270.0, 0.0),
            ("camera_side", "Side View", 180.0, 0.0),
            ("camera_iso", "Isometric View", 210.0, 20.0),
        )
        for icon, tooltip, azimuth, elevation in view_buttons:
            button = QToolButton(self.hud)
            button.setIcon(get_icon(icon))
            button.setToolTip(tooltip)
            button.setFixedSize(24, 24)
            button.setAutoRaise(True)
            button.clicked.connect(
                lambda _checked=False, az=azimuth, el=elevation: self.viewer.set_view(az, el)
            )
            self._cam_buttons.append((button, icon))
            hud_layout.addWidget(button)

        # Camera Fit Button
        self.fit_button = QToolButton(self.hud)
        self.fit_button.setIcon(get_icon("view_fit"))
        self.fit_button.setToolTip("Fit Model in View (F)")
        self.fit_button.setFixedSize(24, 24)
        self.fit_button.setAutoRaise(True)
        self.fit_button.clicked.connect(self.viewer.fit_view)
        hud_layout.addWidget(self.fit_button)

        self.colored_button.clicked.connect(lambda: self.viewer.set_face_style(FACE_COLORED))
        self.mono_button.clicked.connect(lambda: self.viewer.set_face_style(FACE_MONOCHROME))

        api.on_project_changed(self._on_project_changed)
        api.on_project_content_changed(self._on_project_content_changed)
        api.on_selection_changed(self._on_selection_changed)
        api.on_section_selection_changed(self._on_section_selection_changed)
        self.viewer.componentPicked.connect(self._on_component_picked)
        self.destroyed.connect(self._detach)

        self.hud.adjustSize()
        layout.addWidget(
            self.hud,
            0,
            0,
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        )
        self.hud.raise_()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # QOpenGLWidget creates its native surface lazily. Raise the overlay
        # after that show cycle as well, otherwise the surface may cover it on
        # some window managers/drivers.
        QTimer.singleShot(0, self.hud.raise_)

    def update_theme_style(self) -> None:
        self.hud.setPalette(self.palette())
        self.solid_button.setIcon(get_icon("view_solid"))
        self.wire_button.setIcon(get_icon("view_wireframe"))
        self.colored_button.setIcon(get_icon("view_colored"))
        self.mono_button.setIcon(get_icon("view_monochrome"))
        self.trans_button.setIcon(get_icon("view_transparent"))
        self.grid_button.setIcon(get_icon("view_grid"))
        self.projection_button.setIcon(get_icon("fa6s.ruler-combined"))
        self._update_projection_tooltip()
        self.palette_button.setIcon(get_icon("view_palette"))
        for btn, icon_name in self._cam_buttons:
            btn.setIcon(get_icon(icon_name))
        self.fit_button.setIcon(get_icon("view_fit"))
        self.viewer.update_theme_style()

    def _build_palette_menu(self) -> None:
        self._palette_menu.clear()
        group = QActionGroup(self)
        group.setExclusive(True)
        for name in palette_names():
            action = QAction(name.capitalize(), self)
            action.setCheckable(True)
            action.setChecked(name == active_palette())
            action.triggered.connect(
                lambda _checked=False, palette_name=name: self._on_palette_selected(palette_name)
            )
            group.addAction(action)
            self._palette_menu.addAction(action)

    def _on_palette_selected(self, name: str) -> None:
        try:
            set_active_palette(name)
        except ValueError:
            return
        QSettings().setValue(_VIEWER_PALETTE_KEY, name)
        self._build_palette_menu()
        project = self._api.current_project
        if project is not None:
            self._refresh(project, fit=False)

    def _on_display_toggled(self) -> None:
        if not self.solid_button.isChecked() and not self.wire_button.isChecked():
            sender = self.sender()
            if sender == self.solid_button:
                self.wire_button.setChecked(True)
            else:
                self.solid_button.setChecked(True)
        self.viewer.set_show_solid(self.solid_button.isChecked())
        self.viewer.set_show_wireframe(self.wire_button.isChecked())
        settings = QSettings()
        settings.setValue(_VIEWER_SOLID_KEY, self.solid_button.isChecked())
        settings.setValue(_VIEWER_WIRE_KEY, self.wire_button.isChecked())

    def _on_grid_toggled(self, checked: bool) -> None:
        self.viewer.set_show_grid(checked)
        QSettings().setValue(_VIEWER_GRID_KEY, checked)

    def _on_projection_toggled(self, checked: bool) -> None:
        self.viewer.set_orthographic(checked)
        QSettings().setValue(
            _VIEWER_PROJECTION_KEY,
            "orthographic" if checked else "perspective",
        )
        self._update_projection_tooltip()

    def _update_projection_tooltip(self) -> None:
        mode = "Orthographic" if self.projection_button.isChecked() else "Perspective"
        next_mode = "Perspective" if self.projection_button.isChecked() else "Orthographic"
        self.projection_button.setToolTip(f"Projection: {mode} (click for {next_mode})")

    def _load_viewer_defaults(self) -> None:
        projection = str(viewer_setting(_VIEWER_PROJECTION_KEY, "orthographic")).lower()
        self._default_orthographic = projection != "perspective"

        palette = str(viewer_setting(_VIEWER_PALETTE_KEY, active_palette())).lower()
        try:
            set_active_palette(palette)
        except ValueError:
            pass

        self._default_show_grid = _as_bool(
            viewer_setting(_VIEWER_GRID_KEY, True),
            True,
        )
        self._default_show_solid = _as_bool(
            viewer_setting(_VIEWER_SOLID_KEY, True),
            True,
        )
        self._default_show_wire = _as_bool(
            viewer_setting(_VIEWER_WIRE_KEY, True),
            True,
        )
        self.viewer.set_orthographic(self._default_orthographic)

    def _on_viewer_settings_changed(self, _payload: object = None) -> None:
        self._load_viewer_defaults()
        for button, checked in (
            (self.solid_button, self._default_show_solid),
            (self.wire_button, self._default_show_wire),
            (self.grid_button, self._default_show_grid),
            (self.projection_button, self._default_orthographic),
        ):
            button.blockSignals(True)
            button.setChecked(checked)
            button.blockSignals(False)
        self.viewer.set_show_solid(self._default_show_solid)
        self.viewer.set_show_wireframe(self._default_show_wire)
        self.viewer.set_show_grid(self._default_show_grid)
        self._build_palette_menu()
        self._update_projection_tooltip()
        project = self._api.current_project
        if project is not None:
            self._refresh(project, fit=False)

    def _on_project_changed(self, project: ProjectDocument) -> None:
        self._refresh(project, fit=True)

    def _on_project_content_changed(self, project: ProjectDocument) -> None:
        self._refresh(project, fit=False)

    def _on_selection_changed(self, selection: object | None) -> None:
        component_id = selection.get("id") if isinstance(selection, dict) else None
        self.viewer.set_selected_component(component_id if isinstance(component_id, str) else None)
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
            params = (
                component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
            )
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
        self._api.unsubscribe(
            "geometry.viewer.settings.changed",
            self._on_viewer_settings_changed,
        )
        self._api.remove_project_listener(self._on_project_changed)
        self._api.remove_project_content_listener(self._on_project_content_changed)
        self._api.remove_selection_listener(self._on_selection_changed)
        self._api.remove_section_selection_listener(self._on_section_selection_changed)
