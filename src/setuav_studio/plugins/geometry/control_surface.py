from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import get_icon
from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.property_tables import PropertyTableMixin

CONTROL_SURFACE_TYPES = [
    ("aileron", "Aileron"),
    ("flap", "Flap"),
    ("elevator", "Elevator"),
    ("rudder", "Rudder"),
    ("elevon", "Elevon"),
    ("ruddervator", "Ruddervator"),
]


class ControlSurfaceEditor(PropertyTableMixin, QWidget):
    table_scroll_policy_off = True
    table_max_visible_rows = None
    def __init__(self, api: StudioAPI, component: dict[str, Any]) -> None:
        super().__init__()
        self._api = api
        self._component = component
        self._loading = False

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(6, 6, 6, 8)
        self._content_layout.setSpacing(10)

        self._create_general_section()
        self._create_properties_section()
        self._content_layout.addStretch(1)

        scroll.setWidget(content)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(scroll)

        self.load_component(component)

    def load_component(self, component: dict[str, Any]) -> None:
        self._loading = True
        try:
            self._component = component
            self._load_general()
            self._load_properties()
        finally:
            self._loading = False

    def _create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout:
        section = QWidget()
        section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        header = QWidget()
        header.setProperty("sectionHeader", True)
        header.setFixedHeight(20)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)

        if icon_name:
            icon_label = QLabel()
            pixmap = get_icon(icon_name).pixmap(14, 14)
            icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(14, 14)
            header_layout.addWidget(icon_label)

        title_label = QLabel(title)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addWidget(header)
        self._content_layout.addWidget(section)
        return layout

    def _create_general_section(self) -> None:
        layout = self._create_section("General", "fa6s.circle-info")
        self.general_table = self._property_table([
            ("name", "Name"),
            ("type", "Type"),
            ("parent", "Parent Wing"),
        ])
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _create_properties_section(self) -> None:
        layout = self._create_section("Control Surface Geometry", "fa6s.sliders")
        self.properties_table = self._property_table([
            ("type", "Surface Type"),
            ("span_start", "Span Start (mm)"),
            ("span_end", "Span End (mm)"),
            ("chord", "Chord (mm)"),
            ("hinge_sweep", "Hinge Sweep (°)"),
            ("deflection", "Deflection (°)"),
        ])
        self.properties_table.cellChanged.connect(self._update_property)
        layout.addWidget(self.properties_table)

    def _load_general(self) -> None:
        name = str(self._component.get("name") or self._component.get("id") or "")
        comp_type = str(self._component.get("type") or "org.setuav.core:control-surface")
        parent = str(self._component.get("parent") or self._component.get("attach_to") or "")

        self._set_property_value(self.general_table, "name", name)
        self._set_property_value(self.general_table, "type", comp_type)

        # Parent combo (find all lifting surface components)
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)
        options: list[tuple[str, str]] = [("", "-- None --")]
        if project and isinstance(project.data.get("components"), list):
            for c in project.data["components"]:
                if isinstance(c, dict) and c.get("type") == "org.setuav.core:lifting-surface":
                    cid = str(c.get("id") or "")
                    cname = str(c.get("name") or cid)
                    options.append((cid, cname))

        self._set_property_combo(
            self.general_table,
            "parent",
            parent,
            options,
            self._update_parent,
        )

    def _load_properties(self) -> None:
        geom = self._geometry()
        cs_type = str(geom.get("type") or "aileron")
        span_start = float(geom.get("span_start", 0.0))
        span_end = float(geom.get("span_end", 0.0))
        chord = float(geom.get("chord", 40.0))
        hinge_sweep = float(geom.get("hinge_sweep", 0.0))
        deflection = float(geom.get("deflection", 0.0))

        self._set_property_combo(
            self.properties_table,
            "type",
            cs_type,
            CONTROL_SURFACE_TYPES,
            lambda val: self._update_geom_value("type", val),
        )
        self._set_property_value(self.properties_table, "span_start", f"{span_start:.1f} mm")
        self._set_property_value(self.properties_table, "span_end", f"{span_end:.1f} mm")
        self._set_property_value(self.properties_table, "chord", f"{chord:.1f} mm")
        self._set_property_value(self.properties_table, "hinge_sweep", f"{hinge_sweep:.1f}°")
        self._set_property_value(self.properties_table, "deflection", f"{deflection:.1f}°")

    def _geometry(self) -> dict[str, Any]:
        params = self._component.get("parameters")
        if not isinstance(params, dict):
            params = {}
            self._component["parameters"] = params
        geom = params.get("geometry")
        if not isinstance(geom, dict):
            geom = {}
            params["geometry"] = geom
        return geom

    def _update_general(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.general_table, row)
        val_str = self._property_text(self.general_table, row).strip()
        if key == "name":
            def change() -> None:
                self._component["name"] = val_str
                self._geometry()["tag"] = val_str
            self._edit_component("Rename control surface", change)

    def _update_parent(self, new_parent: str | None) -> None:
        if self._loading:
            return
        def change() -> None:
            self._component["parent"] = new_parent if new_parent else None
            self._component["attach_to"] = new_parent if new_parent else None
        self._edit_component("Change control surface parent wing", change)

    def _update_property(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.properties_table, row)
        val_str = self._property_text(self.properties_table, row)
        if key in ("span_start", "span_end", "chord", "hinge_sweep", "deflection"):
            val = self._parse_number(val_str) or 0.0
            self._update_geom_value(key, val)

    def _update_geom_value(self, key: str, value: Any) -> None:
        if self._loading:
            return
        def change() -> None:
            self._geometry()[key] = value
        self._edit_component(f"Edit {key}", change)

    def _edit_component(self, action_name: str, mutation: Callable[[], None]) -> None:
        if hasattr(self._api, "edit_component"):
            self._api.edit_component(self._component, action_name, mutation)
        else:
            mutation()

    def _set_property_combo(
        self,
        table: QTableWidget,
        key: str,
        value: str,
        options: list[tuple[str, str]],
        on_changed: Callable[[str], None],
    ) -> None:
        for row in range(table.rowCount()):
            if self._property_key(table, row) != key:
                continue
            item = table.item(row, 1)
            if item is not None:
                item.setText("")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            combo = QComboBox(table)
            combo.setFont(QApplication.font())
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            for opt_val, opt_label in options:
                combo.addItem(opt_label, opt_val)
            idx = combo.findData(value)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.currentIndexChanged.connect(lambda _i: on_changed(str(combo.currentData())))
            table.setCellWidget(row, 1, combo)
            return


    @staticmethod
    def _parse_number(value: str) -> float | None:
        try:
            return float(
                value.replace("°", "")
                .replace("mm", "")
                .replace("g", "")
                .split("(")[0]
                .strip()
            )
        except ValueError:
            return None
