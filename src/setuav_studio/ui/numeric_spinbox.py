"""Clean, theme-aware NumericSpinBox widget for embedding in table cells and parameter forms."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QKeyEvent, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse wheel events to prevent accidental changes while scrolling."""

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()


class NumericSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox with up/down arrows and safe wheel scrolling (only active when focused)."""

    def __init__(
        self,
        value: float = 0.0,
        min_value: float = -1e6,
        max_value: float = 1e6,
        step: float = 1.0,
        decimals: int = 2,
        suffix: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFont(QApplication.font())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setRange(float(min_value), float(max_value))
        self.setSingleStep(float(step))
        self.setDecimals(int(decimals))
        if suffix:
            s = str(suffix).strip()
            self.setSuffix(f" {s}" if s else "")
        self.setValue(float(value))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.setKeyboardTracking(False)

        # By default QAbstractSpinBox uses WheelFocus (which steals focus & scrolls on mouse hover).
        # We enforce StrongFocus so wheel never focuses the widget during casual page scrolling.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            line_edit.installEventFilter(self)

    def _is_active_focus(self) -> bool:
        return self.hasFocus() or (self.lineEdit() is not None and self.lineEdit().hasFocus())

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched == self.lineEdit() and event.type() == QEvent.Type.Wheel:
            if not self._is_active_focus():
                event.ignore()
                return False
        return super().eventFilter(watched, event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        # Crucial UX rule: Only adjust value when the spinbox is explicitly focused (clicked/selected)!
        if not self._is_active_focus():
            event.ignore()
            return

        delta = event.angleDelta().y()
        if delta == 0:
            return

        direction = 1.0 if delta > 0 else -1.0
        mult = 0.1 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else (5.0 if event.modifiers() & Qt.KeyboardModifier.ControlModifier else 1.0)
        self.setValue(self.value() + direction * self.singleStep() * mult)
        event.accept()


def set_table_spinbox(
    table: QTableWidget,
    row: int,
    column: int,
    value: float,
    *,
    min_val: float = -1e6,
    max_val: float = 1e6,
    step: float = 1.0,
    decimals: int = 2,
    suffix: str = "",
    on_changed: Callable[[float], None] | None = None,
) -> NumericSpinBox:
    """Helper to cleanly place a NumericSpinBox into a QTableWidget cell."""
    item = table.item(row, column)
    if item is not None:
        item.setText("")
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

    spin = NumericSpinBox(
        value=value,
        min_value=min_val,
        max_value=max_val,
        step=step,
        decimals=decimals,
        suffix=suffix,
        parent=table,
    )
    if on_changed is not None:
        spin.valueChanged.connect(on_changed)
    table.setCellWidget(row, column, spin)
    return spin
