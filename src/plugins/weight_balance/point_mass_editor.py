"""Properties editor for point-mass components."""

from __future__ import annotations

import weakref
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
from setuav_studio.ui.widget.spinbox import set_table_spinbox
from setuav_studio.ui.widget.table import PropertyTableMixin
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
        content = QWidget()
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
        section = QWidget()
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
        layout = self._create_section("Mass", "mass")
        self.mass_table = self._property_table([("mass", "Mass")])
        layout.addWidget(self.mass_table)

    def _create_transform_section(self) -> None:
        layout = self._create_section("Transform", "transform")
        self.transform_table = QTableWidget(2, 3)
        self.transform_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.transform_table.setVerticalHeaderLabels(["Position", "Rotation"])
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
            axis: self._spin(
                row=0,
                column=column,
                minimum=-1e9,
                maximum=1e9,
                quantity="length",
                suffix="mm",
                axis=axis,
                label=f"Position {axis.upper()}",
            )
            for column, axis in enumerate(("x", "y", "z"))
        }
        self.rotation_spins = {
            axis: self._spin(
                row=1,
                column=column,
                minimum=-360.0,
                maximum=360.0,
                quantity="angle",
                suffix="°",
                axis=axis,
                label=f"Rotation {axis.title()}",
            )
            for column, axis in enumerate(("roll", "pitch", "yaw"))
        }
        layout.addWidget(self.transform_table)

    def _transform(self) -> dict[str, Any]:
        tf = self._component.get("transform")
        if not isinstance(tf, dict):
            tf = {}
            self._component["transform"] = tf
        return tf

    def _position(self) -> dict[str, Any]:
        tf = self._transform()
        pos = tf.get("position")
        if not isinstance(pos, dict):
            pos = {}
            tf["position"] = pos
        return pos

    def _rotation(self) -> dict[str, Any]:
        tf = self._transform()
        rot = tf.get("rotation")
        if not isinstance(rot, dict):
            rot = {}
            tf["rotation"] = rot
        return rot

    def _spin(
        self,
        row: int,
        column: int,
        minimum: float,
        maximum: float,
        quantity: str,
        suffix: str,
        axis: str,
        label: str = "",
    ) -> Any:
        self_ref = weakref.ref(self)
        target_dict = self._position() if row == 0 else self._rotation()
        return set_table_spinbox(
            self.transform_table,
            row,
            column,
            0.0,
            min_val=minimum,
            max_val=maximum,
            step=1.0,
            decimals=2,
            quantity=quantity,
            suffix=suffix,
            target_data=target_dict,
            property_key=axis,
            on_changed=lambda _value: (
                self_ref()._transform_changed() if self_ref() is not None else None
            ),
            api=self._api,
            label=label,
        )

    def _load_component(self) -> None:
        self._loading = True
        try:
            params = self._component.setdefault("parameters", {})
            mass_val = float(self._component.get("mass", params.get("mass", 0.0)))
            self._set_property_spinbox(
                self.mass_table,
                "mass",
                mass_val,
                min_val=0.0,
                max_val=1e8,
                step=10.0,
                decimals=1,
                unit="g",
                target_data=params,
                on_changed=self._on_mass_changed,
                label="Mass",
            )
            pos = self._position()
            rot = self._rotation()
            for axis, spin in self.position_spins.items():
                val = pos.get(axis, 0.0)
                spin.setValue(val)
            for axis, spin in self.rotation_spins.items():
                val = rot.get(axis, 0.0)
                spin.setValue(val)
        finally:
            self._loading = False

    def _on_mass_changed(self, value: Any) -> None:
        if self._loading:
            return
        try:
            num_val = float(value)
        except (ValueError, TypeError):
            return

        def change() -> None:
            self._component["mass"] = num_val
            self._component.setdefault("parameters", {})["mass"] = num_val

        self._api.edit_component(self._component, "Edit point mass", change)

    def _transform_changed(self) -> None:
        if self._loading:
            return
        position = {axis: spin.value() for axis, spin in self.position_spins.items()}
        rotation = {axis: spin.value() for axis, spin in self.rotation_spins.items()}

        def change() -> None:
            pos = self._position()
            pos.update(position)
            rot = self._rotation()
            rot.update(rotation)

        self._api.edit_component(self._component, "Edit point mass transform", change)

    def update_theme_style(self) -> None:
        for label, icon_name in self._section_icons:
            set_label_icon(label, icon_name)


def _number(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
