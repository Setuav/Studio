"""Shared component-level transform editor."""

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

from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.spinbox import NumericSpinBox, set_table_spinbox
from setuav_studio.ui.widget.table import PropertyTableMixin
from setuav_studio_sdk import StudioAPI


class TransformEditor(PropertyTableMixin, QWidget):
    """Edit a component's parent-relative position and rotation."""

    table_edit_triggers = QAbstractItemView.EditTrigger.NoEditTriggers
    table_value_placeholder = "-"
    table_value_editable_default = False

    def __init__(
        self,
        api: StudioAPI,
        selection: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("core.transform_editor")
        self._api = api
        component_id = str(selection.get("component_id") or "")
        self._component = (
            api.current_project.get_component(component_id)
            if api.current_project is not None and component_id
            else None
        )
        self._loading = False
        self._section_icons: list[tuple[QLabel, str]] = []

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._content_layout.setContentsMargins(6, 6, 6, 8)
        self._content_layout.setSpacing(10)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        root_layout.addWidget(scroll)

        self._create_reference_section()
        self._create_transform_section()
        self._content_layout.addStretch(1)

        if self._component is not None:
            self._load_component(self._component)
        else:
            self._set_enabled(False)

    def update_theme_style(self) -> None:
        for label, icon_name in self._section_icons:
            set_label_icon(label, icon_name)

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
        header_layout.setSpacing(5)

        icon_label = QLabel(header)
        set_label_icon(icon_label, icon_name)
        icon_label.setFixedSize(14, 14)
        self._section_icons.append((icon_label, icon_name))
        header_layout.addWidget(icon_label)
        header_layout.addWidget(QLabel(title, header))
        header_layout.addStretch(1)

        layout.addWidget(header)
        self._content_layout.addWidget(section)
        return layout

    def _create_reference_section(self) -> None:
        layout = self._create_section("Reference Frame", "transform")
        self.reference_table = self._property_table(
            [
                ("component", "Component"),
                ("parent", "Parent Frame"),
            ]
        )
        layout.addWidget(self.reference_table)

    def _create_transform_section(self) -> None:
        layout = self._create_section("Transform", "transform")
        self.transform_table = QTableWidget(2, 3)
        self.transform_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.transform_table.setVerticalHeaderLabels(["Position", "Rotation"])
        self.transform_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.transform_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.transform_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
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
            axis: self._set_transform_spin(
                row=0,
                column=column,
                minimum=-1_000_000_000.0,
                maximum=1_000_000_000.0,
                step=1.0,
                decimals=3,
                quantity="length",
                suffix="mm",
            )
            for column, axis in enumerate(("x", "y", "z"))
        }
        self.rotation_spins = {
            axis: self._set_transform_spin(
                row=1,
                column=column,
                minimum=-360.0,
                maximum=360.0,
                step=1.0,
                decimals=3,
                quantity="angle",
                suffix="°",
            )
            for column, axis in enumerate(("roll", "pitch", "yaw"))
        }
        layout.addWidget(self.transform_table)

    def _transform(self) -> dict[str, Any]:
        if self._component is None:
            return {}
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

    def _set_transform_spin(
        self,
        *,
        row: int,
        column: int,
        minimum: float,
        maximum: float,
        step: float,
        decimals: int,
        quantity: str,
        suffix: str,
        target_data: dict[str, Any] | None = None,
        property_key: str | None = None,
        value: float | str = 0.0,
        label: str = "",
    ) -> NumericSpinBox:
        return set_table_spinbox(
            self.transform_table,
            row,
            column,
            value,
            min_val=minimum,
            max_val=maximum,
            step=step,
            decimals=decimals,
            quantity=quantity,
            suffix=suffix,
            target_data=target_data,
            property_key=property_key,
            api=self._api,
            label=label,
            on_changed=lambda _value: self._update_transform(),
        )

    def _load_component(self, component: dict[str, Any]) -> None:
        self._loading = True
        try:
            self._set_property_value(
                self.reference_table,
                "component",
                str(component.get("name") or component.get("id") or ""),
                editable=False,
            )
            self._set_property_value(
                self.reference_table,
                "parent",
                self._parent_frame_name(component),
                editable=False,
            )

            pos = self._position()
            rot = self._rotation()
            for col, axis in enumerate(("x", "y", "z")):
                self.position_spins[axis] = self._set_transform_spin(
                    row=0,
                    column=col,
                    minimum=-1_000_000_000.0,
                    maximum=1_000_000_000.0,
                    step=1.0,
                    decimals=3,
                    quantity="length",
                    suffix="mm",
                    target_data=pos,
                    property_key=axis,
                    value=pos.get(axis, 0.0),
                    label=f"Position {axis.upper()}",
                )
            for col, axis in enumerate(("roll", "pitch", "yaw")):
                self.rotation_spins[axis] = self._set_transform_spin(
                    row=1,
                    column=col,
                    minimum=-360.0,
                    maximum=360.0,
                    step=1.0,
                    decimals=3,
                    quantity="angle",
                    suffix="°",
                    target_data=rot,
                    property_key=axis,
                    value=rot.get(axis, 0.0),
                    label=f"Rotation {axis.title()}",
                )
        finally:
            self._loading = False

    def _update_transform(self) -> None:
        if self._loading or self._component is None:
            return
        component = self._component
        position = {axis: spin.value() for axis, spin in self.position_spins.items()}
        rotation = {axis: spin.value() for axis, spin in self.rotation_spins.items()}

        def change() -> None:
            self._position().update(position)
            self._rotation().update(rotation)

        self._api.edit_component(
            component,
            f"Edit transform of {component.get('name') or 'component'}",
            change,
        )

    def _parent_frame_name(self, component: dict[str, Any]) -> str:
        parent_id = component.get("attach_to") or component.get("parent")
        if not parent_id:
            return "SETUAV_BODY"
        project = self._api.current_project
        if project is None:
            return str(parent_id)
        parent = project.get_component(str(parent_id))
        return str(parent.get("name") or parent_id) if parent else str(parent_id)

    def _set_enabled(self, enabled: bool) -> None:
        self.reference_table.setEnabled(enabled)
        self.transform_table.setEnabled(enabled)


def _number(value: object) -> float:
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    return 0.0
