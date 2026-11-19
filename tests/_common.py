"""Shared test helpers for setuav-studio tests."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QWidget

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

TEST_PROJECT_PATH = Path(__file__).parent / "fixtures" / "fixed-wing"


def register_fixture_component_types(api: StudioAPI) -> None:
    """Register the component types of the fixture project that its plugins provide.

    Core tests use these without activating the plugins: the core types, and the
    airframe types with control surfaces as subparts.
    """
    from setuav_studio.api import ComponentTypeContribution
    from setuav_studio.ui.shell.native_registrations import register_native_component_types

    register_native_component_types(api)
    for type_id, name, subpart in (
        ("org.setuav.core:fuselage", "Fuselage", False),
        ("org.setuav.core:lifting-surface", "Lifting Surface", False),
        ("org.setuav.core:control-surface", "Control Surface", True),
        ("org.setuav.core:propulsor", "Propulsor", False),
        ("org.setuav.core:battery", "Battery", False),
    ):
        api.register_component_type(
            ComponentTypeContribution(id=type_id, name=name, icon="component", subpart=subpart)
        )


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
