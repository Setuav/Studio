"""Properties editor for a component's declared mass properties."""

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

from setuav_studio.api import StudioAPI, StudioEvents
from setuav_studio.model.expression import get_expression, set_expression
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.spinbox import evaluate_table_cell_input, set_table_spinbox
from setuav_studio.ui.widget.table import ExpressionPropertyCell, PropertyTableMixin
from setuav_studio.units import get_unit_manager
from setuav_studio.utilities.mass_balance import (
    get_component_subparts,
    resolve_component_aggregate_mass_properties,
    resolve_component_local_cg,
    resolve_component_local_inertia,
)


class MassPropertiesEditor(PropertyTableMixin, QWidget):
    """Table-based mass editor styled like the other Setuav property docks."""

    table_scroll_policy_off = True
    table_max_visible_rows = None

    def __init__(
        self,
        api: StudioAPI,
        component: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("core.mass_properties_editor")
        self._api = api
        component_id = str(component["id"])
        self._component_id = component_id
        self._component = (
            api.project.get_component(component_id)
            if api.project is not None and component_id
            else None
        )
        self._loading = False
        self._section_icons: list[tuple[QLabel, str]] = []
        # Subparts such as control surfaces carry their own mass; the fields
        # below edit this component alone and a read-only row shows the total.
        self._has_subparts = bool(
            self._component is not None
            and api.project is not None
            and get_component_subparts(component_id, api.project, api.subpart_types)
        )

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

        self._create_mass_section(component_id)
        component_type = api.get_component_type(str(component.get("type") or ""))
        if component_type is not None and component_type.derived_mass:
            self.mass_g.setReadOnly(True)
        self._create_cg_section()
        self._create_inertia_section()
        self._content_layout.addStretch(1)

        if self._component is not None:
            self._load_component(self._component)
            api.on_project_content_changed(self._on_project_content_changed)
            api.subscribe(StudioEvents.UNITS_CHANGED, self._on_project_content_changed)

    def _on_project_content_changed(self, _project: Any = None) -> None:
        if self._loading or not self._component_id or self._api.project is None:
            return
        comp = self._api.project.get_component(self._component_id)
        if comp is not None:
            self._component = comp
            self._load_component(comp)

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

    def _create_mass_section(self, component_id: str) -> None:
        layout = self._create_section("Mass", "fa6s.cubes-stacked")
        rows = [("component", "Component"), ("mass", "Mass")]
        if self._has_subparts:
            rows.append(("total_mass", "Total with Subparts"))
        self.mass_table = self._property_table(rows)
        component_name = (
            str(self._component.get("name") or component_id)
            if self._component is not None
            else "Missing component"
        )
        self._set_property_value(
            self.mass_table,
            "component",
            component_name,
            editable=False,
        )
        self.mass_g = self._set_numeric_cell(
            self.mass_table,
            "mass",
            minimum=0.0,
            maximum=1_000_000_000.0,
            step=1.0,
            decimals=3,
            quantity="mass",
            suffix="g",
            on_changed=lambda raw: self._on_field_changed("mass", raw),
        )
        layout.addWidget(self.mass_table)

    def _create_cg_section(self) -> None:
        layout = self._create_section("Local Center of Gravity", "fa6s.crosshairs")
        self.cg_table = QTableWidget(1, 3)
        self.cg_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.cg_table.setVerticalHeaderLabels(["Position"])
        self.cg_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.cg_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.cg_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cg_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cg_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cg_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.cg_table.horizontalHeader().setFixedHeight(23)
        self.cg_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.cg_table.verticalHeader().setDefaultSectionSize(23)
        self.cg_table.verticalHeader().setMinimumWidth(82)
        self.cg_table.setAlternatingRowColors(True)
        self.cg_table.setFixedHeight(48)

        self.cg_spins = {
            axis: set_table_spinbox(
                self.cg_table,
                0,
                column,
                0.0,
                min_val=-10_000_000.0,
                max_val=10_000_000.0,
                step=1.0,
                decimals=3,
                quantity="length",
                suffix="mm",
                raw_callback=True,
                on_changed=lambda raw, axis=axis: self._on_field_changed(f"cg.{axis}", raw),
                api=self._api,
                label=f"CG {axis.upper()}",
            )
            for column, axis in enumerate(("x", "y", "z"))
        }
        layout.addWidget(self.cg_table)

    def _create_inertia_section(self) -> None:
        layout = self._create_section("Inertia Tensor", "fa6s.cube")
        moment_keys = ("ixx", "iyy", "izz")
        product_keys = ("ixy", "ixz", "iyz")
        self.inertia_moments_table = self._inertia_row_table(
            [key.upper() for key in moment_keys],
            "Moments",
        )
        self.inertia_products_table = self._inertia_row_table(
            [key.upper() for key in product_keys],
            "Products",
        )
        self.inertia_spins = {}
        for table, keys, minimum in (
            (self.inertia_moments_table, moment_keys, 0.0),
            (self.inertia_products_table, product_keys, -1_000_000.0),
        ):
            self.inertia_spins.update(
                {
                    key: set_table_spinbox(
                        table,
                        0,
                        column,
                        0.0,
                        min_val=minimum,
                        max_val=1_000_000.0,
                        step=0.000001,
                        decimals=8,
                        quantity="inertia",
                        suffix="kg·m²",
                        raw_callback=True,
                        on_changed=lambda raw, key=key: self._on_field_changed(
                            f"inertia.{key}", raw
                        ),
                        api=self._api,
                        label=key.upper(),
                    )
                    for column, key in enumerate(keys)
                }
            )
        layout.addWidget(self.inertia_moments_table)
        layout.addWidget(self.inertia_products_table)

    @staticmethod
    def _inertia_row_table(headers: list[str], row_label: str) -> QTableWidget:
        table = QTableWidget(1, 3)
        table.setHorizontalHeaderLabels(headers)
        table.setVerticalHeaderLabels([row_label])
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setFixedHeight(23)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.verticalHeader().setDefaultSectionSize(23)
        table.verticalHeader().setMinimumWidth(82)
        table.setAlternatingRowColors(True)
        table.setFixedHeight(48)
        return table

    def _set_numeric_cell(
        self,
        table: QTableWidget,
        key: str,
        *,
        minimum: float,
        maximum: float,
        step: float,
        decimals: int,
        quantity: str = "",
        suffix: str,
        on_changed: Any | None = None,
    ) -> ExpressionPropertyCell:
        for row in range(table.rowCount()):
            if self._property_key(table, row) == key:
                return set_table_spinbox(
                    table,
                    row,
                    1,
                    0.0,
                    min_val=minimum,
                    max_val=maximum,
                    step=step,
                    decimals=decimals,
                    quantity=quantity,
                    suffix=suffix,
                    raw_callback=True,
                    on_changed=on_changed,
                    api=self._api,
                    label=key.title(),
                )
        raise KeyError(f"Unknown mass-properties field: {key}")

    def _load_component(self, component: dict[str, Any]) -> None:
        self._loading = True
        try:
            source = self._source_component(component)
            mass = _number(component.get("mass", source.get("mass", 0.0)))
            _show(self.mass_g, mass, get_expression(component, "mass"))

            cg = resolve_component_local_cg(component)
            declared_cg = component.get("local_cg_mm")
            for axis, value in zip(("x", "y", "z"), cg, strict=True):
                _show(self.cg_spins[axis], value, get_expression(declared_cg, axis))

            inertia_tensor = resolve_component_local_inertia(component, mass / 1000.0)
            declared_inertia = component.get("inertia_kg_m2")
            for key, spin in self.inertia_spins.items():
                value = float(getattr(inertia_tensor, key))
                _show(spin, value, get_expression(declared_inertia, key))

            if self._has_subparts and self._api.project is not None:
                total = resolve_component_aggregate_mass_properties(
                    str(component["id"]), self._api.project, self._api.subpart_types
                )
                self._set_property_value(
                    self.mass_table,
                    "total_mass",
                    get_unit_manager().format_value(total.mass_kg * 1000.0, "mass", 3),
                    editable=False,
                )
        finally:
            self._loading = False

    def _on_field_changed(self, field: str, raw: str) -> None:
        """Store the one edited value with its formula; the others stay as they are."""
        component = self._component
        if self._loading or component is None:
            return
        cells = {
            "mass": self.mass_g,
            **{f"cg.{axis}": spin for axis, spin in self.cg_spins.items()},
            **{f"inertia.{key}": spin for key, spin in self.inertia_spins.items()},
        }
        cell = cells[field]
        group, _, key = field.partition(".")
        min_val = 0.0 if (group == "mass" or key in ("ixx", "iyy", "izz")) else None
        parsed = evaluate_table_cell_input(
            raw, self._api, cell=cell, label=cell.get_label(), min_val=min_val
        )
        if parsed is None:
            return
        value, expression = parsed

        def change() -> None:
            if group == "mass":
                target, key_in_target = component, "mass"
            else:
                name = "local_cg_mm" if group == "cg" else "inertia_kg_m2"
                target = component.setdefault(name, {})
                key_in_target = key
            target[key_in_target] = value
            set_expression(target, key_in_target, expression)

        self._api.edit_component(component, "Change component mass", change)
        self._load_component(component)
        viewport = self._api.viewport
        if viewport is not None:
            viewport.update_component_cg()
            viewport.update_aircraft_cg()

    def _source_component(self, component: dict[str, Any]) -> dict[str, Any]:
        if component.get("kind") != "instance" or self._api.project is None:
            return component
        source_id = component.get("source")
        source = self._api.project.get_component(str(source_id or ""))
        return source if source is not None else component


def _number(value: object) -> float:
    if value is None or value == "":
        return 0.0
    try:
        if isinstance(value, (int, float, str)):
            return float(value)
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _show(cell: ExpressionPropertyCell, value: float, expression: str | None) -> None:
    """Show a stored formula, or the value when the field has none."""
    cell.setText(expression if expression is not None else str(value))
