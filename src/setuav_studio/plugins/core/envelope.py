"""Shared physical-envelope editor for non-geometric components."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)
from setuav_studio_sdk import StudioAPI

from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.numeric_spinbox import NumericSpinBox, set_table_spinbox
from setuav_studio.ui.property_tables import PropertyTableMixin

from .derived_geometry import derive_component_geometry

PHYSICAL_EXTENSION_ID = "org.setuav.core.physical"


class EnvelopeEditor(PropertyTableMixin, QWidget):
    """Edit a component's local bounding envelope and show its volume."""

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
        self.setObjectName("core.envelope_editor")
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

        self._create_definition_section()
        self._create_dimensions_section()
        self._create_offset_section()
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

    def _create_definition_section(self) -> None:
        layout = self._create_section("Envelope", "fa6s.ruler-combined")
        self.definition_table = self._property_table(
            [
                ("component", "Component"),
                ("shape", "Shape"),
                ("volume", "Volume"),
            ]
        )
        layout.addWidget(self.definition_table)
        self._set_property_combo(
            self.definition_table,
            "shape",
            "box",
            [("box", "Box")],
            self._on_shape_changed,
        )
        self.shape_combo = self._find_combo(self.definition_table, "shape")

    def _create_dimensions_section(self) -> None:
        layout = self._create_section("Dimensions", "fa6s.arrows-left-right")
        self.dimensions_table = self._vector_table("Size (mm)")
        self.dimension_spins = {
            axis: self._set_vector_spin(self.dimensions_table, column, axis)
            for column, axis in enumerate(("x", "y", "z"))
        }
        layout.addWidget(self.dimensions_table)

    def _create_offset_section(self) -> None:
        layout = self._create_section("Local Offset", "mdi6.axis-arrow")
        self.offset_table = self._vector_table("Offset (mm)")
        self.offset_spins = {
            axis: self._set_vector_spin(self.offset_table, column, axis)
            for column, axis in enumerate(("x", "y", "z"))
        }
        layout.addWidget(self.offset_table)

    @staticmethod
    def _vector_table(row_label: str) -> QTableWidget:
        table = QTableWidget(1, 3)
        table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        table.setVerticalHeaderLabels([row_label])
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setFixedHeight(23)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.verticalHeader().setDefaultSectionSize(23)
        table.verticalHeader().setMinimumWidth(96)
        table.setFixedHeight(48)
        return table

    def _set_vector_spin(
        self,
        table: QTableWidget,
        column: int,
        _axis: str,
    ) -> NumericSpinBox:
        return set_table_spinbox(
            table,
            0,
            column,
            0.0,
            min_val=0.0 if table is self.dimensions_table else -1_000_000_000.0,
            max_val=1_000_000_000.0,
            step=1.0,
            decimals=3,
            suffix="mm",
            on_changed=lambda _value: self._update_envelope(),
        )

    def _load_component(self, component: dict[str, Any]) -> None:
        self._loading = True
        try:
            self._set_property_value(
                self.definition_table,
                "component",
                str(component.get("name") or component.get("id") or ""),
                editable=False,
            )
            envelope = self._envelope(component)
            if not envelope:
                project_data = getattr(self._api.current_project, "data", {})
                project_components = (
                    project_data.get("components", []) if isinstance(project_data, dict) else []
                )
                by_id = {
                    str(item.get("id")): item
                    for item in project_components
                    if isinstance(item, dict) and isinstance(item.get("id"), str)
                }
                by_id.setdefault(str(component.get("id") or ""), component)
                derived = derive_component_geometry(component, by_id)
                envelope = derived.envelope
            shape = str(envelope.get("shape") or "box")
            if self.shape_combo is not None:
                index = max(self.shape_combo.findData(shape), 0)
                self.shape_combo.setCurrentIndex(index)
            self._load_vector(
                self.dimension_spins,
                envelope.get("size_mm"),
            )
            self._load_vector(
                self.offset_spins,
                envelope.get("offset_mm"),
            )
            self._update_volume_display()
        finally:
            self._loading = False

    def _on_shape_changed(self, _shape: str) -> None:
        self._update_envelope()

    def _update_envelope(self) -> None:
        if self._loading or self._component is None:
            return
        shape = str(self.shape_combo.currentData() or "box")
        size = {axis: spin.value() for axis, spin in self.dimension_spins.items()}
        offset = {axis: spin.value() for axis, spin in self.offset_spins.items()}

        def change(extension: dict[str, Any]) -> None:
            extension["envelope"] = {
                "shape": shape,
                "size_mm": size,
                "offset_mm": offset,
            }

        self._api.edit_component_extension(
            str(self._component.get("id") or ""),
            PHYSICAL_EXTENSION_ID,
            f"Edit physical envelope of {self._component.get('name') or 'component'}",
            change,
        )
        self._update_volume_display()

    def _update_volume_display(self) -> None:
        volume_mm3 = self.volume_value()
        value = (
            f"{volume_mm3 / 1_000_000_000.0:.6f} m³ ({volume_mm3 / 1_000_000.0:.3f} L)"
            if volume_mm3 > 0.0
            else "—"
        )
        self._set_property_value(
            self.definition_table,
            "volume",
            value,
            editable=False,
        )

    def volume_value(self) -> float:
        """Return the current box envelope volume in cubic millimetres."""
        volume_mm3 = 1.0
        for spin in self.dimension_spins.values():
            volume_mm3 *= spin.value()
        return volume_mm3

    @staticmethod
    def _envelope(component: dict[str, Any]) -> dict[str, Any]:
        extensions = component.get("extensions")
        extensions = extensions if isinstance(extensions, dict) else {}
        envelope_extension = extensions.get(PHYSICAL_EXTENSION_ID)
        envelope_extension = envelope_extension if isinstance(envelope_extension, dict) else {}
        envelope = envelope_extension.get("envelope")
        return envelope if isinstance(envelope, dict) else {}

    @staticmethod
    def _load_vector(spins: dict[str, NumericSpinBox], value: object) -> None:
        values = value if isinstance(value, dict) else {}
        for axis, spin in spins.items():
            spin.setValue(_number(values.get(axis)))

    @staticmethod
    def _find_combo(table: QTableWidget, key: str) -> QComboBox | None:
        for row in range(table.rowCount()):
            if str(table.item(row, 0).data(Qt.ItemDataRole.UserRole) or "") != key:
                continue
            widget = table.cellWidget(row, 1)
            return widget if isinstance(widget, QComboBox) else None
        return None

    def _set_enabled(self, enabled: bool) -> None:
        self.definition_table.setEnabled(enabled)
        self.dimensions_table.setEnabled(enabled)
        self.offset_table.setEnabled(enabled)


def _number(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
