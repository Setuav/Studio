from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.numeric_spinbox import NumericSpinBox, set_table_spinbox
from setuav_studio.ui.property_tables import PropertyTableMixin
from setuav_studio_sdk import StudioAPI

CONTROL_SURFACE_TYPES = [
    ("aileron", "Aileron"),
    ("flap", "Flap"),
    ("elevator", "Elevator"),
    ("rudder", "Rudder"),
    ("elevon", "Elevon"),
    ("ruddervator", "Ruddervator"),
]

SIZING_DRIVER_MODES = [
    ("ratio", "Preserve Ratio (Eta & %c)"),
    ("dimension", "Preserve Dimension (Span & Depth mm)"),
    ("area_chord", "Area + Chord Fraction Driven"),
    ("area_span", "Area + Span Extent Driven"),
]

SYMMETRY_MODES = [
    ("auto", "Auto (By Type)"),
    ("antisymmetric", "Antisymmetric (Differential)"),
    ("symmetric", "Symmetric"),
    ("none", "None (Single)"),
]


class ControlSurfaceEditor(PropertyTableMixin, QWidget):
    table_scroll_policy_off = True
    table_max_visible_rows = None

    def __init__(self, api: StudioAPI, component: dict[str, Any]) -> None:
        super().__init__()
        self._api = api
        self._component = component
        self._loading = False
        self._cs_spinboxes: dict[str, Any] = {}

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

        from setuav_studio.units import get_unit_manager

        get_unit_manager().units_changed.connect(self._on_units_changed)

        self.load_component(component)

    def _on_units_changed(self) -> None:
        if self._component is not None:
            self._load_properties()

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
            set_label_icon(icon_label, icon_name)
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
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("type", "Type"),
                ("parent", "Parent Wing"),
            ]
        )
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _create_properties_section(self) -> None:
        layout = self._create_section("Control Surfaces", "geometry_add_control_surface")
        self.properties_table = self._property_table(
            [
                ("tag", "Tag / Label"),
                ("type", "Type"),
                ("sizing_mode", "Sizing Driver Mode"),
                ("area", "Area"),
                ("area_ratio", "Area Ratio"),
                ("span_start", "Span Start"),
                ("span_end", "Span End"),
                ("span_length", "Span Length"),
                ("eta_start", "Eta Start"),
                ("eta_end", "Eta End"),
                ("chord_fraction", "Chord Fraction"),
                ("chord", "Control Chord"),
                ("hinge_sweep", "Hinge Sweep"),
                ("deflection", "Deflection Angle"),
                ("symmetry_mode", "Symmetry Mode"),
            ]
        )
        self.properties_table.cellChanged.connect(self._update_property_cell)
        layout.addWidget(self.properties_table)

    def _parent_wing_info(self) -> tuple[float, float, float, float]:
        """Return (semi_span, root_chord, tip_chord, parent_wing_area_dm2) for parent lifting surface."""
        parent_id = str(self._component.get("parent") or self._component.get("attach_to") or "")
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)
        if project and isinstance(project.data.get("components"), list):
            for c in project.data["components"]:
                if isinstance(c, dict) and str(c.get("id") or "") == parent_id:
                    params = c.get("parameters", {})
                    geom = params.get("geometry", {})
                    profs = geom.get("profiles", [])
                    if isinstance(profs, list) and profs:
                        span_values = [
                            float(p.get("position", {}).get("y", 0.0))
                            for p in profs
                            if isinstance(p.get("position"), dict)
                        ]
                        y0 = span_values[0] if span_values else 0.0
                        y1 = span_values[-1] if span_values else 0.0
                        semi_span = abs(y1 - y0) if len(span_values) >= 2 else 400.0
                        root_chord = float(profs[0].get("chord", 150.0))
                        tip_chord = float(profs[-1].get("chord", 100.0))
                        wing_area_dm2 = (semi_span * (root_chord + tip_chord)) / 10000.0
                        return (
                            max(semi_span, 1.0),
                            max(root_chord, 1.0),
                            max(tip_chord, 1.0),
                            max(wing_area_dm2, 0.01),
                        )
        return 400.0, 150.0, 100.0, 10.0

    def _load_general(self) -> None:
        name = str(self._component.get("name") or self._component.get("id") or "")
        comp_type = str(self._component.get("type") or "org.setuav.core:control-surface")
        parent = str(self._component.get("parent") or self._component.get("attach_to") or "")

        self._set_property_value(self.general_table, "name", name)
        self._set_property_value(self.general_table, "type", comp_type, editable=False)

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
        from .control_surface_values import compute_control_surface_metrics

        was_loading = self._loading
        self._loading = True
        try:
            geom = self._geometry()
            semi_span, root_chord, tip_chord, wing_area = self._parent_wing_info()
            self._cs_spinboxes = {}

            metrics = compute_control_surface_metrics(
                geom, semi_span, root_chord, tip_chord, wing_area
            )

            tag_val = str(
                geom.get("tag") or self._component.get("name") or self._component.get("id") or ""
            )
            cs_type = str(geom.get("type") or "aileron").lower()
            sizing_mode = str(geom.get("sizing_mode", geom.get("span_mode", "ratio"))).lower()

            hinge_sweep = float(geom.get("hinge_sweep", 0.0))
            deflection = float(geom.get("deflection", 0.0))
            sym_mode = str(geom.get("symmetry_mode", "auto")).lower()

            driver_keys = self._get_driver_keys_for_mode(sizing_mode)

            self._set_property_value(self.properties_table, "tag", tag_val)
            self._set_property_combo(
                self.properties_table,
                "type",
                cs_type,
                CONTROL_SURFACE_TYPES,
                lambda val: self._on_prop_combo_changed("type", val),
            )
            self._set_property_combo(
                self.properties_table,
                "sizing_mode",
                sizing_mode,
                SIZING_DRIVER_MODES,
                lambda val: self._on_prop_combo_changed("sizing_mode", val),
            )

            self._setup_param(
                "area",
                "Area",
                metrics["area_dm2"],
                geom.get("area_expression"),
                "dm²",
                3,
                driver_keys,
            )
            self._setup_param(
                "area_ratio", "Area Ratio", metrics["area_ratio"], None, "%", 1, driver_keys
            )
            self._setup_param(
                "span_start",
                "Span start",
                metrics["span_start"],
                geom.get("span_start_expression"),
                "mm",
                2,
                driver_keys,
            )
            self._setup_param(
                "span_end",
                "Span end",
                metrics["span_end"],
                geom.get("span_end_expression"),
                "mm",
                2,
                driver_keys,
            )
            self._setup_param(
                "span_length",
                "Span length",
                metrics["span_length"],
                geom.get("span_length_expression"),
                "mm",
                2,
                driver_keys,
            )
            self._setup_param(
                "eta_start",
                "Span start fraction",
                metrics["eta_start"],
                geom.get("eta_start_expression"),
                "",
                3,
                driver_keys,
            )
            self._setup_param(
                "eta_end",
                "Span end fraction",
                metrics["eta_end"],
                geom.get("eta_end_expression"),
                "",
                3,
                driver_keys,
            )
            self._setup_param(
                "chord_fraction",
                "Chord fraction",
                metrics["chord_fraction"],
                geom.get("chord_fraction_expression"),
                "c",
                3,
                driver_keys,
            )
            self._setup_param(
                "chord",
                "Control chord",
                metrics["chord"],
                geom.get("chord_expression"),
                "mm",
                2,
                driver_keys,
            )

            hs_val = geom.get("hinge_sweep_expression") or hinge_sweep
            self._set_property_expression(
                self.properties_table,
                "hinge_sweep",
                hs_val,
                on_changed=lambda val: self._on_prop_spinbox_changed("hinge_sweep", val),
                api=self._api,
                label="Hinge sweep angle",
                unit="°",
                decimals=2,
            )

            def_val = geom.get("deflection_expression") or deflection
            self._set_property_expression(
                self.properties_table,
                "deflection",
                def_val,
                on_changed=lambda val: self._on_prop_spinbox_changed("deflection", val),
                api=self._api,
                label="Deflection angle",
                unit="°",
                decimals=2,
            )

            self._set_property_combo(
                self.properties_table,
                "symmetry_mode",
                sym_mode,
                SYMMETRY_MODES,
                lambda val: self._on_prop_combo_changed("symmetry_mode", val),
            )
        finally:
            self._loading = was_loading

    def _on_prop_spinbox_changed(self, key: str, value: Any) -> None:
        if self._loading:
            return
        geom = self._geometry()
        semi_span, root_chord, tip_chord, _wing_area = self._parent_wing_info()

        val_str = str(value).strip() if value is not None else ""
        num_val: float | None = None
        if val_str.startswith("=") or not val_str.replace(".", "", 1).replace("-", "", 1).isdigit():
            # Expression formula
            geom[f"{key}_expression"] = val_str
            if self._api is not None and getattr(self._api, "current_project", None) is not None:
                try:
                    from setuav_studio.plugins.core.expressions import ExpressionEvaluator

                    evaluator = ExpressionEvaluator()
                    scope = self._api.current_project.get_scope(api=self._api)
                    expr = val_str.lstrip("=").strip()
                    res = evaluator.evaluate(expr, scope)
                    if isinstance(res, (int, float)):
                        num_val = float(res)
                except Exception:
                    pass
        else:
            geom.pop(f"{key}_expression", None)
            with contextlib.suppress(ValueError):
                num_val = float(val_str)

        if num_val is None:
            return

        def change() -> None:
            self._apply_spinbox_change(geom, key, num_val, semi_span, root_chord, tip_chord)

        self._edit_component(f"Edit control surface {key}", change)
        self._load_properties()

    def _apply_spinbox_change(
        self,
        geometry: dict[str, Any],
        key: str,
        value: float,
        semi_span: float,
        root_chord: float,
        tip_chord: float = 100.0,
    ) -> None:
        from .control_surface_values import solve_control_surface_from_area

        if key == "area":
            driver_mode = str(geometry.get("sizing_mode", "area_chord")).lower()
            solve_control_surface_from_area(
                geometry, float(value), semi_span, root_chord, tip_chord, driver_mode
            )
        elif key in {"span_start", "span_end"}:
            geometry[key] = float(value)
            geometry[key.replace("span", "eta")] = round(float(value) / semi_span, 4)
        elif key == "span_length":
            start = float(geometry.get("span_start", 0.0))
            end = min(start + float(value), semi_span)
            geometry["span_end"] = round(end, 1)
            geometry["eta_end"] = round(end / semi_span, 4)
        elif key in {"eta_start", "eta_end"}:
            geometry[key] = float(value)
            geometry[key.replace("eta", "span")] = round(float(value) * semi_span, 1)
        elif key == "chord_fraction":
            geometry[key] = float(value)
            geometry["chord"] = round(float(value) * root_chord, 1)
        elif key == "chord":
            geometry[key] = max(float(value), 1.0)
            geometry["chord_fraction"] = round(float(value) / root_chord, 3)
        elif key in {"hinge_sweep", "deflection"}:
            geometry[key] = float(value)

    @staticmethod
    def _get_driver_keys_for_mode(sizing_mode: str) -> set[str]:
        if sizing_mode == "dimension":
            return {"span_start", "span_end", "chord"}
        if sizing_mode == "area_chord":
            return {"area", "span_start", "eta_start", "chord_fraction"}
        if sizing_mode == "area_span":
            return {"area", "span_start", "span_end", "eta_start", "eta_end"}
        return {"eta_start", "eta_end", "chord_fraction"}

    def _setup_param(
        self,
        key: str,
        label_text: str,
        current_val: float,
        raw_expr: str | None,
        unit: str,
        dec: int,
        driver_keys: set[str],
    ) -> None:
        is_driver = key in driver_keys
        target_row = -1
        for r in range(self.properties_table.rowCount()):
            if self._property_key(self.properties_table, r) == key:
                target_row = r
                break
        if target_row < 0:
            return

        label_item = self.properties_table.item(target_row, 0)
        if label_item:
            font = label_item.font()
            font.setBold(is_driver)
            label_item.setFont(font)
            if is_driver:
                label_item.setForeground(QApplication.palette().text())
            else:
                label_item.setForeground(QColor(130, 130, 130))

        if is_driver:
            val_to_pass = raw_expr if raw_expr else current_val
            self._set_property_expression(
                self.properties_table,
                key,
                val_to_pass,
                on_changed=lambda val, k=key: self._on_prop_spinbox_changed(k, val),
                api=self._api,
                label=label_text,
                unit=unit,
                decimals=dec,
            )
        else:
            from setuav_studio.ui.property_tables import format_engineering_value
            from setuav_studio.units import get_quantity_for_unit, get_unit_manager

            um = get_unit_manager()
            self.properties_table.removeCellWidget(target_row, 1)

            q_id = get_quantity_for_unit(unit)
            if q_id:
                disp_val = um.to_display(current_val, q_id)
                sym = um.get_unit_symbol(q_id)
            else:
                disp_val = current_val
                sym = unit or ""

            val_str = format_engineering_value(disp_val, dec)
            if sym:
                val_str += f" {sym}"
            val_item = self.properties_table.item(target_row, 1)
            if not val_item:
                val_item = QTableWidgetItem(val_str)
                self.properties_table.setItem(target_row, 1, val_item)
            else:
                val_item.setText(val_str)
            val_item.setForeground(QColor(130, 130, 130))
            val_item.setFlags(val_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            val_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def _set_linked_spinbox_value(self, key: str, value: float) -> None:
        spinbox = getattr(self, "_cs_spinboxes", {}).get(key)
        if spinbox is None:
            return
        spinbox.blockSignals(True)
        spinbox.setValue(value)
        spinbox.blockSignals(False)

    def _on_prop_combo_changed(self, key: str, value: str) -> None:
        if self._loading:
            return
        geom = self._geometry()

        def change() -> None:
            geom[key] = value

        self._edit_component(f"Edit control surface {key}", change)
        self._load_properties()

    def _update_property_cell(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.properties_table, row)
        val_str = self._property_text(self.properties_table, row).strip()
        if key == "tag":
            geom = self._geometry()

            def change() -> None:
                geom["tag"] = val_str
                self._component["name"] = val_str

            self._edit_component("Rename control surface tag", change)

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

    def _edit_component(self, action_name: str, mutation: Callable[[], None]) -> None:
        if hasattr(self._api, "edit_component"):
            self._api.edit_component(self._component, action_name, mutation)
        else:
            mutation()

    def _set_property_spinbox(
        self,
        table: QTableWidget,
        key: str,
        value: float,
        *,
        min_val: float = -1e6,
        max_val: float = 1e6,
        step: float = 1.0,
        decimals: int = 2,
        suffix: str = "",
        on_changed: Callable[[float], None] | None = None,
    ) -> NumericSpinBox | None:
        for row in range(table.rowCount()):
            if self._property_key(table, row) != key:
                continue
            return set_table_spinbox(
                table,
                row,
                1,
                value,
                min_val=min_val,
                max_val=max_val,
                step=step,
                decimals=decimals,
                suffix=suffix,
                on_changed=on_changed,
            )
        return None

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
            combo.currentIndexChanged.connect(
                lambda _i, combo=combo: on_changed(str(combo.currentData()))
            )
            table.setCellWidget(row, 1, combo)
            return
