"""Dialog for scaling an entire fuselage across length, width, height, and radii."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.widget.spinbox import NumericSpinBox
from setuav_studio.units import get_unit_manager

from ...engine.fuselage_geometry import fuselage_extents, scale_fuselage_geometry

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

_MIN_SCALE = 0.05
_MAX_SCALE = 20.0


class ScaleFuselageDialog(QDialog):
    """Interactive dialog for uniform or per-axis fuselage scaling."""

    def __init__(
        self,
        component: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        name = str(component.get("name") or component.get("id") or "Fuselage")
        self.setWindowTitle(f"Scale Fuselage — {name}")
        self.setMinimumWidth(420)

        self._length_mm, self._width_mm, self._height_mm, _min_x = fuselage_extents(component)
        self._syncing = False
        um = get_unit_manager()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.uniform_checkbox = QCheckBox("Uniform scale (lock all axes & radii)")
        self.uniform_checkbox.setChecked(True)
        self.uniform_checkbox.toggled.connect(self._on_uniform_toggled)
        layout.addWidget(self.uniform_checkbox)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        for col, heading in enumerate(("Dimension", "Current", "Scale", "Target")):
            lbl = QLabel(heading)
            font = lbl.font()
            font.setBold(True)
            lbl.setFont(font)
            if col > 0:
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(lbl, 0, col)

        self.scale_x_spin = self._make_scale_spin()
        self.scale_y_spin = self._make_scale_spin()
        self.scale_z_spin = self._make_scale_spin()
        self.scale_r_spin = self._make_scale_spin(min_value=0.0)

        self.target_x_spin = self._make_target_spin(self._length_mm, um)
        self.target_y_spin = self._make_target_spin(self._width_mm, um)
        self.target_z_spin = self._make_target_spin(self._height_mm, um)

        rows: tuple[tuple[str, float, NumericSpinBox, NumericSpinBox], ...] = (
            ("Length (X)", self._length_mm, self.scale_x_spin, self.target_x_spin),
            ("Width (Y)", self._width_mm, self.scale_y_spin, self.target_y_spin),
            ("Height (Z)", self._height_mm, self.scale_z_spin, self.target_z_spin),
        )
        for row_idx, (label, current_mm, scale_spin, target_spin) in enumerate(rows, start=1):
            grid.addWidget(QLabel(label), row_idx, 0)
            current_lbl = QLabel(
                um.format_value(current_mm, "length", 1) if current_mm > 0 else "—"
            )
            current_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(current_lbl, row_idx, 1)
            grid.addWidget(scale_spin, row_idx, 2)
            grid.addWidget(target_spin, row_idx, 3)

        grid.addWidget(QLabel("Radii"), 4, 0)
        dash_lbl = QLabel("—")
        dash_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(dash_lbl, 4, 1)
        grid.addWidget(self.scale_r_spin, 4, 2)
        radii_hint = QLabel("All corners & vertices")
        radii_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(radii_hint, 4, 3)

        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)
        layout.addLayout(grid)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("Scale")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.scale_x_spin.valueChanged.connect(lambda v: self._on_scale_changed("x", v))
        self.scale_y_spin.valueChanged.connect(lambda v: self._on_scale_changed("y", v))
        self.scale_z_spin.valueChanged.connect(lambda v: self._on_scale_changed("z", v))
        self.scale_r_spin.valueChanged.connect(lambda v: self._on_scale_changed("r", v))

        self.target_x_spin.valueChanged.connect(lambda v: self._on_target_changed("x", v))
        self.target_y_spin.valueChanged.connect(lambda v: self._on_target_changed("y", v))
        self.target_z_spin.valueChanged.connect(lambda v: self._on_target_changed("z", v))

    @staticmethod
    def _make_scale_spin(*, min_value: float = _MIN_SCALE) -> NumericSpinBox:
        return NumericSpinBox(
            value=1.0,
            min_value=min_value,
            max_value=_MAX_SCALE,
            step=0.05,
            decimals=3,
            suffix="×",
        )

    @staticmethod
    def _make_target_spin(current_mm: float, um: Any) -> NumericSpinBox:
        decimals = um.display_decimals("length", 1)
        disp_val = um.to_display(current_mm, "length") if current_mm > 0.0 else 0.0
        min_disp = um.to_display(max(1.0, current_mm * _MIN_SCALE), "length")
        max_disp = um.to_display(max(100.0, current_mm * _MAX_SCALE), "length")
        spin = NumericSpinBox(
            value=disp_val,
            min_value=min_disp,
            max_value=max_disp,
            step=max(0.1, round(disp_val * 0.05, decimals)),
            decimals=decimals,
            quantity="length",
        )
        spin.setEnabled(current_mm > 1e-6)
        return spin

    def scale_factors(self) -> tuple[float, float, float, float]:
        """Return ``(scale_x, scale_y, scale_z, scale_radius)``."""
        return (
            float(self.scale_x_spin.value()),
            float(self.scale_y_spin.value()),
            float(self.scale_z_spin.value()),
            float(self.scale_r_spin.value()),
        )

    def _on_uniform_toggled(self, checked: bool) -> None:
        if checked:
            self._on_scale_changed("x", float(self.scale_x_spin.value()))

    def _on_scale_changed(self, axis: str, value: float) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            if self.uniform_checkbox.isChecked():
                clamped = max(_MIN_SCALE, value)
                for spin in (
                    self.scale_x_spin,
                    self.scale_y_spin,
                    self.scale_z_spin,
                    self.scale_r_spin,
                ):
                    spin.setValue(clamped)
                self._sync_all_targets()
            else:
                self._sync_target_for(axis)
        finally:
            self._syncing = False

    def _on_target_changed(self, axis: str, display_value: float) -> None:
        if self._syncing:
            return
        base_map = {"x": self._length_mm, "y": self._width_mm, "z": self._height_mm}
        current_mm = base_map[axis]
        if current_mm <= 1e-6:
            return
        um = get_unit_manager()
        target_mm = um.to_base(display_value, "length")
        factor = max(_MIN_SCALE, min(_MAX_SCALE, target_mm / current_mm))

        self._syncing = True
        try:
            if self.uniform_checkbox.isChecked():
                for spin in (
                    self.scale_x_spin,
                    self.scale_y_spin,
                    self.scale_z_spin,
                    self.scale_r_spin,
                ):
                    spin.setValue(factor)
                self._sync_all_targets()
            else:
                spin_map = {
                    "x": self.scale_x_spin,
                    "y": self.scale_y_spin,
                    "z": self.scale_z_spin,
                }
                spin_map[axis].setValue(factor)
        finally:
            self._syncing = False

    def _sync_target_for(self, axis: str) -> None:
        um = get_unit_manager()
        mapping = {
            "x": (self._length_mm, self.scale_x_spin, self.target_x_spin),
            "y": (self._width_mm, self.scale_y_spin, self.target_y_spin),
            "z": (self._height_mm, self.scale_z_spin, self.target_z_spin),
        }
        entry = mapping.get(axis)
        if entry is None:
            return
        current_mm, scale_spin, target_spin = entry
        if current_mm > 1e-6:
            target_spin.setValue(um.to_display(current_mm * float(scale_spin.value()), "length"))

    def _sync_all_targets(self) -> None:
        for axis in ("x", "y", "z"):
            self._sync_target_for(axis)


def open_scale_fuselage_dialog(
    api: StudioAPI,
    component: dict[str, Any],
    parent: QWidget | None = None,
) -> bool:
    """Open the Scale Fuselage dialog and apply scaling in one undoable edit."""
    project = api.project
    if project is None:
        api.show_status("Open a project before scaling geometry", "warning")
        return False
    if project.read_only:
        api.show_status("The project is read-only", "warning")
        return False

    comp_id = str(component.get("id") or "")
    fresh = project.get_component(comp_id) if comp_id else component
    if fresh is None:
        return False

    dialog = ScaleFuselageDialog(fresh, parent=parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False

    sx, sy, sz, sr = dialog.scale_factors()
    if (
        abs(sx - 1.0) <= 1e-9
        and abs(sy - 1.0) <= 1e-9
        and abs(sz - 1.0) <= 1e-9
        and abs(sr - 1.0) <= 1e-9
    ):
        return False

    def _apply() -> None:
        target = project.get_component(comp_id) if comp_id else fresh
        if target is not None:
            scale_fuselage_geometry(
                target,
                scale_x=sx,
                scale_y=sy,
                scale_z=sz,
                scale_radius=sr,
            )

    api.edit_component(fresh, "Scale fuselage", _apply)
    name = str(fresh.get("name") or comp_id or "Fuselage")
    api.show_status(f"Scaled {name}", "success", 3000)
    return True


__all__ = ["ScaleFuselageDialog", "open_scale_fuselage_dialog"]
