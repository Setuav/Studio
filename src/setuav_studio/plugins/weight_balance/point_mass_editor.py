"""Properties editor for point-mass components."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.numeric_spinbox import NumericSpinBox, set_table_spinbox
from setuav_studio.ui.property_tables import PropertyTableMixin
from setuav_studio_sdk import StudioAPI


class PointMassEditor(PropertyTableMixin, QWidget):
    """Edit only the mass and body transform of a point mass."""

    def __init__(
        self,
        api: StudioAPI,
        component: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("weight_balance.point_mass_editor")
        self._api = api
        self._component = component
        self._loading = False
        self._section_icons: list[tuple[QLabel, str]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        content = QWidget(self)
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(6, 6, 6, 8)
        self._content_layout.setSpacing(10)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        root.addWidget(scroll)

        self._create_mass_section()
        self._create_transform_section()
        self._content_layout.addStretch(1)
        self._load_component()

    def _create_section(self, title: str, icon_name: str) -> QVBoxLayout:
        section = QWidget(self)
        section.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        header = QWidget(section)
        header.setProperty("sectionHeader", True)
        header.setFixedHeight(20)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)
        label = QLabel(header)
        set_label_icon(label, icon_name)
        label.setFixedSize(14, 14)
        self._section_icons.append((label, icon_name))
        header_layout.addWidget(label)
        header_layout.addWidget(QLabel(title, header))
        header_layout.addStretch(1)
        layout.addWidget(header)
        self._content_layout.addWidget(section)
        return layout

    def _create_mass_section(self) -> None:
        layout = self._create_section("Mass", "fa6s.weight-scale")
        self.mass_table = self._property_table([("mass", "Mass (g)")])
        self.mass_table.cellChanged.connect(self._mass_changed)
        layout.addWidget(self.mass_table)

    def _create_transform_section(self) -> None:
        layout = self._create_section("Transform", "mdi6.axis-arrow")
        self.transform_table = QTableWidget(2, 3, self)
        self.transform_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.transform_table.setVerticalHeaderLabels(["Position (mm)", "Rotation (°)"])
        self.transform_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.transform_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.transform_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.transform_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.transform_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.transform_table.horizontalHeader().setFixedHeight(23)
        self.transform_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.transform_table.verticalHeader().setDefaultSectionSize(23)
        self.transform_table.verticalHeader().setMinimumWidth(96)
        self.transform_table.setAlternatingRowColors(True)
        self.transform_table.setFixedHeight(71)
        self.position_spins = {
            axis: self._spin(row=0, column=column, minimum=-1e9, maximum=1e9, suffix="mm")
            for column, axis in enumerate(("x", "y", "z"))
        }
        self.rotation_spins = {
            axis: self._spin(row=1, column=column, minimum=-360.0, maximum=360.0, suffix="°")
            for column, axis in enumerate(("roll", "pitch", "yaw"))
        }
        layout.addWidget(self.transform_table)

    def _spin(
        self,
        *,
        row: int,
        column: int,
        minimum: float,
        maximum: float,
        suffix: str,
    ) -> NumericSpinBox:
        return set_table_spinbox(
            self.transform_table,
            row,
            column,
            0.0,
            min_val=minimum,
            max_val=maximum,
            step=1.0,
            decimals=3,
            suffix=suffix,
            on_changed=lambda _value: self._transform_changed(),
        )

    def _load_component(self) -> None:
        self._loading = True
        try:
            params = self._component.get("parameters")
            params = params if isinstance(params, dict) else {}
            self._set_property_value(
                self.mass_table,
                "mass",
                f"{float(self._component.get('mass', params.get('mass', 0.0))):.3f}",
            )
            transform = self._component.get("transform")
            transform = transform if isinstance(transform, dict) else {}
            position = transform.get("position")
            position = position if isinstance(position, dict) else {}
            rotation = transform.get("rotation")
            rotation = rotation if isinstance(rotation, dict) else {}
            for axis, spin in self.position_spins.items():
                spin.setValue(_number(position.get(axis)))
            for axis, spin in self.rotation_spins.items():
                spin.setValue(_number(rotation.get(axis)))
        finally:
            self._loading = False

    def _mass_changed(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        value = max(0.0, self._parse_number(self._property_text(self.mass_table, row)) or 0.0)

        def change() -> None:
            self._component["mass"] = value
            self._component.setdefault("parameters", {})["mass"] = value

        self._api.edit_component(self._component, "Edit point mass", change)

    def _transform_changed(self) -> None:
        if self._loading:
            return
        position = {axis: spin.value() for axis, spin in self.position_spins.items()}
        rotation = {axis: spin.value() for axis, spin in self.rotation_spins.items()}

        def change() -> None:
            self._component["transform"] = {"position": position, "rotation": rotation}

        self._api.edit_component(self._component, "Edit point-mass transform", change)

    def update_theme_style(self) -> None:
        for label, icon_name in self._section_icons:
            set_label_icon(label, icon_name)


def _number(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
