"""Screenshot capture dialog for configuring custom resolution and background transparency."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.style.icons import get_icon


class ScreenshotDialog(QDialog):
    """Dialog allowing the user to configure screenshot resolution and transparency."""

    def __init__(
        self,
        initial_width: int = 1920,
        initial_height: int = 1080,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("screenshot_dialog")
        self.setWindowTitle("Capture Screenshot")
        self.setWindowIcon(get_icon("screenshot"))
        self.setModal(True)
        self.setFixedWidth(320)

        init_w = max(1, initial_width)
        init_h = max(1, initial_height)
        self._aspect_ratio = float(init_w) / float(init_h)
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form_layout.setSpacing(8)

        # Width
        self.width_spin = QSpinBox(self)
        self.width_spin.setRange(1, 16384)
        self.width_spin.setSuffix(" px")
        self.width_spin.setValue(init_w)
        form_layout.addRow("Width:", self.width_spin)

        # Height
        self.height_spin = QSpinBox(self)
        self.height_spin.setRange(1, 16384)
        self.height_spin.setSuffix(" px")
        self.height_spin.setValue(init_h)
        form_layout.addRow("Height:", self.height_spin)

        layout.addLayout(form_layout)

        # Lock aspect ratio
        self.lock_aspect_check = QCheckBox("Lock aspect ratio", self)
        self.lock_aspect_check.setChecked(True)
        layout.addWidget(self.lock_aspect_check)

        # Transparent background
        self.transparent_check = QCheckBox("Transparent background", self)
        self.transparent_check.setChecked(False)
        layout.addWidget(self.transparent_check)

        # Signals for aspect ratio locking
        self.width_spin.valueChanged.connect(self._on_width_changed)
        self.height_spin.valueChanged.connect(self._on_height_changed)
        self.lock_aspect_check.toggled.connect(self._on_lock_toggled)

        layout.addSpacing(6)

        # Buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Capture")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _on_width_changed(self, new_width: int) -> None:
        if self._updating or not self.lock_aspect_check.isChecked():
            return
        if self._aspect_ratio <= 0:
            return
        self._updating = True
        try:
            new_height = max(1, round(new_width / self._aspect_ratio))
            self.height_spin.setValue(new_height)
        finally:
            self._updating = False

    def _on_height_changed(self, new_height: int) -> None:
        if self._updating or not self.lock_aspect_check.isChecked():
            return
        self._updating = True
        try:
            new_width = max(1, round(new_height * self._aspect_ratio))
            self.width_spin.setValue(new_width)
        finally:
            self._updating = False

    def _on_lock_toggled(self, checked: bool) -> None:
        if checked and self.height_spin.value() > 0:
            self._aspect_ratio = float(self.width_spin.value()) / float(self.height_spin.value())

    @property
    def resolution(self) -> tuple[int, int]:
        """Return the configured (width, height) resolution in pixels."""
        return self.width_spin.value(), self.height_spin.value()

    @property
    def transparent_background(self) -> bool:
        """Return whether transparent background is requested."""
        return self.transparent_check.isChecked()
