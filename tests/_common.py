"""Shared test helpers for setuav-studio tests."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QWidget

TEST_PROJECT_PATH = Path(__file__).parent / "fixtures" / "fixed-wing"


def get_qapp() -> QApplication:
    """Return the singleton QApplication, creating it if needed."""
    app = QApplication.instance()
    if app is None:
        return QApplication([])
    assert isinstance(app, QApplication)
    return app


def table_item(table: QTableWidget, row: int, column: int) -> QTableWidgetItem:
    """Return the item at ``row``/``column``, failing when the cell holds no item."""
    item = table.item(row, column)
    assert item is not None, f"no table item at ({row}, {column})"
    return item


def cell_widget[W: QWidget](table: QTableWidget, row: int, column: int, widget_type: type[W]) -> W:
    """Return the cell widget at ``row``/``column``, failing unless it is a ``widget_type``."""
    widget = table.cellWidget(row, column)
    assert isinstance(widget, widget_type), (
        f"cell ({row}, {column}) holds {type(widget).__name__}, expected {widget_type.__name__}"
    )
    return widget
