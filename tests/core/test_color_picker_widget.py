"""Unit tests for ColorPickerWidget and color parsing utilities."""

from __future__ import annotations

import unittest

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidget, QWidget

from setuav_studio.ui.widget.color_picker import (
    ColorPickerWidget,
    color_to_hex_str,
    color_to_rgb_str,
    parse_color,
)
from setuav_studio.ui.widget.table import PropertyTableMixin
from setuav_studio_sdk import ParameterField
from tests._common import get_qapp


class DummyTableWidget(PropertyTableMixin, QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table = self._property_table([("color", "Color"), ("length", "Length")])


class ColorPickerWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = get_qapp()

    def test_parse_color(self) -> None:
        # QColor instance
        c1 = QColor(10, 20, 30)
        self.assertEqual(parse_color(c1), c1)

        # Hex strings
        c_hex = parse_color("#4A90E2")
        self.assertIsNotNone(c_hex)
        assert c_hex is not None
        self.assertEqual(c_hex.red(), 74)
        self.assertEqual(c_hex.green(), 144)
        self.assertEqual(c_hex.blue(), 226)

        c_short_hex = parse_color("#F00")
        self.assertIsNotNone(c_short_hex)
        assert c_short_hex is not None
        self.assertEqual(c_short_hex.red(), 255)
        self.assertEqual(c_short_hex.green(), 0)
        self.assertEqual(c_short_hex.blue(), 0)

        # CSS rgb(...) string
        c_rgb = parse_color("rgb(100, 150, 200)")
        self.assertIsNotNone(c_rgb)
        assert c_rgb is not None
        self.assertEqual((c_rgb.red(), c_rgb.green(), c_rgb.blue()), (100, 150, 200))

        # Comma-separated integers string
        c_csv = parse_color("255, 128, 64")
        self.assertIsNotNone(c_csv)
        assert c_csv is not None
        self.assertEqual((c_csv.red(), c_csv.green(), c_csv.blue()), (255, 128, 64))

        # Tuple / list of integers
        c_tuple = parse_color((50, 100, 150))
        self.assertIsNotNone(c_tuple)
        assert c_tuple is not None
        self.assertEqual((c_tuple.red(), c_tuple.green(), c_tuple.blue()), (50, 100, 150))

        # Tuple of normalized floats
        c_floats = parse_color((0.0, 1.0, 0.5))
        self.assertIsNotNone(c_floats)
        assert c_floats is not None
        self.assertEqual((c_floats.red(), c_floats.green(), c_floats.blue()), (0, 255, 128))

        # Invalid strings
        self.assertIsNone(parse_color("not_a_color_xyz"))
        self.assertIsNone(parse_color(""))
        self.assertIsNone(parse_color(None))

    def test_color_to_strings(self) -> None:
        c = QColor(74, 144, 226)
        self.assertEqual(color_to_rgb_str(c), "74, 144, 226")
        self.assertEqual(color_to_hex_str(c), "#4A90E2")

    def test_color_picker_widget_initialization_and_set_color(self) -> None:
        changes: list[str] = []
        picker = ColorPickerWidget(
            initial_color="#4A90E2",
            on_changed=changes.append,
            label="Surface Color",
        )

        self.assertEqual(picker.rgb_text(), "74, 144, 226")
        self.assertEqual(picker.hex_text(), "#4A90E2")
        self.assertEqual(picker.rgb_tuple(), (74, 144, 226))
        self.assertEqual(picker.text(), "74, 144, 226")
        self.assertEqual(picker.value(), "74, 144, 226")
        self.assertIn("74, 144, 226", picker.swatch_button.styleSheet())

        # Change color programmatically
        picker.set_color("255, 0, 0")
        self.assertEqual(picker.rgb_text(), "255, 0, 0")
        self.assertEqual(picker.rgb_tuple(), (255, 0, 0))
        self.assertEqual(changes, ["255, 0, 0"])

    def test_color_picker_widget_text_editing(self) -> None:
        changes: list[str] = []
        picker = ColorPickerWidget(
            initial_color="74, 144, 226",
            on_changed=changes.append,
        )

        # Simulate typing valid RGB string
        picker.line_edit.setText("0, 128, 255")
        picker._commit_text()
        self.assertEqual(picker.rgb_text(), "0, 128, 255")
        self.assertEqual(changes[-1], "0, 128, 255")

        # Simulate typing hex string
        picker.line_edit.setText("#FF8000")
        picker._commit_text()
        self.assertEqual(picker.rgb_text(), "255, 128, 0")
        self.assertEqual(changes[-1], "255, 128, 0")

        # Simulate typing invalid string -> reverts
        picker.line_edit.setText("invalid")
        picker._commit_text()
        self.assertEqual(picker.rgb_text(), "255, 128, 0")

    def test_property_table_integration(self) -> None:
        dummy = DummyTableWidget()
        changes: list[str] = []

        dummy._set_property_color(
            dummy.table,
            "color",
            "74, 144, 226",
            on_changed=changes.append,
            label="Surface Color",
        )

        # Verify cell widget is ColorPickerWidget
        cell_widget = dummy.table.cellWidget(0, 1)
        self.assertIsInstance(cell_widget, ColorPickerWidget)
        assert isinstance(cell_widget, ColorPickerWidget)
        self.assertEqual(cell_widget.text(), "74, 144, 226")

        # Verify PropertyTableMixin._property_text reads ColorPickerWidget
        self.assertEqual(dummy._property_text(dummy.table, 0), "74, 144, 226")
        self.assertEqual(dummy._property_value(dummy.table, "color"), "74, 144, 226")

        # Update via widget
        cell_widget.set_color("200, 100, 50")
        self.assertEqual(changes, ["200, 100, 50"])
        self.assertEqual(dummy._property_text(dummy.table, 0), "200, 100, 50")

    def test_bind_parametric_properties_with_color_field(self) -> None:
        table = QTableWidget()
        target_data = {"color": "100, 200, 50", "length": 150.0}
        fields = [
            ParameterField(
                key="color",
                label="Surface Color",
                field_type=str,
                default="74, 144, 226",
                widget_type="color",
            ),
            ParameterField(key="length", label="Length", default=100.0),
        ]

        mixin = DummyTableWidget()
        on_changed_calls: list[tuple[str, str]] = []
        mixin.bind_parametric_properties(
            table,
            target_data,
            fields,
            on_changed=lambda k, v: on_changed_calls.append((k, v)),
        )

        self.assertEqual(table.rowCount(), 2)
        color_widget = table.cellWidget(0, 1)
        self.assertIsInstance(color_widget, ColorPickerWidget)
        assert isinstance(color_widget, ColorPickerWidget)
        self.assertEqual(color_widget.text(), "100, 200, 50")

        # Edit color
        color_widget.set_color("10, 20, 30")
        self.assertEqual(target_data["color"], "10, 20, 30")
        self.assertEqual(on_changed_calls, [("color", "10, 20, 30")])


if __name__ == "__main__":
    unittest.main()
