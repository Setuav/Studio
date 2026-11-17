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

from setuav_studio.api import StudioAPI
from setuav_studio.model.expression import set_expression
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.spinbox import evaluate_table_cell_input, set_table_spinbox
from setuav_studio.ui.widget.table import ExpressionPropertyCell, PropertyTableMixin
from setuav_studio.utilities.transform import attached_component_ids, components_by_id

_VEHICLE_LABEL = "Vehicle"


class TransformEditor(PropertyTableMixin, QWidget):
    """Edit what a component is attached to and its position and rotation relative to it.

    A subpart's frame is the component it is part of, which its own editor selects, so
    for a subpart the attach target is shown but not edited here.
    """

    table_edit_triggers = QAbstractItemView.EditTrigger.NoEditTriggers
    table_value_placeholder = "-"
    table_value_editable_default = False

    def __init__(
        self,
        api: StudioAPI,
        component: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("core.transform_editor")
        self._api = api
        component_id = str(component["id"])
        self._component = (
            api.project.get_component(component_id)
            if api.project is not None and component_id
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
            api.on_project_content_changed(self._on_project_content_changed)
        else:
            self._set_enabled(False)

    def _on_project_content_changed(self, _project: Any = None) -> None:
        if not self._loading and self._component is not None:
            self._load_component(self._component)

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
                ("attach_to", "Attached to"),
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
        transform_kind: str = "position",
        axis: str = "x",
        value: float | str = 0.0,
        label: str = "",
    ) -> ExpressionPropertyCell:
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
            property_key=axis,
            raw_callback=True,
            api=self._api,
            label=label,
            on_changed=lambda val, k=transform_kind, a=axis: self._on_transform_changed(k, a, val),
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
            self._load_attach_to(component)

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
                    transform_kind="position",
                    axis=axis,
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
                    transform_kind="rotation",
                    axis=axis,
                    value=rot.get(axis, 0.0),
                    label=f"Rotation {axis.title()}",
                )
        finally:
            self._loading = False

    def _on_transform_changed(self, kind: str, axis: str, value: Any) -> None:
        if self._loading or self._component is None:
            return
        spins = self.position_spins if kind == "position" else self.rotation_spins
        spin = spins.get(axis)
        parsed = evaluate_table_cell_input(
            value,
            self._api,
            cell=spin,
            label=f"{kind.title()} {axis.upper()}",
            min_val=-360.0 if kind == "rotation" else -1_000_000_000.0,
            max_val=360.0 if kind == "rotation" else 1_000_000_000.0,
        )
        if parsed is None:
            return
        num_val, expr_to_store = parsed
        component = self._component

        def change() -> None:
            target = self._position() if kind == "position" else self._rotation()
            target[axis] = num_val
            set_expression(target, axis, expr_to_store)

        self._api.edit_component(
            component,
            f"Edit transform of {component.get('name') or 'component'}",
            change,
        )

    def _load_attach_to(self, component: dict[str, Any]) -> None:
        project = self._api.project
        assert project is not None
        components = components_by_id(project)
        current = str(component.get("attach_to") or "")
        if component.get("type") in self._api.subpart_types:
            target = components.get(current)
            name = str(target.get("name") or current) if target else _VEHICLE_LABEL
            self._set_property_value(self.reference_table, "attach_to", name, editable=False)
            return
        component_id = str(component["id"])
        excluded = {component_id} | attached_component_ids(component_id, components)
        options = [("", _VEHICLE_LABEL)] + [
            (other_id, str(other.get("name") or other_id))
            for other_id, other in components.items()
            if other_id not in excluded and other.get("type") not in self._api.subpart_types
        ]
        self._set_property_combo(
            self.reference_table, "attach_to", current, options, self._on_attach_to_changed
        )

    def _on_attach_to_changed(self, target_id: str) -> None:
        if self._loading or self._component is None:
            return
        if target_id == str(self._component.get("attach_to") or ""):
            return
        self._api.attach_component(
            self._component, target_id or None, preserve_world_transform=True
        )
        self._load_component(self._component)

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
