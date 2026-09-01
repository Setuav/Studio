"""Clean, theme-aware NumericSpinBox widget for embedding in table cells and parameter forms."""

from __future__ import annotations

import weakref
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
        quantity: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._quantity = quantity
        self.setFont(QApplication.font())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setRange(float(min_value), float(max_value))
        self.setSingleStep(float(step))
        self.setDecimals(int(decimals))

        from setuav_studio.units import get_unit_manager

        if self._quantity:
            sym = get_unit_manager().get_unit_symbol(self._quantity)
            self.setSuffix(f" {sym}" if sym else "")
            get_unit_manager().units_changed.connect(self._on_units_changed)
            self.destroyed.connect(self._disconnect_units_changed)
        elif suffix:
            s = str(suffix).strip()
            self.setSuffix(f" {s}" if s else "")

        self.setValue(float(value))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.setKeyboardTracking(False)
        self._setup_focus_and_filter()

    def _setup_focus_and_filter(self) -> None:
        # By default QAbstractSpinBox uses WheelFocus (which steals focus & scrolls on mouse hover).
        # We enforce StrongFocus so wheel never focuses the widget during casual page scrolling.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            line_edit.installEventFilter(self)

    def _disconnect_units_changed(self) -> None:
        try:
            from setuav_studio.units import get_unit_manager

            get_unit_manager().units_changed.disconnect(self._on_units_changed)
        except (RuntimeError, TypeError):
            pass

    def _on_units_changed(self) -> None:
        if self._quantity:
            from setuav_studio.units import get_unit_manager

            sym = get_unit_manager().get_unit_symbol(self._quantity)
            self.setSuffix(f" {sym}" if sym else "")

        self._setup_focus_and_filter()

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


def _resolve_table_api(table: QTableWidget, explicit_api: Any | None) -> Any | None:
    if explicit_api is not None:
        return explicit_api
    parent = table.parent()
    while parent is not None:
        api = getattr(parent, "_api", None)
        if api is not None:
            return api
        parent = parent.parent()
    return None


def _parse_spinbox_callback_value(
    new_text: str,
    api: Any | None,
    min_val: float | None = None,
    max_val: float | None = None,
) -> Any:
    clean = new_text.strip()
    if clean.startswith("=") or not clean.replace(".", "", 1).replace("-", "", 1).isdigit():
        if api is not None and getattr(api, "current_project", None) is not None:
            try:
                from setuav_studio.model.expressions import ExpressionEvaluator

                evaluator = ExpressionEvaluator()
                scope = api.current_project.get_scope(api=api)
                res = evaluator.evaluate(clean.lstrip("=").strip(), scope)
                if isinstance(res, (int, float)):
                    num = float(res)
                    if min_val is not None:
                        num = max(min_val, num)
                    if max_val is not None:
                        num = min(max_val, num)
                    return num
            except Exception:
                pass
        return clean
    try:
        num = float(clean)
        if min_val is not None:
            num = max(min_val, num)
        if max_val is not None:
            num = min(max_val, num)
        return num
    except ValueError:
        return clean


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
    from setuav_studio.ui.property_tables import ExpressionPropertyCell, format_engineering_value

    item = table.item(row, column)
    if item is not None:
        item.setText("")
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

    if not label:
        col0_item = table.item(row, 0)
        label = col0_item.text() if col0_item else ""

    resolved_api = _resolve_table_api(table, api)

    on_changed_ref = (
        weakref.WeakMethod(on_changed)
        if callable(on_changed) and hasattr(on_changed, "__self__")
        else on_changed
    )

    def handle_cell_changed(new_text: str) -> None:
        cb = on_changed_ref() if isinstance(on_changed_ref, weakref.WeakMethod) else on_changed_ref
        if cb is not None:
            cb(_parse_spinbox_callback_value(new_text, resolved_api, min_val, max_val))

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
    )
    table.setCellWidget(row, column, cell)
    return cell
