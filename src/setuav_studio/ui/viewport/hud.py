"""Fixed bottom control HUD bar for the 3D Studio Viewport."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QToolButton,
)

from setuav_studio.ui.style.icons import get_icon
from setuav_studio.ui.viewport.constants import (
    FACE_COLORED,
    FACE_MONOCHROME,
    WIRE_FEATURE,
    WIRE_FULL,
)

if TYPE_CHECKING:
    from setuav_studio.ui.viewport.viewport import StudioViewport


class StudioViewportHUD(QFrame):
    """Fixed bottom control bar anchored at the bottom-center of the 3D viewport.

    Provides quick access to:
      - Solid / Wireframe / Transparency rendering modes
      - Colored vs Monochrome shading
      - Reference grid and orthographic / perspective projection
      - Camera viewpoints (Top, Bottom, Front, Side, Iso) and Fit
      - High-resolution screenshot capture
    """

    def __init__(self, viewport: StudioViewport) -> None:
        super().__init__(viewport)
        self._viewport = viewport

        self.setObjectName("viewerHUD")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setAutoFillBackground(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(3)

        # 1. Solid surface toggle
        self.solid_button = QToolButton(self)
        self.solid_button.setCheckable(True)
        self.solid_button.setChecked(self._viewport.is_show_solid())
        self.solid_button.setIcon(get_icon("view_solid"))
        self.solid_button.setToolTip("Toggle Solid Surface")
        self.solid_button.setFixedSize(24, 24)
        self.solid_button.setAutoRaise(True)
        self.solid_button.toggled.connect(self._viewport.set_show_solid)
        layout.addWidget(self.solid_button)

        # 2. Wireframe mode menu
        self.wire_button = QToolButton(self)
        self.wire_button.setIcon(get_icon("view_wireframe"))
        self.wire_button.setFixedSize(24, 24)
        self.wire_button.setAutoRaise(True)
        self.wire_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._wire_menu = QMenu(self.wire_button)
        self.wire_button.setMenu(self._wire_menu)
        self._build_wire_menu()
        layout.addWidget(self.wire_button)

        # 3. Transparency (X-Ray) toggle
        self.trans_button = QToolButton(self)
        self.trans_button.setCheckable(True)
        self.trans_button.setChecked(self._viewport.is_transparent())
        self.trans_button.setIcon(get_icon("view_transparent"))
        self.trans_button.setToolTip("Toggle Transparency (X-Ray)")
        self.trans_button.setFixedSize(24, 24)
        self.trans_button.setAutoRaise(True)
        self.trans_button.toggled.connect(self._viewport.set_transparent)
        layout.addWidget(self.trans_button)

        layout.addWidget(self._create_separator())

        # 4. Colored vs Monochrome Shading Group
        self.style_group = QButtonGroup(self)
        self.style_group.setExclusive(True)

        self.colored_button = QToolButton(self)
        self.colored_button.setCheckable(True)
        self.colored_button.setChecked(self._viewport.face_style() == FACE_COLORED)
        self.colored_button.setIcon(get_icon("view_colored"))
        self.colored_button.setToolTip("Component Colors")
        self.colored_button.setFixedSize(24, 24)
        self.colored_button.setAutoRaise(True)
        self.colored_button.clicked.connect(lambda: self._viewport.set_face_style(FACE_COLORED))
        self.style_group.addButton(self.colored_button)
        layout.addWidget(self.colored_button)

        self.mono_button = QToolButton(self)
        self.mono_button.setCheckable(True)
        self.mono_button.setChecked(self._viewport.face_style() == FACE_MONOCHROME)
        self.mono_button.setIcon(get_icon("view_monochrome"))
        self.mono_button.setToolTip("Monochrome / Neutral")
        self.mono_button.setFixedSize(24, 24)
        self.mono_button.setAutoRaise(True)
        self.mono_button.clicked.connect(lambda: self._viewport.set_face_style(FACE_MONOCHROME))
        self.style_group.addButton(self.mono_button)
        layout.addWidget(self.mono_button)

        layout.addWidget(self._create_separator())

        # 5. Grid toggle
        self.grid_button = QToolButton(self)
        self.grid_button.setCheckable(True)
        self.grid_button.setChecked(self._viewport.is_show_grid())
        self.grid_button.setIcon(get_icon("view_grid"))
        self.grid_button.setToolTip("Toggle Reference Grid")
        self.grid_button.setFixedSize(24, 24)
        self.grid_button.setAutoRaise(True)
        self.grid_button.toggled.connect(self._viewport.set_show_grid)
        layout.addWidget(self.grid_button)

        # 6. Projection toggle (Orthographic vs Perspective)
        self.projection_button = QToolButton(self)
        self.projection_button.setCheckable(True)
        self.projection_button.setChecked(self._viewport.is_orthographic())
        self.projection_button.setFixedSize(24, 24)
        self.projection_button.setAutoRaise(True)
        self.projection_button.toggled.connect(self._on_projection_toggled)
        layout.addWidget(self.projection_button)
        self._update_projection_state()

        # 7. Layers button with checkable visibility menu
        self.layers_button = QToolButton(self)
        self.layers_button.setIcon(get_icon("view_layers"))
        self.layers_button.setToolTip("Layers")
        self.layers_button.setFixedSize(24, 24)
        self.layers_button.setAutoRaise(True)
        self.layers_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._layers_menu = QMenu(self.layers_button)
        self.layers_button.setMenu(self._layers_menu)
        self._layers_menu.aboutToShow.connect(self._build_layers_menu)
        self._build_layers_menu()
        layout.addWidget(self.layers_button)

        # Connect viewport layer signals to update layer menu
        self._viewport.layers_changed.connect(self._build_layers_menu)
        self._viewport.layer_visibility_changed.connect(self._on_layer_visibility_changed)

        layout.addWidget(self._create_separator())

        # 8. Standard Camera Viewpoints
        self._cam_buttons: list[tuple[QToolButton, str]] = []
        view_presets = (
            ("camera_top", "Top View", "top"),
            ("camera_bottom", "Bottom View", "bottom"),
            ("camera_front", "Front View", "front"),
            ("camera_side", "Side View", "side"),
            ("camera_iso", "Isometric View", "iso"),
        )
        for icon, tooltip, preset in view_presets:
            btn = QToolButton(self)
            btn.setIcon(get_icon(icon))
            btn.setToolTip(tooltip)
            btn.setFixedSize(24, 24)
            btn.setAutoRaise(True)
            btn.clicked.connect(
                lambda _checked=False, p=preset: self._viewport.set_view_preset(p)  # type: ignore[arg-type]
            )
            self._cam_buttons.append((btn, icon))
            layout.addWidget(btn)

        # 8. Fit View button
        self.fit_button = QToolButton(self)
        self.fit_button.setIcon(get_icon("view_fit"))
        self.fit_button.setToolTip("Fit Model in View (F)")
        self.fit_button.setFixedSize(24, 24)
        self.fit_button.setAutoRaise(True)
        self.fit_button.clicked.connect(self._viewport.fit_view)
        layout.addWidget(self.fit_button)

        layout.addWidget(self._create_separator())

        # 9. Screenshot button opening custom resolution dialog
        self.screenshot_button = QToolButton(self)
        self.screenshot_button.setIcon(get_icon("screenshot"))
        self.screenshot_button.setToolTip("Capture Screenshot")
        self.screenshot_button.setFixedSize(24, 24)
        self.screenshot_button.setAutoRaise(True)
        self.screenshot_button.clicked.connect(self._open_screenshot_dialog)
        layout.addWidget(self.screenshot_button)

        self.adjustSize()

    def update_theme_style(self) -> None:
        """Update icons and palette styles when the application theme changes."""
        self.setPalette(self.palette())
        self.solid_button.setIcon(get_icon("view_solid"))
        self.wire_button.setIcon(get_icon("view_wireframe"))
        self.colored_button.setIcon(get_icon("view_colored"))
        self.mono_button.setIcon(get_icon("view_monochrome"))
        self.trans_button.setIcon(get_icon("view_transparent"))
        self.grid_button.setIcon(get_icon("view_grid"))
        self._update_projection_state()
        self.layers_button.setIcon(get_icon("view_layers"))
        for btn, icon_name in self._cam_buttons:
            btn.setIcon(get_icon(icon_name))
        self.fit_button.setIcon(get_icon("view_fit"))
        self.screenshot_button.setIcon(get_icon("screenshot"))

    @staticmethod
    def _create_separator() -> QFrame:
        sep = QFrame()
        sep.setObjectName("hudSep")
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        return sep

    def _build_wire_menu(self) -> None:
        self._wire_menu.clear()
        group = QActionGroup(self)
        group.setExclusive(True)
        is_wire_on = self._viewport.is_show_wireframe()
        current_mode = self._viewport.wire_mode()

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
            self._viewport.set_show_wireframe(False)
        else:
            self._viewport.set_show_wireframe(True)
            self._viewport.set_wire_mode(mode)  # type: ignore[arg-type]
        self._build_wire_menu()
        self._update_wire_tooltip()

    def _update_wire_tooltip(self) -> None:
        if not self._viewport.is_show_wireframe():
            self.wire_button.setToolTip("Wireframe: Off")
        elif self._viewport.wire_mode() == WIRE_FEATURE:
            self.wire_button.setToolTip("Wireframe: Feature Edges")
        else:
            self.wire_button.setToolTip("Wireframe: Full Mesh")

    @property
    def layers_menu(self) -> QMenu:
        """Return the layers popup menu."""
        return self._layers_menu

    def _build_layers_menu(self) -> None:
        self._layers_menu.clear()
        layer_ids = self._viewport.layers()
        if not layer_ids:
            empty_action = QAction("No Layers", self)
            empty_action.setEnabled(False)
            self._layers_menu.addAction(empty_action)
            return

        for layer_id in layer_ids:
            layer = self._viewport.get_layer(layer_id)
            title = layer.name if (layer and layer.name) else layer_id.capitalize()
            action = QAction(title, self)
            action.setData(layer_id)
            action.setCheckable(True)
            action.setChecked(self._viewport.is_layer_visible(layer_id))
            action.triggered.connect(
                lambda _checked=False, act=action, lid=layer_id: self._viewport.set_layer_visible(
                    lid, act.isChecked()
                )
            )
            self._layers_menu.addAction(action)

    def _on_layer_visibility_changed(self, layer_id: str, visible: bool) -> None:
        for action in self._layers_menu.actions():
            if action.data() == layer_id:
                action.blockSignals(True)
                action.setChecked(visible)
                action.blockSignals(False)
                break

    def _on_projection_toggled(self, checked: bool) -> None:
        self._viewport.set_orthographic(checked)
        self._update_projection_state()

    def _update_projection_state(self) -> None:
        is_ortho = self._viewport.is_orthographic()
        mode = "Orthographic" if is_ortho else "Perspective"
        next_mode = "Perspective" if is_ortho else "Orthographic"
        self.projection_button.setChecked(is_ortho)
        self.projection_button.setIcon(
            get_icon("view_isometric" if is_ortho else "view_perspective")
        )
        self.projection_button.setToolTip(f"Projection: {mode} (click for {next_mode})")

    def _open_screenshot_dialog(self) -> None:
        from setuav_studio.ui.dialog.screenshot import ScreenshotDialog

        cur_w = self._viewport.width()
        cur_h = self._viewport.height()
        if cur_w < 100 or cur_h < 100:
            cur_w, cur_h = 1920, 1080

        dialog = ScreenshotDialog(cur_w, cur_h, parent=self.window())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        width, height = dialog.resolution
        transparent = dialog.transparent_background

        image = self._viewport.capture_screenshot(
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
