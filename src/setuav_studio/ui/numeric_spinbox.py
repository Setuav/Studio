"""Clean, theme-aware NumericSpinBox widget for embedding in table cells and parameter forms."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QSizePolicy,
    QTableWidget,
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
        if (
            watched == self.lineEdit()
            and event.type() == QEvent.Type.Wheel
            and not self._is_active_focus()
        ):
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
        mult = (
            0.1
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            else (5.0 if event.modifiers() & Qt.KeyboardModifier.ControlModifier else 1.0)
        )
        self.setValue(self.value() + direction * self.singleStep() * mult)
        event.accept()


def set_table_spinbox(
    table: QTableWidget,
    row: int,
    column: int,
    value: float | str,
    *,
    min_val: float = -1e6,
    max_val: float = 1e6,
    step: float = 1.0,
    decimals: int = 2,
    suffix: str = "",
    quantity: str | None = None,
    unit: str | None = None,
    on_changed: Callable[[Any], None] | None = None,
    api: Any | None = None,
    label: str = "",
) -> Any:
    """Helper to cleanly place an ExpressionPropertyCell with fx assistant into a QTableWidget cell."""
    from setuav_studio.ui.property_tables import ExpressionPropertyCell

    item = table.item(row, column)
    if item is not None:
        item.setText("")
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

    if not label:
        col0_item = table.item(row, 0)
        label = col0_item.text() if col0_item else ""

    resolved_api = api
    if resolved_api is None:
        parent = table.parent()
        while parent is not None:
            if hasattr(parent, "_api"):
                resolved_api = parent._api
                break
            parent = parent.parent()

    def handle_cell_changed(new_text: str) -> None:
        if on_changed is None:
            return
        clean = new_text.strip()
        if clean.startswith("=") or not clean.replace(".", "", 1).replace("-", "", 1).isdigit():
            if resolved_api is not None and getattr(resolved_api, "current_project", None) is not None:
                try:
                    from setuav_studio.plugins.core.expressions import ExpressionEvaluator

                    evaluator = ExpressionEvaluator()
                    scope = resolved_api.current_project.get_scope(api=resolved_api)
                    expr = clean.lstrip("=").strip()
                    res = evaluator.evaluate(expr, scope)
                    if isinstance(res, (int, float)):
                        on_changed(float(res))
                        return
                except Exception:
                    pass
            on_changed(clean)
        else:
            try:
                on_changed(float(clean))
            except ValueError:
                on_changed(clean)

    from setuav_studio.ui.property_tables import format_engineering_value

    init_str = (
        format_engineering_value(value, decimals)
        if isinstance(value, (int, float)) and not str(value).startswith("=")
        else str(value)
    )
    cell = ExpressionPropertyCell(
        initial_value=init_str,
        on_changed=handle_cell_changed if on_changed else None,
        api=resolved_api,
        label=label,
        decimals=decimals,
        quantity=quantity,
        unit=unit or suffix.strip(),
        parent=table,
    )
    table.setCellWidget(row, column, cell)
    return cell
