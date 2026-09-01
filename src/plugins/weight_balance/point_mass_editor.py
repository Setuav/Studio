"""Properties editor for point-mass components."""

from __future__ import annotations

import contextlib
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
from setuav_studio.ui.numeric_spinbox import set_table_spinbox
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
        layout = self._create_section("Mass", "fa6s.weight-scale")
        self.mass_table = self._property_table([("mass", "Mass")])
        layout.addWidget(self.mass_table)

    def _create_transform_section(self) -> None:
        layout = self._create_section("Transform", "mdi6.axis-arrow")
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
            )
            for column, axis in enumerate(("roll", "pitch", "yaw"))
        }
        layout.addWidget(self.transform_table)

    def _spin(
        self,
        row: int,
        column: int,
        minimum: float,
        maximum: float,
        quantity: str,
        suffix: str,
        label: str = "",
    ) -> Any:
        self_ref = weakref.ref(self)
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
            on_changed=lambda _value: (
                self_ref()._transform_changed() if self_ref() is not None else None
            ),
            api=self._api,
            label=label,
        )

    def _load_component(self) -> None:
        self._loading = True
        try:
            params = self._component.get("parameters")
            params = params if isinstance(params, dict) else {}
            mass_val = self._component.get("mass_expression") or self._component.get(
                "mass", params.get("mass", 0.0)
            )
            self._set_property_expression(
                self.mass_table,
                "mass",
                mass_val,
                on_changed=self._on_mass_expression_changed,
                label="Mass",
                unit="g",
            )
            transform = self._component.get("transform")
            transform = transform if isinstance(transform, dict) else {}
            position = transform.get("position")
            position = position if isinstance(position, dict) else {}
            rotation = transform.get("rotation")
            rotation = rotation if isinstance(rotation, dict) else {}
            for axis, spin in self.position_spins.items():
                val = position.get(f"{axis}_expression") or position.get(axis, 0.0)
                spin.setValue(val)
            for axis, spin in self.rotation_spins.items():
                val = rotation.get(f"{axis}_expression") or rotation.get(axis, 0.0)
                spin.setValue(val)
        finally:
            self._loading = False

    def _on_mass_expression_changed(self, val_text: str) -> None:
        if self._loading:
            return
        clean = val_text.strip()
        num_val: float | None = None
        params = self._component.setdefault("parameters", {})
        if clean.startswith("=") or not clean.replace(".", "", 1).replace("-", "", 1).isdigit():
            params["mass_expression"] = clean
            if self._api is not None and getattr(self._api, "current_project", None) is not None:
                try:
                    from setuav_studio.project.expressions import ExpressionEvaluator

                    evaluator = ExpressionEvaluator()
                    scope = self._api.current_project.get_scope(api=self._api)
                    expr = clean.lstrip("=").strip()
                    res = evaluator.evaluate(expr, scope)
                    if isinstance(res, (int, float)):
                        num_val = float(res)
                except Exception:
                    pass
        else:
            params.pop("mass_expression", None)
            with contextlib.suppress(ValueError):
                num_val = float(clean)

        def change() -> None:
            if num_val is not None:
                self._component["mass"] = num_val
                self._component.setdefault("parameters", {})["mass"] = num_val

        self._api.edit_component(self._component, "Edit point mass", change)

    def _transform_changed(self) -> None:
        if self._loading:
            return
        position = {axis: spin.value() for axis, spin in self.position_spins.items()}
        rotation = {axis: spin.value() for axis, spin in self.rotation_spins.items()}

        def change() -> None:
            tf = self._component.setdefault("transform", {})
            tf["position"] = position
            tf["rotation"] = rotation
            # Store any transform expression strings safely in component parameters
            exprs: dict[str, str] = {}
            for axis, spin in self.position_spins.items():
                txt = spin.text().strip()
                if txt.startswith("="):
                    exprs[f"position.{axis}"] = txt
            for axis, spin in self.rotation_spins.items():
                txt = spin.text().strip()
                if txt.startswith("="):
                    exprs[f"rotation.{axis}"] = txt
            if exprs:
                self._component.setdefault("parameters", {})["transform_expressions"] = exprs
            elif "parameters" in self._component:
                self._component["parameters"].pop("transform_expressions", None)

        self._api.edit_component(self._component, "Edit point-mass transform", change)

    def update_theme_style(self) -> None:
        for label, icon_name in self._section_icons:
            set_label_icon(label, icon_name)


def _number(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
