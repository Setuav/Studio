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

from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.widget.spinbox import NumericSpinBox, set_table_spinbox
from setuav_studio.ui.widget.table import PropertyTableMixin
from setuav_studio_sdk import StudioAPI


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

        self._create_definition_section()
        self._create_dimensions_section()
        self._create_offset_section()
        self._create_sections_section()
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

    def _create_definition_section(self) -> None:
        layout = self._create_section("Envelope", "envelope")
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
            [
                ("box", "Box"),
                ("trapezoid", "Trapezoid"),
                ("cylinder", "Cylinder"),
                ("sphere", "Sphere"),
            ],
            self._on_shape_changed,
        )
        self.shape_combo = self._find_combo(self.definition_table, "shape")

    def _create_dimensions_section(self) -> None:
        layout = self._create_section("Dimensions", "fa6s.arrows-left-right")
        self.dimensions_table = self._vector_table("Size")
        self.dimension_spins = {
            axis: self._set_vector_spin(self.dimensions_table, column, axis)
            for column, axis in enumerate(("x", "y", "z"))
        }
        layout.addWidget(self.dimensions_table)

    def _create_offset_section(self) -> None:
        layout = self._create_section("Local Offset", "mdi6.axis-arrow")
        self.offset_table = self._vector_table("Offset")
        self.offset_spins = {
            axis: self._set_vector_spin(self.offset_table, column, axis)
            for column, axis in enumerate(("x", "y", "z"))
        }
        layout.addWidget(self.offset_table)

    def _create_sections_section(self) -> None:
        self._sections_container = QWidget()
        layout = QVBoxLayout(self._sections_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        header = QWidget(self._sections_container)
        header.setProperty("sectionHeader", True)
        header.setFixedHeight(20)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)

        icon_label = QLabel(header)
        set_label_icon(icon_label, "fa6s.layer-group")
        icon_label.setFixedSize(14, 14)
        self._section_icons.append((icon_label, "fa6s.layer-group"))
        header_layout.addWidget(icon_label)
        header_layout.addWidget(QLabel("BBox Sections", header))
        header_layout.addStretch(1)
        layout.addWidget(header)

        self.sections_table = QTableWidget(0, 5)
        self.sections_table.setHorizontalHeaderLabels(
            ["Station", "Width", "Height", "Z Pos", "Shape"]
        )
        self.sections_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sections_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sections_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sections_table.setAlternatingRowColors(True)
        self.sections_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sections_table.horizontalHeader().setFixedHeight(23)
        self.sections_table.verticalHeader().setDefaultSectionSize(23)
        self.sections_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sections_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.sections_table)

        self._content_layout.addWidget(self._sections_container)
        self._sections_container.setVisible(False)

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
            self._load_sections(envelope.get("sections"))
            self._update_volume_display()
        finally:
            self._loading = False

    def _load_sections(self, sections: object) -> None:
        if isinstance(sections, list) and sections:
            self._sections_container.setVisible(True)
            self.sections_table.setRowCount(len(sections))
            self.sections_table.setFixedHeight(23 + len(sections) * 23 + 2)
            from PySide6.QtWidgets import QTableWidgetItem

            for row, sec in enumerate(sections):
                if not isinstance(sec, dict):
                    continue
                st = _number(sec.get("station_x_mm", sec.get("span_y_mm", 0.0)))
                w = _number(sec.get("width_mm", sec.get("chord_mm", 0.0)))
                h = _number(sec.get("height_mm", sec.get("thickness_mm", 0.0)))
                pos = sec.get("position", {}) if isinstance(sec.get("position"), dict) else {}
                z = _number(pos.get("z", 0.0))
                sh = sec.get("shape", "box")
                for col, val in enumerate(
                    (
                        f"{st:.1f} mm",
                        f"{w:.1f} mm",
                        f"{h:.1f} mm",
                        f"{z:.1f} mm",
                        str(sh).capitalize(),
                    )
                ):
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.sections_table.setItem(row, col, item)
        else:
            self._sections_container.setVisible(False)
            self.sections_table.setRowCount(0)
            self.sections_table.setFixedHeight(0)

    def _on_shape_changed(self, _shape: str) -> None:
        self._update_envelope()

    def _update_envelope(self) -> None:
        if self._loading or self._component is None:
            return
        shape = (
            str(self.shape_combo.currentData() or "box") if self.shape_combo is not None else "box"
        )
        size = {axis: spin.value() for axis, spin in self.dimension_spins.items()}
        offset = {axis: spin.value() for axis, spin in self.offset_spins.items()}
        component = self._component

        def change() -> None:
            existing = component.get("envelope")
            new_env = dict(existing) if isinstance(existing, dict) else {}
            new_env.update(
                {
                    "shape": shape,
                    "size_mm": size,
                    "offset_mm": offset,
                }
            )
            component["envelope"] = new_env

        self._api.edit_component(
            component,
            f"Edit envelope of {component.get('name') or 'component'}",
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
        """Return the current envelope volume in cubic millimetres."""
        envelope = self._envelope(self._component) if self._component is not None else {}
        geom_vol = envelope.get("volume_mm3")
        size_mm = envelope.get("size_mm")
        if (
            isinstance(geom_vol, (int, float))
            and geom_vol > 0.0
            and isinstance(size_mm, dict)
            and all(
                abs(self.dimension_spins[axis].value() - _number(size_mm.get(axis))) < 1e-3
                for axis in ("x", "y", "z")
                if axis in self.dimension_spins
            )
        ):
            return float(geom_vol)

        volume_mm3 = 1.0
        for spin in self.dimension_spins.values():
            volume_mm3 *= spin.value()
        shape = (
            str(self.shape_combo.currentData() or "box") if self.shape_combo is not None else "box"
        )
        if shape == "cylinder":
            return volume_mm3 * 0.7853981633974483
        if shape == "sphere":
            return volume_mm3 * 0.5235987755982988
        if shape == "trapezoid":
            return volume_mm3 * 0.6
        return volume_mm3

    @staticmethod
    def _envelope(component: dict[str, Any]) -> dict[str, Any]:
        envelope = component.get("envelope")
        return envelope if isinstance(envelope, dict) else {}

    @staticmethod
    def _load_vector(spins: dict[str, NumericSpinBox], value: object) -> None:
        values = value if isinstance(value, dict) else {}
        for axis, spin in spins.items():
            spin.setValue(_number(values.get(axis)))

    @staticmethod
    def _find_combo(table: QTableWidget, key: str) -> QComboBox | None:
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is None or str(item.data(Qt.ItemDataRole.UserRole) or "") != key:
                continue
            widget = table.cellWidget(row, 1)
            return widget if isinstance(widget, QComboBox) else None
        return None

    def _set_enabled(self, enabled: bool) -> None:
        self.definition_table.setEnabled(enabled)
        self.dimensions_table.setEnabled(enabled)
        self.offset_table.setEnabled(enabled)
        self.sections_table.setEnabled(enabled)


def _number(value: object) -> float:
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    return 0.0
