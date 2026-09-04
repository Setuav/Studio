import logging
from contextlib import suppress

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QMenu,
    QMessageBox,
    QToolButton,
    QWidget,
)

from setuav_studio.project import ProjectDocument
from setuav_studio.ui.icons import get_icon
from setuav_studio_sdk import StudioAPI, StudioEvents

from .settings import (
    _VIEWER_GRID_KEY,
    _VIEWER_PALETTE_KEY,
    _VIEWER_PROJECTION_KEY,
    _VIEWER_SCREENSHOT_TRANSPARENT_KEY,
    _VIEWER_SOLID_KEY,
    _VIEWER_WIRE_KEY,
    _VIEWER_WIRE_MODE_KEY,
    viewer_setting,
)
from .viewport.mesh import (
    FACE_COLORED,
    FACE_MONOCHROME,
    WIRE_FEATURE,
    WIRE_FULL,
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
            StudioEvents.GEOMETRY_VIEWER_SETTINGS_CHANGED,
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

        # Display Toggles (Solid surface toggle & Wireframe mode popup menu)
        self.solid_button = QToolButton(self.hud)
        self.solid_button.setCheckable(True)
        self.solid_button.setChecked(self._default_show_solid)
        self.solid_button.setIcon(get_icon("view_solid"))
        self.solid_button.setToolTip("Toggle Solid Surface")
        self.solid_button.setFixedSize(24, 24)
        self.solid_button.setAutoRaise(True)
        self.solid_button.toggled.connect(self._on_solid_toggled)
        hud_layout.addWidget(self.solid_button)

        self.wire_button = QToolButton(self.hud)
        self.wire_button.setIcon(get_icon("view_wireframe"))
        self.wire_button.setFixedSize(24, 24)
        self.wire_button.setAutoRaise(True)
        self.wire_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._wire_menu = QMenu(self.wire_button)
        self.wire_button.setMenu(self._wire_menu)
        self._build_wire_menu()
        hud_layout.addWidget(self.wire_button)

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

        sep1 = QFrame(self.hud)
        sep1.setObjectName("hudSep")
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setFrameShadow(QFrame.Shadow.Plain)
        hud_layout.addWidget(sep1)

        # Shading / Surface Style Group (Exclusive: Colored / Monochrome)
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

        # Color Palette Selector (between Colored and Monochrome)
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
        self.projection_button.setFixedSize(24, 24)
        self.projection_button.setAutoRaise(True)
        self.projection_button.toggled.connect(self._on_projection_toggled)
        hud_layout.addWidget(self.projection_button)
        self._update_projection_state()

        sep3 = QFrame(self.hud)
        sep3.setObjectName("hudSep")
        sep3.setFrameShape(QFrame.Shape.VLine)
        sep3.setFrameShadow(QFrame.Shadow.Plain)
        hud_layout.addWidget(sep3)

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

        self.fit_button = QToolButton(self.hud)
        self.fit_button.setIcon(get_icon("view_fit"))
        self.fit_button.setToolTip("Fit Model in View (F)")
        self.fit_button.setFixedSize(24, 24)
        self.fit_button.setAutoRaise(True)
        self.fit_button.clicked.connect(self.viewer.fit_view)
        hud_layout.addWidget(self.fit_button)

        sep_screenshot = QFrame(self.hud)
        sep_screenshot.setObjectName("hudSep")
        sep_screenshot.setFrameShape(QFrame.Shape.VLine)
        sep_screenshot.setFrameShadow(QFrame.Shadow.Plain)
        hud_layout.addWidget(sep_screenshot)

        # Screenshot Button with Resolution Menu
        self.screenshot_button = QToolButton(self.hud)
        self.screenshot_button.setIcon(get_icon("screenshot"))
        self.screenshot_button.setToolTip("Capture Screenshot")
        self.screenshot_button.setFixedSize(24, 24)
        self.screenshot_button.setAutoRaise(True)
        self.screenshot_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._screenshot_menu = QMenu(self.screenshot_button)
        self._screenshot_presets = [
            ("HD (1280 × 720)", 1280, 720),
            ("Full HD (1920 × 1080)", 1920, 1080),
            ("QHD (2560 × 1440)", 2560, 1440),
            ("4K UHD (3840 × 2160)", 3840, 2160),
        ]
        for label, w, h in self._screenshot_presets:
            self._screenshot_menu.addAction(
                label,
                lambda _checked=False, sw=w, sh=h: self._take_screenshot(sw, sh),
            )
        self._screenshot_menu.addSeparator()
        self._screenshot_menu.addAction("Custom Resolution…", self._take_screenshot_custom)
        self._screenshot_menu.addSeparator()
        self._action_transparent_bg = self._screenshot_menu.addAction("Transparent Background")
        self._action_transparent_bg.setCheckable(True)
        self._action_transparent_bg.setChecked(
            _as_bool(
                viewer_setting(_VIEWER_SCREENSHOT_TRANSPARENT_KEY, False),
                False,
            )
        )
        self._action_transparent_bg.toggled.connect(
            lambda checked: QSettings().setValue(_VIEWER_SCREENSHOT_TRANSPARENT_KEY, checked)
        )
        self.screenshot_button.setMenu(self._screenshot_menu)
        hud_layout.addWidget(self.screenshot_button)

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
        self._update_projection_state()
        self.palette_button.setIcon(get_icon("view_palette"))
        for btn, icon_name in self._cam_buttons:
            btn.setIcon(get_icon(icon_name))
        self.fit_button.setIcon(get_icon("view_fit"))
        self.screenshot_button.setIcon(get_icon("screenshot"))
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

    def _build_wire_menu(self) -> None:
        self._wire_menu.clear()
        group = QActionGroup(self)
        group.setExclusive(True)
        is_wire_on = self.viewer._show_wireframe
        current_mode = self.viewer.wire_mode()

        modes = (
            ("Off", "off", not is_wire_on),
            ("Feature Edges", WIRE_FEATURE, is_wire_on and current_mode == WIRE_FEATURE),
            ("Full Mesh", WIRE_FULL, is_wire_on and current_mode == WIRE_FULL),
        )
        for label, mode_key, is_checked in modes:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(is_checked)
            action.triggered.connect(
                lambda _checked=False, m=mode_key: self._on_wire_mode_selected(m)
            )
            group.addAction(action)
            self._wire_menu.addAction(action)
        self._update_wire_tooltip()

    def _on_wire_mode_selected(self, mode: str) -> None:
        if mode == "off":
            self.viewer.set_show_wireframe(False)
            QSettings().setValue(_VIEWER_WIRE_KEY, False)
        else:
            self.viewer.set_show_wireframe(True)
            self.viewer.set_wire_mode(mode)
            QSettings().setValue(_VIEWER_WIRE_KEY, True)
            QSettings().setValue(_VIEWER_WIRE_MODE_KEY, mode)
        self._build_wire_menu()
        self._update_wire_tooltip()

    def _on_solid_toggled(self, checked: bool) -> None:
        self.viewer.set_show_solid(checked)
        QSettings().setValue(_VIEWER_SOLID_KEY, checked)

    def _on_grid_toggled(self, checked: bool) -> None:
        self.viewer.set_show_grid(checked)
        QSettings().setValue(_VIEWER_GRID_KEY, checked)

    def _on_projection_toggled(self, checked: bool) -> None:
        self.viewer.set_orthographic(checked)
        QSettings().setValue(
            _VIEWER_PROJECTION_KEY,
            "orthographic" if checked else "perspective",
        )
        self._update_projection_state()

    def _update_projection_state(self) -> None:
        is_ortho = self.projection_button.isChecked()
        mode = "Orthographic" if is_ortho else "Perspective"
        next_mode = "Perspective" if is_ortho else "Orthographic"
        self.projection_button.setIcon(
            get_icon("view_isometric" if is_ortho else "view_perspective")
        )
        self.projection_button.setToolTip(f"Projection: {mode} (click for {next_mode})")

    def _update_wire_tooltip(self) -> None:
        if not self.viewer._show_wireframe:
            self.wire_button.setToolTip("Wireframe: Off")
        elif self.viewer.wire_mode() == WIRE_FEATURE:
            self.wire_button.setToolTip("Wireframe: Feature Edges")
        else:
            self.wire_button.setToolTip("Wireframe: Full Mesh")

    def _load_viewer_defaults(self) -> None:
        projection = str(viewer_setting(_VIEWER_PROJECTION_KEY, "orthographic")).lower()
        self._default_orthographic = projection != "perspective"

        palette = str(viewer_setting(_VIEWER_PALETTE_KEY, active_palette())).lower()
        with suppress(ValueError):
            set_active_palette(palette)

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
        wire_mode = str(viewer_setting(_VIEWER_WIRE_MODE_KEY, WIRE_FEATURE)).lower()
        if wire_mode in (WIRE_FEATURE, WIRE_FULL):
            self.viewer.set_wire_mode(wire_mode)
        self.viewer.set_show_solid(self._default_show_solid)
        self.viewer.set_show_wireframe(self._default_show_wire)
        self.viewer.set_orthographic(self._default_orthographic)
        if hasattr(self, "_action_transparent_bg"):
            self._action_transparent_bg.blockSignals(True)
            self._action_transparent_bg.setChecked(
                _as_bool(
                    viewer_setting(_VIEWER_SCREENSHOT_TRANSPARENT_KEY, False),
                    False,
                )
            )
            self._action_transparent_bg.blockSignals(False)

    def _on_viewer_settings_changed(self, _payload: object = None) -> None:
        self._load_viewer_defaults()
        for button, checked in (
            (self.solid_button, self._default_show_solid),
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
        self._build_wire_menu()
        self._update_projection_tooltip()
        self._update_wire_tooltip()
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

        # 2. Match control surface sub-tag or child component (e.g. "main-wing:control_1", "main-wing:mirror:control_1")
        parts = component_id.split(":")
        sub_tag = parts[-1]
        base_id = parts[0]
        for component in raw_components:
            cid = str(component.get("id") or "")
            params = (
                component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
            )
            geom = params.get("geometry") if isinstance(params.get("geometry"), dict) else {}
            tag = str(geom.get("tag") or component.get("name") or cid)
            if (
                cid in (sub_tag, f"{base_id}-{sub_tag}", f"{base_id}_{sub_tag}")
                or tag == sub_tag
                or sub_tag.endswith(cid)
            ):
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

    def _take_screenshot(
        self,
        width: int,
        height: int,
        transparent: bool | None = None,
    ) -> None:
        if transparent is None:
            transparent = (
                self._action_transparent_bg.isChecked()
                if hasattr(self, "_action_transparent_bg")
                else False
            )
        image = self.viewer.capture_screenshot(
            width,
            height,
            transparent_background=transparent,
        )
        if image is None or image.isNull():
            QMessageBox.warning(
                self,
                "Screenshot",
                "Could not capture screenshot.\nThe OpenGL context may not be available.",
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Screenshot",
            f"screenshot_{width}x{height}.png",
            "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;All Files (*)",
        )
        if not path:
            return

        if not image.save(path):
            QMessageBox.warning(
                self,
                "Screenshot",
                f"Failed to save image to:\n{path}",
            )

    def _take_screenshot_custom(self) -> None:
        text, ok = QInputDialog.getText(
            self,
            "Custom Resolution",
            "Enter resolution (Width x Height):",
            text="1920x1080",
        )
        if not ok or not text:
            return
        text = text.strip().lower().replace("×", "x")
        parts = text.split("x")
        if len(parts) != 2:
            QMessageBox.warning(
                self, "Invalid Resolution", "Format: WIDTHxHEIGHT  (e.g. 1920x1080)"
            )
            return
        try:
            width, height = int(parts[0].strip()), int(parts[1].strip())
        except ValueError:
            QMessageBox.warning(self, "Invalid Resolution", "Width and height must be integers.")
            return
        if width < 1 or height < 1 or width > 16384 or height > 16384:
            QMessageBox.warning(
                self, "Invalid Resolution", "Resolution must be between 1×1 and 16384×16384."
            )
            return
        self._take_screenshot(width, height)

    def _detach(self, *_args: object) -> None:
        self._api.unsubscribe(
            "geometry.viewer.settings.changed",
            self._on_viewer_settings_changed,
        )
        self._api.remove_project_listener(self._on_project_changed)
        self._api.remove_project_content_listener(self._on_project_content_changed)
        self._api.remove_selection_listener(self._on_selection_changed)
        self._api.remove_section_selection_listener(self._on_section_selection_changed)
