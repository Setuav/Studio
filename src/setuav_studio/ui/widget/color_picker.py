"""Reusable, theme-aware ColorPickerWidget for property tables and parameter forms."""

from __future__ import annotations

import re
import weakref
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from setuav_studio.ui.widget.table import FocusAwareLineEdit


def parse_color(value: Any) -> QColor | None:
    """Parse various color representations into a valid QColor.

    Supports:
    - QColor instances
    - Hex strings: '#RRGGBB', '#RGB', '#RRGGBBAA'
    - CSS rgb/rgba: 'rgb(255, 128, 0)', 'rgba(255, 128, 0, 1.0)'
    - Comma/whitespace separated integers or floats: '255, 128, 0', '0.3, 0.6, 0.9'
    - Tuples/lists: (255, 128, 0), [0.3, 0.6, 0.9]
    - Named colors: 'red', 'blue', etc.
    """
    if isinstance(value, QColor):
        return value if value.isValid() else None

    if isinstance(value, (tuple, list)) and len(value) >= 3:
        try:
            vals = [float(v) for v in value[:4]]
            # Distinguish 0.0-1.0 floats from 0-255 integers
            if any(v > 1.0 for v in vals[:3]):
                r = min(255, max(0, round(vals[0])))
                g = min(255, max(0, round(vals[1])))
                b = min(255, max(0, round(vals[2])))
                a = min(255, max(0, round(vals[3]))) if len(vals) >= 4 else 255
            else:
                r = min(255, max(0, round(vals[0] * 255.0)))
                g = min(255, max(0, round(vals[1] * 255.0)))
                b = min(255, max(0, round(vals[2] * 255.0)))
                a = min(255, max(0, round(vals[3] * 255.0))) if len(vals) >= 4 else 255
            color = QColor(r, g, b, a)
            return color if color.isValid() else None
        except (ValueError, TypeError):
            return None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None

        # Hex format
        if text.startswith("#"):
            color = QColor(text)
            if color.isValid():
                return color

        # rgb(...) or rgba(...) format
        if text.lower().startswith("rgb"):
            left_paren = text.find("(")
            right_paren = text.rfind(")")
            if left_paren != -1 and right_paren != -1:
                text = text[left_paren + 1 : right_paren]

        # Comma, semicolon, or whitespace separated numbers
        clean = text.strip("()[]")
        parts = [p.strip() for p in re.split(r"[,;\s]+", clean) if p.strip()]
        if len(parts) >= 3:
            try:
                nums = [float(p) for p in parts]
                return parse_color(nums)
            except ValueError:
                pass

        # Named color
        color = QColor(text)
        if color.isValid():
            return color

    return None


def color_to_rgb_str(color: QColor) -> str:
    """Format QColor as standard 'r, g, b' string."""
    return f"{color.red()}, {color.green()}, {color.blue()}"


def color_to_hex_str(color: QColor) -> str:
    """Format QColor as '#RRGGBB' uppercase hex string."""
    return color.name().upper()


class ColorPickerWidget(QWidget):
    """Compact property-editor color picker with preview swatch and RGB text editing."""

    colorChanged = Signal(str)

    def __init__(
        self,
        initial_color: Any = "74, 144, 226",
        on_changed: Callable[[str], None] | None = None,
        label: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        if callable(on_changed):
            try:
                self._on_changed: Any = weakref.WeakMethod(on_changed)
            except TypeError:
                self._on_changed = on_changed
        else:
            self._on_changed = None
        parsed = parse_color(initial_color)
        self._current_color: QColor = parsed if parsed is not None else QColor(74, 144, 226)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.swatch_button = QPushButton(self)
        self.swatch_button.setFixedSize(24, 20)
        self.swatch_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swatch_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.swatch_button.clicked.connect(self._open_color_dialog)
        layout.addWidget(self.swatch_button)

        self.line_edit = FocusAwareLineEdit(self)
        self.line_edit.setPlaceholderText("R, G, B or #HEX")
        self.line_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.line_edit.returnPressed.connect(self._commit_text)
        self.line_edit.focused_out.connect(self._commit_text)
        self.line_edit.textEdited.connect(self._on_text_edited)
        layout.addWidget(self.line_edit, 1)

        self._update_display(notify=False)

    def _open_color_dialog(self) -> None:
        """Open the native QColorDialog to pick a color visually or via sliders."""
        title = f"Select Color — {self._label}" if self._label else "Select Color"
        dlg = QColorDialog(self._current_color, self.window())
        dlg.setWindowTitle(title)
        if dlg.exec():
            selected = dlg.selectedColor()
            if selected.isValid():
                self.set_color(selected, notify=True)

    def _commit_text(self) -> None:
        """Parse the input in the line edit and update color state."""
        text = self.line_edit.text().strip()
        parsed = parse_color(text)
        if parsed is not None:
            self.set_color(parsed, notify=True)
        else:
            self._update_display(notify=False)

    def _on_text_edited(self, text: str) -> None:
        """Provide real-time visual feedback on the swatch while typing."""
        parsed = parse_color(text)
        if parsed is not None:
            self._apply_swatch_style(parsed)

    def _apply_swatch_style(self, color: QColor) -> None:
        r, g, b = color.red(), color.green(), color.blue()
        self.swatch_button.setStyleSheet(
            f"QPushButton {{ background-color: rgb({r}, {g}, {b}); "
            f"border: 1px solid #555; border-radius: 3px; }} "
            f"QPushButton:hover {{ border: 1px solid #aaa; }}"
        )

    def _update_display(self, notify: bool = False) -> None:
        self._apply_swatch_style(self._current_color)
        rgb_text = color_to_rgb_str(self._current_color)
        hex_text = color_to_hex_str(self._current_color)
        tip = f"RGB: ({rgb_text}) | Hex: {hex_text}"

        self.swatch_button.setToolTip(f"Click to pick color\n{tip}")
        self.line_edit.blockSignals(True)
        self.line_edit.setText(rgb_text)
        self.line_edit.setToolTip(tip)
        self.line_edit.blockSignals(False)

        if notify:
            self._notify_changed(rgb_text)

    def _notify_changed(self, rgb_text: str) -> None:
        self.colorChanged.emit(rgb_text)
        if self._on_changed is not None:
            cb = (
                self._on_changed()
                if isinstance(self._on_changed, (weakref.WeakMethod, weakref.ReferenceType))
                else self._on_changed
            )
            if cb is not None:
                cb(rgb_text)

    def set_color(self, color: Any, notify: bool = True) -> None:
        """Set the active color from a QColor, string, or sequence."""
        parsed = parse_color(color)
        if parsed is not None:
            changed = parsed != self._current_color
            self._current_color = parsed
            self._update_display(notify=notify and changed)

    def color(self) -> QColor:
        """Get the current QColor."""
        return self._current_color

    def rgb_tuple(self) -> tuple[int, int, int]:
        """Get the current RGB values as an (r, g, b) integer tuple."""
        return (self._current_color.red(), self._current_color.green(), self._current_color.blue())

    def rgb_text(self) -> str:
        """Get the current RGB string formatted as 'r, g, b'."""
        return color_to_rgb_str(self._current_color)

    def hex_text(self) -> str:
        """Get the current uppercase hex string '#RRGGBB'."""
        return color_to_hex_str(self._current_color)

    # Standard property editor widget interfaces
    def text(self) -> str:
        return self.rgb_text()

    def setText(self, text: str) -> None:
        self.set_color(text, notify=False)

    def value(self) -> str:
        return self.rgb_text()

    def setValue(self, val: Any) -> None:
        self.set_color(val, notify=True)
