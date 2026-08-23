"""Shared component-level transform editor."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.numeric_spinbox import NumericSpinBox, set_table_spinbox
from setuav_studio.ui.property_tables import PropertyTableMixin


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

        content = QWidget(self)
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
        layout = self._create_section("Reference Frame", "mdi6.axis-arrow")
        self.reference_table = self._property_table([
            ("component", "Component"),
            ("parent", "Parent Frame"),
        ])
        layout.addWidget(self.reference_table)

    def _create_transform_section(self) -> None:
        layout = self._create_section("Transform", "mdi6.axis-arrow")
        self.transform_table = QTableWidget(2, 3, self)
        self.transform_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.transform_table.setVerticalHeaderLabels(
            ["Position (mm)", "Rotation (°)"]
        )
        self.transform_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.transform_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectItems
        )
        self.transform_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.transform_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.transform_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.transform_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.transform_table.horizontalHeader().setFixedHeight(23)
        self.transform_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
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
                suffix="°",
            )
            for column, axis in enumerate(("roll", "pitch", "yaw"))
        }
        layout.addWidget(self.transform_table)

    def _set_transform_spin(
        self,
        *,
        row: int,
        column: int,
        minimum: float,
        maximum: float,
        step: float,
        decimals: int,
        suffix: str,
    ) -> NumericSpinBox:
        return set_table_spinbox(
            self.transform_table,
            row,
            column,
            0.0,
            min_val=minimum,
            max_val=maximum,
            step=step,
            decimals=decimals,
            suffix=suffix,
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

            transform = component.get("transform")
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

    def _update_transform(self) -> None:
        if self._loading or self._component is None:
            return
        position = {
            axis: spin.value() for axis, spin in self.position_spins.items()
        }
        rotation = {
            axis: spin.value() for axis, spin in self.rotation_spins.items()
        }

        def change() -> None:
            self._component["transform"] = {
                "position": position,
                "rotation": rotation,
            }

        self._api.edit_component(
            self._component,
            f"Edit transform of {self._component.get('name') or 'component'}",
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
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
