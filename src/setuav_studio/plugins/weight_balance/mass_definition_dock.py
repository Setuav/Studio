"""Properties editor for a component's declared mass properties."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.buttons import refresh_button_role, set_button_role
from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.numeric_spinbox import NumericSpinBox, set_table_spinbox
from setuav_studio.ui.property_tables import PropertyTableMixin

from .engine.solver import EXTENSION_ID


class MassPropertiesEditor(PropertyTableMixin, QWidget):
    """Table-based mass editor styled like the other SETUAV property docks."""

    table_scroll_policy_off = True
    table_max_visible_rows = None

    def __init__(
        self,
        api: StudioAPI,
        selection: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("weight_balance.mass_properties_editor")
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

        self._create_mass_section(component_id)
        self._create_cg_section()
        self._create_inertia_section()
        self._create_actions()
        self._content_layout.addStretch(1)

        self.apply_button.setEnabled(self._component is not None)
        self.apply_button.clicked.connect(self._apply)

        if self._component is not None:
            self._load_component(self._component)

    def update_theme_style(self) -> None:
        for label, icon_name in self._section_icons:
            set_label_icon(label, icon_name)
        refresh_button_role(self.apply_button)

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

    def _create_mass_section(self, component_id: str) -> None:
        layout = self._create_section("Mass", "fa6s.cubes-stacked")
        self.mass_table = self._property_table(
            [
                ("component", "Component"),
                ("mass", "Mass"),
            ]
        )
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
            suffix="g",
        )
        layout.addWidget(self.mass_table)

    def _create_cg_section(self) -> None:
        layout = self._create_section("Local Center of Gravity", "fa6s.crosshairs")
        self.cg_table = QTableWidget(1, 3, self)
        self.cg_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.cg_table.setVerticalHeaderLabels(["Position (mm)"])
        self.cg_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.cg_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectItems
        )
        self.cg_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cg_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.cg_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.cg_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.cg_table.horizontalHeader().setFixedHeight(23)
        self.cg_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
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
                suffix="mm",
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
                        suffix="kg·m²",
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

    def _create_actions(self) -> None:
        container = QWidget(self)
        container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 2)

        self.apply_button = QPushButton("Apply Mass Properties", container)
        self.apply_button.setFixedHeight(28)
        set_button_role(self.apply_button, "primary", "fa6s.check")
        layout.addWidget(self.apply_button)
        self._content_layout.addWidget(container)

    def _set_numeric_cell(
        self,
        table: QTableWidget,
        key: str,
        *,
        minimum: float,
        maximum: float,
        step: float,
        decimals: int,
        suffix: str,
    ) -> NumericSpinBox:
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
                    suffix=suffix,
                )
        raise KeyError(f"Unknown mass-properties field: {key}")

    def _load_component(self, component: dict[str, Any]) -> None:
        self._loading = True
        try:
            source = self._source_component(component)
            parameters = component.get("parameters")
            parameters = parameters if isinstance(parameters, dict) else {}
            source_parameters = source.get("parameters")
            source_parameters = (
                source_parameters if isinstance(source_parameters, dict) else {}
            )
            mass = component.get(
                "mass",
                parameters.get(
                    "mass",
                    source.get("mass", source_parameters.get("mass", 0.0)),
                ),
            )
            self.mass_g.setValue(_number(mass))

            source_extensions = source.get("extensions")
            source_extensions = (
                source_extensions if isinstance(source_extensions, dict) else {}
            )
            source_definition = source_extensions.get(EXTENSION_ID)
            source_definition = (
                source_definition if isinstance(source_definition, dict) else {}
            )
            extensions = component.get("extensions")
            extensions = extensions if isinstance(extensions, dict) else {}
            own_definition = extensions.get(EXTENSION_ID)
            own_definition = (
                own_definition if isinstance(own_definition, dict) else {}
            )
            definition = dict(source_definition)
            definition.update(own_definition)
            cg = definition.get("local_cg_mm")
            cg = cg if isinstance(cg, dict) else {}
            for axis, spin in self.cg_spins.items():
                spin.setValue(_number(cg.get(axis)))

            inertia = definition.get(
                "inertia_kg_m2",
                parameters.get("inertia", source_parameters.get("inertia")),
            )
            inertia = inertia if isinstance(inertia, dict) else {}
            for key, spin in self.inertia_spins.items():
                spin.setValue(_number(inertia.get(key)))
        finally:
            self._loading = False

    def _apply(self) -> None:
        component = self._component
        if self._loading or component is None:
            return
        mass_g = self.mass_g.value()
        cg = {axis: spin.value() for axis, spin in self.cg_spins.items()}
        inertia = {key: spin.value() for key, spin in self.inertia_spins.items()}

        def change() -> None:
            component["mass"] = mass_g
            parameters = component.get("parameters")
            if isinstance(parameters, dict) and "mass" in parameters:
                parameters["mass"] = mass_g
            extensions = component.setdefault("extensions", {})
            if not isinstance(extensions, dict):
                extensions = {}
                component["extensions"] = extensions
            definition = extensions.setdefault(EXTENSION_ID, {})
            if not isinstance(definition, dict):
                definition = {}
                extensions[EXTENSION_ID] = definition
            definition.update(
                {
                    "mass_source": "declared",
                    "local_cg_mm": cg,
                    "inertia_kg_m2": inertia,
                }
            )

        self._api.edit_component(component, "Edit component mass definition", change)

    def _source_component(self, component: dict[str, Any]) -> dict[str, Any]:
        if component.get("kind") != "instance" or self._api.current_project is None:
            return component
        source_id = component.get("source")
        source = self._api.current_project.get_component(str(source_id or ""))
        return source if source is not None else component


def _number(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
