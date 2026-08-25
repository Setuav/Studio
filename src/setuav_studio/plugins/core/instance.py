from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.icons import set_label_icon


class InstanceEditor(QWidget):
    def __init__(self, api: StudioAPI, instance: dict[str, Any]) -> None:
        super().__init__()
        self._api = api
        self._instance = instance
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 8)
        layout.setSpacing(10)

        layout.addWidget(self._header("Instance", "instance"))
        self.properties_table = self._table(["Property", "Value"])
        self.properties_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectItems
        )
        self.properties_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.properties_table.cellChanged.connect(self._update_property)
        layout.addWidget(self.properties_table)

        layout.addWidget(self._header("Transform", "mdi6.axis-arrow"))
        self.transform_table = QTableWidget(2, 3)
        self.transform_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.transform_table.setVerticalHeaderLabels(
            ["Position (mm)", "Rotation (°)"]
        )
        self.transform_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.transform_table.horizontalHeader().setFixedHeight(23)
        self.transform_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.transform_table.verticalHeader().setDefaultSectionSize(23)
        self.transform_table.verticalHeader().setMinimumWidth(82)
        self.transform_table.setAlternatingRowColors(True)
        self.transform_table.setFixedHeight(71)
        self.transform_table.cellChanged.connect(self._update_transform)
        layout.addWidget(self.transform_table)
        layout.addStretch()

        self._refresh()

    @staticmethod
    def _header(text: str, icon_name: str | None = None) -> QWidget:
        header = QWidget()
        header.setProperty("sectionHeader", True)
        header.setFixedHeight(20)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)

        if icon_name:
            icon_label = QLabel()
            set_label_icon(icon_label, icon_name)
            icon_label.setFixedSize(14, 14)
            header_layout.addWidget(icon_label)

        title_label = QLabel(text)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        return header

    def _refresh(self) -> None:
        self._loading = True
        derivation = self._mapping(self._instance, "derivation")
        derivation_type = str(derivation.get("type") or "copy")
        definitions = [
            ("name", "Name", True),
            ("id", "ID", False),
            ("source", "Source", False),
            ("parent", "Parent", False),
            ("derivation_type", "Derivation", False),
        ]
        if derivation_type == "mirror":
            definitions.extend(
                [
                    ("plane", "Mirror plane", False),
                    ("offset", "Mirror offset (mm)", True),
                ]
            )

        for row in range(self.properties_table.rowCount()):
            widget = self.properties_table.cellWidget(row, 1)
            if widget is not None:
                self.properties_table.removeCellWidget(row, 1)
                widget.deleteLater()
        self.properties_table.clearContents()
        self.properties_table.setRowCount(len(definitions))
        for row, (key, label, editable) in enumerate(definitions):
            label_item = QTableWidgetItem(label)
            label_item.setData(Qt.ItemDataRole.UserRole, key)
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.properties_table.setItem(row, 0, label_item)

            value_item = QTableWidgetItem(self._property_value(key, derivation))
            if not editable:
                value_item.setFlags(
                    value_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )
            self.properties_table.setItem(row, 1, value_item)

        self._set_combo(
            "derivation_type",
            derivation_type,
            [("copy", "Copy"), ("mirror", "Mirror")],
            self._change_derivation,
        )
        if derivation_type == "mirror":
            self._set_combo(
                "plane",
                str(derivation.get("plane") or "XZ"),
                [("XY", "XY"), ("XZ", "XZ"), ("YZ", "YZ")],
                self._change_plane,
            )
        self._fit_height(self.properties_table)
        self._set_transform_values()
        self._loading = False

    def _property_value(self, key: str, derivation: dict[str, Any]) -> str:
        if key == "source":
            return self._component_name(self._instance.get("source"))
        if key == "parent":
            parent = self._instance.get("attach_to") or self._instance.get("parent")
            return self._component_name(parent) if parent is not None else "—"
        if key == "derivation_type":
            return str(derivation.get("type") or "copy")
        if key in {"plane", "offset"}:
            return str(derivation.get(key) or ("XZ" if key == "plane" else 0))
        return str(self._instance.get(key) or "")

    def _component_name(self, component_id: object) -> str:
        identifier = str(component_id or "")
        project = self._api.current_project
        if project is not None:
            components = project.data.get("components", [])
            if isinstance(components, list):
                for component in components:
                    if not isinstance(component, dict):
                        continue
                    if str(component.get("id") or "") == identifier:
                        return str(component.get("name") or identifier)
        return identifier

    def _update_property(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._key(row)
        item = self.properties_table.item(row, column)
        value = item.text().strip() if item is not None else ""
        if key == "name":
            if not value:
                self._refresh()
                return
            self._edit(
                "Rename component instance",
                lambda: self._instance.__setitem__("name", value),
            )
            return
        if key == "offset":
            try:
                offset = float(value)
            except ValueError:
                self._refresh()
                return
            self._edit(
                "Edit mirror offset",
                lambda: self._object(self._instance, "derivation").__setitem__(
                    "offset", offset
                ),
            )

    def _change_derivation(self, value: str) -> None:
        if self._loading or value not in {"copy", "mirror"}:
            return
        derivation = (
            {"type": "copy"}
            if value == "copy"
            else {"type": "mirror", "plane": "XZ", "offset": 0.0}
        )
        self._edit(
            "Change instance derivation",
            lambda: self._instance.__setitem__("derivation", derivation),
        )

    def _change_plane(self, value: str) -> None:
        if self._loading or value not in {"XY", "XZ", "YZ"}:
            return
        self._edit(
            "Change mirror plane",
            lambda: self._object(self._instance, "derivation").__setitem__(
                "plane", value
            ),
        )

    def _set_transform_values(self) -> None:
        transform = self._mapping(self._instance, "transform")
        position = self._mapping(transform, "position")
        rotation = self._mapping(transform, "rotation")
        values = (
            (position.get("x", 0), position.get("y", 0), position.get("z", 0)),
            (
                rotation.get("roll", 0),
                rotation.get("pitch", 0),
                rotation.get("yaw", 0),
            ),
        )
        for row, row_values in enumerate(values):
            for column, value in enumerate(row_values):
                self.transform_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(str(value or 0)),
                )

    def _update_transform(self, _row: int, _column: int) -> None:
        if self._loading:
            return
        values: list[list[float]] = []
        try:
            for row in range(2):
                values.append(
                    [
                        float(self.transform_table.item(row, column).text())
                        for column in range(3)
                    ]
                )
        except (AttributeError, ValueError):
            self._refresh()
            return

        def change() -> None:
            self._instance["transform"] = {
                "position": dict(zip(("x", "y", "z"), values[0], strict=True)),
                "rotation": dict(
                    zip(("roll", "pitch", "yaw"), values[1], strict=True)
                ),
            }

        self._edit("Edit instance transform", change)

    def _edit(self, description: str, change: Callable[[], None]) -> None:
        self._api.edit_component(self._instance, description, change)
        self._refresh()

    def _set_combo(
        self,
        key: str,
        value: str,
        options: list[tuple[str, str]],
        on_changed: Callable[[str], None],
    ) -> None:
        for row in range(self.properties_table.rowCount()):
            if self._key(row) != key:
                continue
            item = self.properties_table.item(row, 1)
            if item is not None:
                item.setText("")
            combo = QComboBox(self.properties_table)
            combo.setFont(QApplication.font())
            combo.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            combo.view().setProperty("tableComboPopup", True)
            combo.view().setFont(QApplication.font())
            for option_value, label in options:
                combo.addItem(label, option_value)
            combo.setCurrentIndex(max(combo.findData(value), 0))
            combo.currentIndexChanged.connect(
                lambda _index, editor=combo, callback=on_changed: callback(
                    str(editor.currentData())
                )
            )
            self.properties_table.setCellWidget(row, 1, combo)
            return

    def _key(self, row: int) -> str:
        item = self.properties_table.item(row, 0)
        return str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""

    @staticmethod
    def _object(owner: dict[str, Any], key: str) -> dict[str, Any]:
        value = owner.get(key)
        if not isinstance(value, dict):
            value = {}
            owner[key] = value
        return value

    @staticmethod
    def _mapping(owner: dict[str, Any], key: str) -> dict[str, Any]:
        value = owner.get(key)
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.horizontalHeader().setFixedHeight(23)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        return table

    @staticmethod
    def _fit_height(table: QTableWidget) -> None:
        table.setFixedHeight(
            table.horizontalHeader().height()
            + table.verticalHeader().defaultSectionSize() * table.rowCount()
            + 2
        )
