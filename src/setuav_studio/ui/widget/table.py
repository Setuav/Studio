"""Shared property-table helpers for editors, docks and dialogs.

`PropertyTableMixin` provides shared "Property / Value" table building blocks
for component editors, docks and results panels. Subclasses tune behaviour
via class attributes instead of reimplementing table plumbing:

    table_headers                 column labels for _property_table
    table_edit_triggers           edit triggers enabled on the table
    table_value_placeholder       initial text for value cells
    table_value_editable_default  editable flag used when _set_property_value
                                  is called without an explicit editable
    table_combo_cls               widget class used for combo cells
    table_combo_strict_find       only select a combo entry when the value
                                  actually matches one of the options
    table_max_visible_rows        height cap for _fit_table_height (None = all)
    table_scroll_policy_off       disable horizontal/vertical scroll bars
    table_property_text_spinbox   _property_text also reads QDoubleSpinBox cells
"""

from __future__ import annotations

import weakref
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import (
    QFocusEvent,
    QKeyEvent,
    QResizeEvent,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from setuav_studio.ui.widget.spinbox import evaluate_table_cell_input
from setuav_studio.utilities.listeners import dispatch_listeners

if TYPE_CHECKING:
    from setuav_studio.api import ParameterField

# Receives a bound field's key, its new value and the formula it came from.
ParameterChanged = Callable[[str, Any, "str | None"], None]


class ContentFitTableWidget(QTableWidget):
    """Keep columns content-sized, then share any spare viewport width."""

    def __init__(self, rows: int, columns: int, parent=None) -> None:
        super().__init__(rows, columns, parent)
        self._column_fit_pending = False
        self._fitting_columns = False

    def schedule_column_fit(self) -> None:
        if self._column_fit_pending:
            return
        self._column_fit_pending = True
        QTimer.singleShot(0, self._fit_columns_to_viewport)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.schedule_column_fit()

    def _fit_columns_to_viewport(self) -> None:
        self._column_fit_pending = False
        if self._fitting_columns or self.columnCount() == 0:
            return

        self._fitting_columns = True
        try:
            # Reset expanded columns to their real header/data requirements.
            self.resizeColumnsToContents()
            visible_columns = [
                column for column in range(self.columnCount()) if not self.isColumnHidden(column)
            ]
            if not visible_columns:
                return

            natural_widths = {column: self.columnWidth(column) for column in visible_columns}
            spare_width = self.viewport().width() - sum(natural_widths.values())
            if spare_width <= 0:
                return

            share, remainder = divmod(spare_width, len(visible_columns))
            for index, column in enumerate(visible_columns):
                self.setColumnWidth(
                    column,
                    natural_widths[column] + share + (1 if index < remainder else 0),
                )
        finally:
            self._fitting_columns = False


class ExpressionAssistantEditor(Protocol):
    """A focused formula-capable editor that can open the equation assistant."""

    def open_assistant(self) -> None: ...


class ExpressionFocusTracker:
    """Tracks the currently active/focused formula-capable editor across the studio."""

    _active_editor: ExpressionAssistantEditor | None = None
    _listeners: ClassVar[list[Callable[[], None]]] = []

    @classmethod
    def set_active_editor(cls, editor: ExpressionAssistantEditor | None) -> None:
        if cls._active_editor is not editor:
            cls._active_editor = editor
            dispatch_listeners(cls._listeners)

    @classmethod
    def get_active_editor(cls) -> ExpressionAssistantEditor | None:
        return cls._active_editor

    @classmethod
    def has_active_editor(cls) -> bool:
        return cls._active_editor is not None

    @classmethod
    def add_listener(cls, cb: Callable[[], None]) -> None:
        if cb not in cls._listeners:
            cls._listeners.append(cb)

    @classmethod
    def remove_listener(cls, cb: Callable[[], None]) -> None:
        if cb in cls._listeners:
            cls._listeners.remove(cb)


class FocusAwareLineEdit(QLineEdit):
    """QLineEdit that emits focus signals and provides token-aware formula autocompletion."""

    focused_in = Signal()
    focused_out = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        api: Any | None = None,
        enable_autocomplete: bool = True,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._enable_autocomplete = enable_autocomplete
        self._completer: Any | None = None
        self.installEventFilter(self)
        self.textChanged.connect(self._on_text_changed)

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.focused_in.emit()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        if self._completer is not None:
            popup = self._completer.popup()
            if popup is not None and popup.isVisible():
                return
        self.focused_out.emit()

    def _handle_tab_key(self, popup: QAbstractItemView | None, completer: Any | None) -> bool:
        if popup is None or not popup.isVisible() or completer is None:
            return False
        current_idx = popup.currentIndex()
        if not current_idx.isValid() and popup.model() is not None and popup.model().rowCount() > 0:
            current_idx = popup.model().index(0, 0)

        completion = ""
        if current_idx.isValid():
            val = current_idx.data(Qt.ItemDataRole.UserRole)
            if not val:
                val = current_idx.data(Qt.ItemDataRole.DisplayRole)
                if val:
                    val = str(val).split()[0]
            if val:
                completion = str(val)
        if not completion:
            completion = str(completer.currentCompletion() or "")
        if completion:
            self._insert_completion(completion)
        self.setCursorPosition(len(self.text()))
        popup.hide()
        return True

    def _handle_navigation_key(self, popup: QAbstractItemView | None, event: QKeyEvent) -> bool:
        if popup is not None and popup.isVisible():
            popup.keyPressEvent(event)
            event.accept()
            return True
        return False

    def _trigger_manual_completion(self) -> None:
        if not self._enable_autocomplete:
            return
        self._ensure_completer()
        if self._completer is not None:
            token, _, _ = self._get_current_token()
            self._completer.setCompletionPrefix(token)
            cr = self.cursorRect()
            pop = self._completer.popup()
            if pop is not None:
                col_w = pop.sizeHintForColumn(0)
                sb_w = pop.verticalScrollBar().sizeHint().width()
                cr.setWidth(max(col_w + sb_w + 30, 240))
            self._completer.complete(cr)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        completer = self._completer
        popup = completer.popup() if completer is not None else None
        popup_visible = popup is not None and popup.isVisible()

        if event.type() == QEvent.Type.ShortcutOverride and isinstance(event, QKeyEvent):
            key = event.key()
            if popup_visible and key in (
                Qt.Key.Key_Tab,
                Qt.Key.Key_Backtab,
                Qt.Key.Key_Down,
                Qt.Key.Key_Up,
                Qt.Key.Key_PageDown,
                Qt.Key.Key_PageUp,
            ):
                event.accept()
                return True

        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            key = event.key()

            if (
                watched is self
                and popup_visible
                and key
                in (
                    Qt.Key.Key_Down,
                    Qt.Key.Key_Up,
                    Qt.Key.Key_PageDown,
                    Qt.Key.Key_PageUp,
                )
            ):
                return self._handle_navigation_key(popup, event)

            if key == Qt.Key.Key_Tab:
                if self._handle_tab_key(popup, completer):
                    event.accept()
                    return True

            elif key == Qt.Key.Key_Escape:
                if popup_visible and popup is not None:
                    popup.hide()
                    event.accept()
                    return True

            elif (
                key == Qt.Key.Key_Space and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            ):
                self._trigger_manual_completion()
                event.accept()
                return True

            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if popup_visible and popup is not None:
                    current_idx = popup.currentIndex()
                    if current_idx.isValid():
                        val = current_idx.data(Qt.ItemDataRole.UserRole)
                        if val:
                            self._insert_completion(str(val))
                    popup.hide()
                self._finish_and_exit_editing()
                event.accept()
                return True

        return super().eventFilter(watched, event)

    def _finish_and_exit_editing(self) -> None:
        if self._completer is not None:
            popup = self._completer.popup()
            if popup is not None and popup.isVisible():
                popup.hide()

        p: QWidget | None = self.parentWidget()
        is_delegate_editor = False
        view: QAbstractItemView | None = None
        if p is not None:
            if isinstance(p, QAbstractItemView):
                view = p
                is_delegate_editor = True
            else:
                grandparent = p.parentWidget()
                if (
                    grandparent is not None
                    and isinstance(grandparent, QAbstractItemView)
                    and not isinstance(p, ExpressionPropertyCell)
                ):
                    view = grandparent
                    is_delegate_editor = True

        if is_delegate_editor and view is not None:
            view.commitData(self)
            view.closeEditor(self, QStyledItemDelegate.EndEditHint.SubmitModelCache)
            view.setFocus()
        else:
            self.returnPressed.emit()
            self.editingFinished.emit()
            self.clearFocus()

    def _build_completion_items(self) -> list[tuple[str, str]]:
        """Return list of (insert_text, display_text) in priority order."""
        items: list[tuple[str, str]] = []

        resolved_api = self._api
        if resolved_api is None and hasattr(self.parent(), "_api"):
            resolved_api = getattr(self.parent(), "_api", None)

        if resolved_api is not None and resolved_api.project is not None:
            data = resolved_api.project.data
            if isinstance(data, dict):
                # 1. Project Parameters (Highest priority)
                params = data.get("parameters", {})
                if isinstance(params, dict):
                    for k, val in params.items():
                        clean = str(k).replace("-", "_")
                        val_str = (
                            f"{val:g}"
                            if isinstance(val, (int, float))
                            else str(val if val is not None else "")
                        )
                        label = f"{clean:<18} ({val_str})" if val_str else clean
                        items.append((clean, label))
                        if clean != str(k):
                            orig_label = f"{k!s:<18} ({val_str})" if val_str else str(k)
                            items.append((str(k), orig_label))

                # 2. Components and Component Parameters
                comps = data.get("components", [])
                if isinstance(comps, list):
                    for c in comps:
                        if isinstance(c, dict):
                            cid = str(c.get("id") or "").replace("-", "_")
                            c_type = str(c.get("type") or "component")
                            items.append((cid, f"{cid:<18} [{c_type}]"))
                            c_params = c.get("parameters", {})
                            if isinstance(c_params, dict):
                                for pk, pv in c_params.items():
                                    if not pk.startswith("_"):
                                        p_val_str = (
                                            f"{pv:g}"
                                            if isinstance(pv, (int, float))
                                            else str(pv if pv is not None else "")
                                        )
                                        full_k = f"{cid}.{pk}"
                                        items.append((full_k, f"{full_k:<18} ({p_val_str})"))

        # 3. Mathematical Constants
        items.append(("pi", f"{'pi':<18} (3.14159...)"))
        items.append(("e", f"{'e':<18} (2.71828...)"))
        items.append(("g", f"{'g':<18} (9.80665 m/s²)"))

        # 4. Mathematical Functions
        funcs = [
            ("sqrt(", f"{'sqrt(x)':<18} [func]"),
            ("sin(", f"{'sin(x)':<18} [func]"),
            ("cos(", f"{'cos(x)':<18} [func]"),
            ("tan(", f"{'tan(x)':<18} [func]"),
            ("asin(", f"{'asin(x)':<18} [func]"),
            ("acos(", f"{'acos(x)':<18} [func]"),
            ("atan(", f"{'atan(x)':<18} [func]"),
            ("atan2(", f"{'atan2(y, x)':<18} [func]"),
            ("radians(", f"{'radians(deg)':<18} [func]"),
            ("degrees(", f"{'degrees(rad)':<18} [func]"),
            ("exp(", f"{'exp(x)':<18} [func]"),
            ("log(", f"{'log(x)':<18} [func]"),
            ("log10(", f"{'log10(x)':<18} [func]"),
            ("pow(", f"{'pow(x, y)':<18} [func]"),
            ("abs(", f"{'abs(x)':<18} [func]"),
            ("min(", f"{'min(a, b)':<18} [func]"),
            ("max(", f"{'max(a, b)':<18} [func]"),
            ("ceil(", f"{'ceil(x)':<18} [func]"),
            ("floor(", f"{'floor(x)':<18} [func]"),
            ("round(", f"{'round(x, n)':<18} [func]"),
        ]
        for insert_t, disp_t in funcs:
            items.append((insert_t, disp_t))

        return items

    def _ensure_completer(self) -> None:
        if self._completer is not None:
            return
        from PySide6.QtWidgets import QCompleter

        model = QStandardItemModel(self)
        items = self._build_completion_items()
        for insert_text, display_text in items:
            item = QStandardItem(display_text)
            item.setData(insert_text, Qt.ItemDataRole.UserRole)
            model.appendRow(item)

        completer = QCompleter(model, self)
        completer.setCompletionRole(Qt.ItemDataRole.UserRole)
        completer.setWidget(self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        completer.activated.connect(self._insert_completion)
        self._completer = completer
        self.removeEventFilter(self)
        self.installEventFilter(self)
        popup = completer.popup()
        if popup is not None:
            popup.setStyleSheet(
                "QListView { font-family: monospace; font-size: 11px; padding: 2px; } "
                "QListView::item { padding: 2px 4px; } "
                "QListView::item:selected { background-color: #264f78; color: #ffffff; }"
            )
            popup.installEventFilter(self)

    def _on_text_changed(self, text: str) -> None:
        if not self._enable_autocomplete:
            return

        token, _, _ = self._get_current_token()
        # Open completion popup only when at least 1 character of an identifier is typed
        if len(token) >= 1:
            self._ensure_completer()
            if self._completer is not None:
                self._completer.setCompletionPrefix(token)
                cr = self.cursorRect()
                popup = self._completer.popup()
                if popup is not None:
                    col_w = popup.sizeHintForColumn(0)
                    sb_w = popup.verticalScrollBar().sizeHint().width()
                    cr.setWidth(max(col_w + sb_w + 30, 240))
                self._completer.complete(cr)
        else:
            if self._completer is not None:
                popup = self._completer.popup()
                if popup is not None and popup.isVisible():
                    popup.hide()

    def _get_current_token(self) -> tuple[str, int, int]:
        text = self.text()
        cursor_pos = self.cursorPosition()
        left_text = text[:cursor_pos]
        import re

        match = re.search(r"([A-Za-z_][A-Za-z_0-9\.\-]*)$", left_text)
        if not match:
            return "", cursor_pos, cursor_pos
        token = match.group(1)
        start_pos = cursor_pos - len(token)
        return token, start_pos, cursor_pos

    def _insert_completion(self, completion: str) -> None:
        _, start_pos, end_pos = self._get_current_token()
        text = self.text()
        new_text = text[:start_pos] + completion + text[end_pos:]
        self.setText(new_text)
        self.setCursorPosition(len(self.text()))


def format_engineering_value(val: Any, decimals: int | None = 2) -> str:
    """Cleanly formats numbers removing floating-point noise and keeping engineering precision."""
    if val is None or val == "":
        return ""
    try:
        f_val = float(val)
    except (ValueError, TypeError):
        return str(val)

    effective_decimals = 2 if decimals is None else decimals
    rounded = round(f_val, effective_decimals)
    if abs(rounded) < 1e-12:
        return "0" if effective_decimals == 0 else "0.0"
    if effective_decimals == 0:
        return str(int(rounded))
    if abs(rounded - int(rounded)) < 1e-9:
        return f"{rounded:.1f}"
    formatted = f"{rounded:.{effective_decimals}f}".rstrip("0")
    if formatted.endswith("."):
        formatted += "0"
    return formatted


class ExpressionPropertyCell(QWidget):
    """Table cell editor widget with dual display (evaluated value when idle, formula when editing)."""

    def __init__(
        self,
        initial_value: str = "",
        on_changed: Callable[[str], None] | None = None,
        on_open_assistant: Callable[[str], None] | None = None,
        api: Any | None = None,
        label: str = "",
        decimals: int | None = None,
        quantity: str | None = None,
        unit: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if callable(on_changed):
            if hasattr(on_changed, "__self__"):
                self._on_changed = weakref.WeakMethod(on_changed)
            else:
                self._on_changed = on_changed
        else:
            self._on_changed = None
        self._on_open_assistant = on_open_assistant
        self._api = api
        self._label = label
        self._raw_expression = str(initial_value)
        self._is_focused = False
        self._has_error = False
        self._read_only = False

        from setuav_studio.units import get_quantity_for_unit, get_unit_manager

        self._quantity = quantity or get_quantity_for_unit(unit)
        self._suffix = unit or ""
        self._decimals = decimals
        if self._decimals is None:
            lbl = self._label.lower()
            if any(
                w in lbl
                for w in (
                    "eta",
                    "fraction",
                    "taper",
                    "aspect",
                    "ratio",
                    "area",
                    "dm2",
                    "m2",
                    "dm²",
                    "m²",
                )
            ):
                self._decimals = 3
            else:
                self._decimals = 2

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.line_edit = FocusAwareLineEdit(self, api=api)
        self.line_edit.focused_in.connect(self._on_focus_in)
        self.line_edit.focused_out.connect(self._on_focus_out)
        self.line_edit.returnPressed.connect(self._on_return_pressed)
        layout.addWidget(self.line_edit, 1)

        self.unit_label = QLabel(self)
        self.unit_label.setObjectName("cellUnitBadge")
        self.unit_label.setStyleSheet(
            "QLabel { color: #f0f0f0; font-size: 11px; font-weight: bold; padding-left: 2px; padding-right: 3px; }"
        )
        self.unit_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.unit_label)

        from setuav_studio.api import StudioAPI

        if isinstance(api, StudioAPI):
            api.on_project_content_changed(self._on_project_content_changed)
        get_unit_manager().units_changed.connect(self._refresh_display)
        self.destroyed.connect(self._disconnect_units_changed)
        self._refresh_display()

    def _on_project_content_changed(self, _project: Any) -> None:
        if not self._is_focused:
            self._refresh_display()

    def set_error(self, message: str, *, display_text: str | None = None) -> None:
        """Mark the input cell as erroneous with red highlighting and diagnostic tooltip."""
        self._has_error = True
        self.setProperty("expressionError", True)
        self.line_edit.setProperty("expressionError", True)
        if display_text is not None:
            self.line_edit.setText(display_text)
        self.line_edit.setStyleSheet(
            "color: #e53935; font-weight: bold; background-color: rgba(229, 57, 53, 0.08); border: 1px solid #e53935;"
        )
        self.line_edit.setToolTip(message)

    def clear_error(self) -> None:
        """Clear any erroneous state styling on the input cell."""
        self._has_error = False
        self.setProperty("expressionError", False)
        self.line_edit.setProperty("expressionError", False)

    def _disconnect_units_changed(self) -> None:
        try:
            from setuav_studio.units import get_unit_manager

            get_unit_manager().units_changed.disconnect(self._refresh_display)
        except (RuntimeError, TypeError):
            pass

    def _is_formula(self, text: str) -> bool:
        from setuav_studio.model.expression import ExpressionEvaluator

        return ExpressionEvaluator.is_expression(text)

    def _evaluate_expression(self, expr_text: str) -> tuple[bool, Any, str | None]:
        """Evaluate expression against current project scope (or math fallback)."""
        from setuav_studio.model.expression import (
            ExpressionEvaluationError,
            ExpressionEvaluator,
        )

        try:
            evaluator = ExpressionEvaluator()
            scope = {}
            if self._api is not None and self._api.project is not None:
                scope = self._api.project.get_scope(api=self._api)
            expr = expr_text.lstrip("=").strip()
            val = evaluator.evaluate(expr, scope)
            return True, val, None
        except ExpressionEvaluationError as exc:
            return False, None, str(exc)

    def _display_number(self, base_val: float) -> tuple[str, str]:
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        if self._quantity:
            disp_num = um.to_display(base_val, self._quantity)
            sym = um.get_unit_symbol(self._quantity)
            return format_engineering_value(disp_num, self._decimals), sym
        return format_engineering_value(base_val, self._decimals), self._suffix

    def _refresh_display(self) -> None:
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        active_sym = um.get_unit_symbol(self._quantity) if self._quantity else (self._suffix or "")
        self.unit_label.setText(active_sym)
        self.unit_label.setVisible(bool(active_sym))

        # While being actively edited by the user, only update styling, DO NOT overwrite ongoing input!
        if self._is_focused:
            clean_text = self.line_edit.text().strip()
            if self._is_formula(clean_text):
                self.line_edit.setStyleSheet("color: #4CAF50; font-weight: bold;")
            else:
                self.line_edit.setStyleSheet("")
            return

        clean = self._raw_expression.strip()
        if not clean:
            self.line_edit.blockSignals(True)
            self.clear_error()
            self.line_edit.setText("")
            self.line_edit.setStyleSheet("")
            self.line_edit.setToolTip("")
            self.line_edit.blockSignals(False)
            return

        # Idle / Display mode: show evaluated calculated value if it is a formula
        if self._is_formula(clean):
            ok, val, err_msg = self._evaluate_expression(clean)
            self.line_edit.blockSignals(True)
            if ok and not isinstance(val, bool) and isinstance(val, (int, float)):
                self.clear_error()
                disp_val, sym = self._display_number(float(val))
                self.line_edit.setText(disp_val)
                self.line_edit.setStyleSheet(
                    "color: #4CAF50; font-style: italic; font-weight: bold;"
                )
                tip = f"Bound to: {self._raw_expression}\nCalculated value: {disp_val}"
                if sym:
                    tip += f" {sym}"
                self.line_edit.setToolTip(tip)
            else:
                tip = (
                    f"Formula Error in '{self._raw_expression}':\n{err_msg or 'Failed to evaluate'}"
                )
                self.set_error(tip, display_text=f"#REF! {self._raw_expression}")
            self.line_edit.blockSignals(False)
        else:
            self.line_edit.blockSignals(True)
            try:
                num_val = float(clean)
                disp_val, sym = self._display_number(num_val)
                self.line_edit.setText(disp_val)
                if not self._has_error:
                    self.line_edit.setToolTip(f"{disp_val} {sym}" if sym else "")
                    self.line_edit.setStyleSheet("")
            except ValueError:
                self.set_error(
                    f"Invalid numeric value: '{clean}'",
                    display_text=self._raw_expression,
                )
            self.line_edit.blockSignals(False)

    def _on_focus_in(self) -> None:
        if self._is_focused or self._read_only:
            return
        self._is_focused = True
        ExpressionFocusTracker.set_active_editor(self)
        clean = self._raw_expression.strip()
        self.line_edit.blockSignals(True)
        if self._is_formula(clean):
            self.line_edit.setText(self._raw_expression)
            self.line_edit.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            try:
                num_val = float(clean)
                disp_val, _ = self._display_number(num_val)
                self.line_edit.setText(disp_val)
            except ValueError:
                self.line_edit.setText(self._raw_expression)
            self.line_edit.setStyleSheet("")
        self.line_edit.blockSignals(False)
        self.line_edit.selectAll()

    def _convert_input_to_raw_storage(self, text: str) -> str:
        from setuav_studio.units import get_unit_manager

        if not text or self._is_formula(text):
            return text
        try:
            disp_num = float(text)
            base_num = (
                get_unit_manager().to_base(disp_num, self._quantity) if self._quantity else disp_num
            )
            return str(base_num)
        except ValueError:
            return text

    def _call_on_changed(self, text: str) -> None:
        if self._on_changed is None or self._read_only:
            return
        if isinstance(self._on_changed, weakref.WeakMethod):
            cb = self._on_changed()
            if cb is not None:
                cb(text)
        else:
            self._on_changed(text)

    def _commit_line_edit(self, force: bool = False) -> None:
        if self._read_only or (not self._is_focused and not force):
            return
        new_text = self.line_edit.text().strip()
        if not new_text:
            self._refresh_display()
            return
        new_raw = self._convert_input_to_raw_storage(new_text)
        if new_raw != self._raw_expression:
            self.clear_error()
            self._raw_expression = new_raw
            self._call_on_changed(self._raw_expression)

    def _on_focus_out(self) -> None:
        if not self._is_focused:
            return
        self._commit_line_edit()
        self._is_focused = False
        self._refresh_display()
        QTimer.singleShot(400, self._maybe_clear_focus_tracker)

    def _maybe_clear_focus_tracker(self) -> None:
        if not self._is_focused and ExpressionFocusTracker.get_active_editor() is self:
            ExpressionFocusTracker.set_active_editor(None)

    def get_expression(self) -> str:
        return self._raw_expression.strip()

    def stored_expression(self) -> str | None:
        """Return formula expression if current value is a formula, else None."""
        clean = self._raw_expression.strip()
        return clean if clean and self._is_formula(clean) else None

    def set_expression(self, expr: str) -> None:
        self._raw_expression = expr.strip()
        self._call_on_changed(self._raw_expression)
        self._refresh_display()

    def get_label(self) -> str:
        return self._label

    def open_assistant(self) -> None:
        self._handle_button_clicked()

    def hideEvent(self, event: Any) -> None:
        if ExpressionFocusTracker.get_active_editor() is self:
            ExpressionFocusTracker.set_active_editor(None)
        super().hideEvent(event)

    def _on_return_pressed(self) -> None:
        self._commit_line_edit(force=True)
        self._is_focused = False
        self._refresh_display()
        self.line_edit.clearFocus()

    def setDecimals(self, dec: int) -> None:
        self._decimals = dec
        self._refresh_display()

    def setReadOnly(self, read_only: bool) -> None:
        """Display the value in the active unit without accepting edits or formulas."""
        self._read_only = read_only
        self.line_edit.setReadOnly(read_only)
        self.line_edit.setFocusPolicy(
            Qt.FocusPolicy.NoFocus if read_only else Qt.FocusPolicy.StrongFocus
        )

    def isReadOnly(self) -> bool:
        return self._read_only

    def _handle_button_clicked(self) -> None:
        if self._on_open_assistant:
            self._on_open_assistant(self._raw_expression)
        elif self._api is not None:
            from setuav_studio.ui.dialog.expression_dialog import AdvancedExpressionDialog

            curr_text = self._raw_expression.strip()
            dlg = AdvancedExpressionDialog(
                api=self._api,
                initial_expression=curr_text,
                title=f"Equation Editor — {self._label}" if self._label else "Equation Editor",
                is_boolean_constraint=False,
                parent=self.window(),
            )
            if dlg.exec():
                from setuav_studio.model.expression import normalize_equation_input

                new_expr = normalize_equation_input(dlg.get_expression())
                self.setText(new_expr)
                self._call_on_changed(new_expr)

    def text(self) -> str:
        return self._raw_expression

    def setText(self, text: str) -> None:
        self._raw_expression = str(text)
        self._refresh_display()

    def value(self) -> float:
        clean = self._raw_expression.strip()
        if self._is_formula(clean):
            ok, val, _ = self._evaluate_expression(clean)
            if ok and isinstance(val, (int, float)):
                return float(val)
        try:
            return float(clean)
        except ValueError:
            return 0.0

    def setValue(self, val: float | str) -> None:
        self.setText(str(val))
        self._call_on_changed(str(val))

    def suffix(self) -> str:
        from setuav_studio.units import get_unit_manager

        if self._quantity:
            return f" {get_unit_manager().get_unit_symbol(self._quantity)}"
        return f" {self._suffix}" if self._suffix else ""

    def setSuffix(self, suffix: str) -> None:
        self._suffix = suffix.strip()
        self._refresh_display()

    def setRange(self, min_v: float, max_v: float) -> None:
        pass

    def setSingleStep(self, step: float) -> None:
        pass


class PropertyTableMixin:
    """Provides the standard property table helpers to QWidget subclasses."""

    table_headers: tuple[str, str] = ("Property", "Value")
    table_edit_triggers: QAbstractItemView.EditTrigger = (
        QAbstractItemView.EditTrigger.DoubleClicked
        | QAbstractItemView.EditTrigger.EditKeyPressed
        | QAbstractItemView.EditTrigger.SelectedClicked
    )
    table_value_placeholder: str = ""
    table_value_editable_default: bool = True
    table_combo_cls: type[QComboBox] = QComboBox
    table_combo_strict_find: bool = False
    table_max_visible_rows: int | None = 15
    table_scroll_policy_off: bool = False
    table_property_text_spinbox: bool = False

    @classmethod
    def _property_table(
        cls,
        definitions: list[tuple[str, str]],
    ) -> QTableWidget:
        table = cls._table(list(cls.table_headers))
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        if cls.table_scroll_policy_off:
            table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setEditTriggers(cls.table_edit_triggers)
        cls._configure_property_table(table, definitions)
        return table

    @classmethod
    def _configure_property_table(
        cls,
        table: QTableWidget,
        definitions: list[tuple[str, str]],
    ) -> None:
        for row in range(table.rowCount()):
            widget = table.cellWidget(row, 1)
            if widget is not None:
                table.removeCellWidget(row, 1)
                widget.deleteLater()
        table.clearContents()
        table.setRowCount(len(definitions))
        if table.columnCount() < 2:
            table.setColumnCount(2)
            table.setHorizontalHeaderLabels(list(cls.table_headers))
        for row, (key, label) in enumerate(definitions):
            label_item = QTableWidgetItem(label)
            label_item.setData(Qt.ItemDataRole.UserRole, key)
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 0, label_item)
            val_item = QTableWidgetItem(cls.table_value_placeholder)
            if cls.table_value_editable_default:
                val_item.setFlags(val_item.flags() | Qt.ItemFlag.ItemIsEditable)
            else:
                val_item.setFlags(val_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 1, val_item)
        cls._fit_table_height(table, len(definitions))

    def _set_property_combo(
        self,
        table: QTableWidget,
        key: str,
        value: str,
        options: Sequence[tuple[str, str] | str],
        on_changed: Callable[[str], Any],
    ) -> None:
        for row in range(table.rowCount()):
            if self._property_key(table, row) != key:
                continue
            self._set_table_combo(
                table,
                row,
                1,
                value,
                options,
                on_changed,
            )
            return

    @classmethod
    def _set_table_combo(
        cls,
        table: QTableWidget,
        row: int,
        column: int,
        value: str,
        options: Sequence[tuple[str, str] | str],
        on_changed: Callable[[str], Any],
    ) -> None:
        item = table.item(row, column)
        if item is not None:
            item.setText("")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        combo = cls.table_combo_cls(table)
        combo.setFont(QApplication.font())
        combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        combo.view().setProperty("tableComboPopup", True)
        combo.view().setFont(QApplication.font())
        for opt in options:
            if isinstance(opt, tuple) and len(opt) == 2:
                option_value, label = opt
            else:
                option_value, label = str(opt), str(opt)
            combo.addItem(label, option_value)
        if cls.table_combo_strict_find:
            index = combo.findData(value)
            if index >= 0:
                combo.setCurrentIndex(index)
        else:
            combo.setCurrentIndex(max(combo.findData(value), 0))
        combo.currentIndexChanged.connect(
            lambda _index, editor=combo, callback=on_changed: callback(str(editor.currentData()))
        )
        table.setCellWidget(row, column, combo)

    def _set_property_color(
        self,
        table: QTableWidget,
        key: str,
        value: Any,
        on_changed: Callable[[str], Any] | None = None,
        label: str = "",
    ) -> Any:
        for row in range(table.rowCount()):
            if self._property_key(table, row) != key:
                continue
            col0_item = table.item(row, 0)
            resolved_label = label or (col0_item.text() if col0_item else key)
            return self._set_table_color(
                table,
                row,
                1,
                value,
                on_changed=on_changed,
                label=resolved_label,
            )
        return None

    @classmethod
    def _set_table_color(
        cls,
        table: QTableWidget,
        row: int,
        column: int,
        value: Any,
        on_changed: Callable[[str], Any] | None = None,
        label: str = "",
    ) -> Any:
        from setuav_studio.ui.widget.color_picker import ColorPickerWidget

        item = table.item(row, column)
        if item is not None:
            item.setText("")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        picker = ColorPickerWidget(
            initial_color=value,
            on_changed=on_changed,
            label=label,
            parent=table,
        )
        table.setCellWidget(row, column, picker)
        return picker

    @classmethod
    def _set_property_value(
        cls,
        table: QTableWidget,
        key: str,
        value: object,
        *,
        editable: bool | None = None,
    ) -> None:
        if editable is None:
            editable = cls.table_value_editable_default
        for row in range(table.rowCount()):
            if cls._property_key(table, row) != key:
                continue
            item = table.item(row, 1)
            if item is None:
                item = QTableWidgetItem()
                table.setItem(row, 1, item)
            item.setText(str(value))
            if editable:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            return

    def _set_property_spinbox(
        self,
        table: QTableWidget,
        key: str,
        value: float | str,
        *,
        min_val: float = -1e6,
        max_val: float = 1e6,
        step: float = 1.0,
        decimals: int = 2,
        suffix: str = "",
        quantity: str | None = None,
        unit: str | None = None,
        expression: str | None = None,
        target_data: dict[str, Any] | None = None,
        on_changed: Callable[[Any], Any] | None = None,
        on_open_assistant: Callable[[str], None] | None = None,
        raw_callback: bool = False,
        api: Any | None = None,
        label: str = "",
        read_only: bool = False,
    ) -> Any:
        if target_data is None:
            resolved: Any = None
            _get_target = getattr(self, "_get_property_target_data", None)
            _target = getattr(self, "_target_data", None)
            _get = getattr(self, "_get_data", None)
            _geom = getattr(self, "_geometry", None)
            _params = getattr(self, "_parameters", None)
            _comp = getattr(self, "_component", None)

            if callable(_get_target):
                resolved = _get_target()
            elif isinstance(_target, dict):
                resolved = _target
            elif callable(_get):
                resolved = _get()
            elif callable(_geom):
                resolved = _geom()
            elif callable(_params):
                resolved = _params()
            elif isinstance(_params, dict):
                resolved = _params
            elif isinstance(_comp, dict):
                resolved = _comp.get("parameters")

            if isinstance(resolved, dict):
                target_data = resolved

        for row in range(table.rowCount()):
            if self._property_key(table, row) != key:
                continue
            from setuav_studio.ui.widget.spinbox import set_table_spinbox

            resolved_label = label
            if not resolved_label:
                col0_item = table.item(row, 0)
                resolved_label = col0_item.text() if col0_item else key

            cell = set_table_spinbox(
                table,
                row,
                1,
                value,
                min_val=min_val,
                max_val=max_val,
                step=step,
                decimals=decimals,
                suffix=suffix,
                quantity=quantity,
                unit=unit,
                expression=expression,
                target_data=target_data,
                property_key=key,
                on_changed=on_changed,
                on_open_assistant=on_open_assistant,
                raw_callback=raw_callback,
                api=api or getattr(self, "_api", None),
                label=resolved_label,
            )
            if read_only:
                cell.setReadOnly(True)
            return cell
        return None

    def _bind_single_parametric_field(
        self,
        table: QTableWidget,
        f: ParameterField,
        target_data: dict[str, Any],
        on_changed: ParameterChanged,
        resolved_api: Any,
    ) -> None:
        val = target_data.get(f.key, f.default)
        numeric = f.field_type in (float, int)

        def number_changed(text: str) -> None:
            if not text.strip() and f.optional:
                on_changed(f.key, None, None)
                return
            parsed = evaluate_table_cell_input(
                text,
                resolved_api,
                cell=self._property_cell(table, f.key),
                label=f.label,
                min_val=f.min_value,
                max_val=f.max_value,
            )
            if parsed is None:
                return
            number, expression = parsed
            on_changed(f.key, round(number) if f.field_type is int else number, expression)

        def _bind_numeric(*, read_only: bool) -> None:
            self._set_property_spinbox(
                table,
                f.key,
                val,
                min_val=f.min_value if f.min_value is not None else -1e6,
                max_val=f.max_value if f.max_value is not None else 1e6,
                step=f.step if f.step is not None else 1.0,
                decimals=0 if f.field_type is int else f.decimals,
                suffix=f.unit,
                quantity=f.quantity,
                unit=f.unit,
                target_data=target_data,
                on_changed=None if read_only else number_changed,
                raw_callback=True,
                api=resolved_api,
                label=f.label,
                read_only=read_only,
            )

        if f.readonly and numeric:
            _bind_numeric(read_only=True)
        elif f.readonly:
            unit_str = f" {f.unit}" if f.unit else ""
            disp_str = f"{val}{unit_str}" if isinstance(val, (int, float, str)) else str(val)
            self._set_property_value(table, f.key, disp_str, editable=False)
        elif f.widget_type == "color":
            self._set_property_color(
                table,
                f.key,
                val,
                lambda new_v, k=f.key: on_changed(k, new_v, None),
                label=f.label,
            )
        elif f.options:
            self._set_property_combo(
                table,
                f.key,
                str(val),
                list(f.options),
                lambda new_v, k=f.key: on_changed(k, new_v, None),
            )
        elif f.field_type is bool:
            bool_opts = [("true", "True"), ("false", "False")]
            self._set_property_combo(
                table,
                f.key,
                "true" if val else "false",
                bool_opts,
                lambda new_v, k=f.key: on_changed(k, new_v == "true", None),
            )
        elif numeric:
            _bind_numeric(read_only=False)
        else:
            self._set_property_value(table, f.key, val, editable=True)

    def bind_parametric_properties(
        self,
        table: QTableWidget,
        target_data: dict[str, Any],
        fields: Sequence[ParameterField],
        *,
        on_changed: ParameterChanged,
        api: Any | None = None,
    ) -> None:
        """Bind parameter fields to the rows of a property table.

        A numeric cell accepts a number or an '=' formula. It is evaluated here,
        and ``on_changed(key, value, expression)`` receives the number and the
        formula (None for a plain number or a non-numeric field); the caller
        stores both, the formula with ``set_expression``. An emptied optional
        field gives ``(key, None, None)``. The cells show the formulas stored in
        ``target_data['_expressions']``.
        """
        if table.rowCount() != len(fields):
            self._configure_property_table(table, [(f.key, f.label) for f in fields])

        resolved_api = api or getattr(self, "_api", None)
        for f in fields:
            self._bind_single_parametric_field(table, f, target_data, on_changed, resolved_api)

    def _set_property_expression(
        self,
        table: QTableWidget,
        key: str,
        value: object,
        on_changed: Callable[[Any], None] | None = None,
        on_open_assistant: Callable[[str], None] | None = None,
        api: Any | None = None,
        label: str = "",
        decimals: int | None = None,
        quantity: str | None = None,
        unit: str | None = None,
        target_data: dict[str, Any] | None = None,
        raw_callback: bool = False,
    ) -> None:
        self._set_property_spinbox(
            table,
            key,
            value if isinstance(value, (int, float, str)) else str(value or ""),
            decimals=decimals or 2,
            quantity=quantity,
            unit=unit,
            target_data=target_data,
            on_changed=on_changed,
            on_open_assistant=on_open_assistant,
            raw_callback=raw_callback,
            api=api,
            label=label,
        )

    @staticmethod
    def _property_key(table: QTableWidget, row: int) -> str:
        item = table.item(row, 0)
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    @classmethod
    def _property_cell(cls, table: QTableWidget, key: str) -> ExpressionPropertyCell | None:
        """Return the ExpressionPropertyCell in column 1 matching property key, if any."""
        for row in range(table.rowCount()):
            if cls._property_key(table, row) == key:
                widget = table.cellWidget(row, 1)
                if isinstance(widget, ExpressionPropertyCell):
                    return widget
        return None

    @classmethod
    def _property_text(cls, table: QTableWidget, row: int) -> str:
        editor = table.cellWidget(row, 1)
        if isinstance(editor, QComboBox):
            return str(editor.currentData())
        if isinstance(editor, ExpressionPropertyCell):
            return editor.text()
        from setuav_studio.ui.widget.color_picker import ColorPickerWidget

        if isinstance(editor, ColorPickerWidget):
            return editor.text()
        if cls.table_property_text_spinbox and isinstance(editor, QDoubleSpinBox):
            return str(editor.value())
        item = table.item(row, 1)
        return item.text() if item is not None else ""

    @classmethod
    def _property_value(cls, table: QTableWidget, key: str) -> str:
        for row in range(table.rowCount()):
            if cls._property_key(table, row) == key:
                return cls._property_text(table, row).strip()
        return ""

    @classmethod
    def _property_numeric(cls, table: QTableWidget, key_or_row: str | int) -> float | None:
        row = key_or_row if isinstance(key_or_row, int) else -1
        if isinstance(key_or_row, str):
            for r in range(table.rowCount()):
                if cls._property_key(table, r) == key_or_row:
                    row = r
                    break
        if row < 0 or row >= table.rowCount():
            return None
        editor = table.cellWidget(row, 1)
        if isinstance(editor, ExpressionPropertyCell):
            return editor.value()
        if isinstance(editor, QDoubleSpinBox):
            return float(editor.value())
        txt = cls._property_text(table, row)
        return cls._parse_number(txt)

    @staticmethod
    def _parse_number(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if not isinstance(value, str):
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        text = value.strip()
        try:
            return float(text)
        except ValueError:
            tokens = text.split()
            if tokens:
                try:
                    return float(tokens[0])
                except ValueError:
                    pass
            return None

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.horizontalHeader().setFixedHeight(23)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        return table

    @classmethod
    def _fit_table_height(
        cls,
        table: QTableWidget,
        row_count: int,
        maximum_visible_rows: int | None = None,
    ) -> None:
        if maximum_visible_rows is None:
            maximum_visible_rows = cls.table_max_visible_rows
        if maximum_visible_rows is None:
            visible_rows = max(row_count, 1)
        else:
            visible_rows = min(max(row_count, 1), maximum_visible_rows)
        height = (
            table.horizontalHeader().height()
            + table.verticalHeader().defaultSectionSize() * visible_rows
            + 2
        )
        table.setFixedHeight(height)
