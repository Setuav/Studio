"""Structural / Airframe System assembly property editor aligned with Setuav airframe structure."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
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
from setuav_studio.ui.widget.table import PropertyTableMixin
from setuav_studio_sdk import StudioAPI


class StructuralSystemEditor(PropertyTableMixin, QWidget):
    """Property editor for airframe structural-system assemblies."""

    def __init__(
        self,
        api: StudioAPI,
        assembly: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._assembly = assembly
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(6, 6, 6, 8)
        self._content_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._create_general_section()
        self._create_fuselage_section()
        self._create_wings_section()
        self._create_metrics_section()

        self._content_layout.addStretch()
        self._load_assembly()

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
            ]
        )
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _create_fuselage_section(self) -> None:
        layout = self._create_section("Fuselage", "fa6s.shuttle-space")
        self.fuselage_table = self._property_table(
            [
                ("fuselage", "Primary Fuselage"),
            ]
        )
        layout.addWidget(self.fuselage_table)

    def _create_wings_section(self) -> None:
        layout = self._create_section("Wings (Lifting Surfaces)", "fa6s.plane")
        self.wings_table = QTableWidget(0, 2)
        self.wings_table.setHorizontalHeaderLabels(["Wing", "Included in Airframe"])
        self.wings_table.horizontalHeader().setStretchLastSection(True)
        self.wings_table.verticalHeader().setVisible(False)
        self.wings_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        layout.addWidget(self.wings_table)

    def _create_metrics_section(self) -> None:
        layout = self._create_section("Airframe Reference Metrics", "fa6s.ruler-combined")
        self.metrics_table = self._property_table(
            [
                ("max_span", "Max Wingspan (b)"),
                ("total_area", "Total Reference Area (S_ref)"),
                ("aspect_ratio", "Equivalent Aspect Ratio (AR)"),
                ("fuselage_length", "Fuselage Length"),
                ("total_mass", "Total Airframe Mass"),
            ]
        )
        layout.addWidget(self.metrics_table)

    def _load_assembly(self) -> None:
        self._loading = True
        try:
            self._set_property_value(
                self.general_table, "name", self._assembly.get("name", "Airframe Structure")
            )
            self._set_property_value(
                self.general_table,
                "type",
                self._assembly.get("type", "org.setuav.core:structural-system"),
                editable=False,
            )

            project = self._api.current_project
            components = project.data.get("components", []) if project else []

            fuselages = [
                (c["id"], c.get("name", c["id"]))
                for c in components
                if c.get("type") == "org.setuav.core:fuselage"
            ]
            wings = [
                c
                for c in components
                if c.get("type") == "org.setuav.core:lifting-surface"
            ]

            members = self._assembly.get("members", {})
            fuse_val = members.get("fuselage")
            fuse_id = fuse_val if isinstance(fuse_val, str) else (fuse_val[0] if isinstance(fuse_val, list) and fuse_val else "")

            # Set Fuselage combo
            none_opt = [("", "-- None --")]
            self._set_property_combo(
                self.fuselage_table,
                "fuselage",
                fuse_id or "",
                none_opt + [(f[0], f[1]) for f in fuselages],
                self._on_fuselage_changed,
            )

            # Populate Wings table with checkboxes
            assigned_wings = members.get("wings", [])
            assigned_wing_ids = set(assigned_wings) if isinstance(assigned_wings, list) else set()

            self.wings_table.setRowCount(len(wings))
            for row, wing in enumerate(wings):
                w_id = str(wing.get("id", ""))
                w_name = str(wing.get("name", w_id))

                name_item = QTableWidgetItem(w_name)
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.wings_table.setItem(row, 0, name_item)

                chk = QCheckBox()
                chk.setChecked(w_id in assigned_wing_ids)
                chk.stateChanged.connect(
                    lambda state, wid=w_id: self._on_wing_toggled(wid, state == Qt.CheckState.Checked.value)
                )

                cell_widget = QWidget()
                cell_layout = QHBoxLayout(cell_widget)
                cell_layout.addWidget(chk)
                cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                self.wings_table.setCellWidget(row, 1, cell_widget)

            self._compute_and_display_metrics(components, fuse_id, assigned_wing_ids)
        finally:
            self._loading = False

    def _compute_and_display_metrics(
        self,
        components: list[dict[str, Any]],
        fuse_id: str | None,
        assigned_wing_ids: set[str],
    ) -> None:
        by_id = {c.get("id"): c for c in components}

        # 1. Wings metrics
        total_s_ref = 0.0
        max_b = 0.0
        total_mass = 0.0

        for w_id in assigned_wing_ids:
            wing = by_id.get(w_id)
            if not wing:
                continue
            total_mass += float(wing.get("mass", 0.0) or 0.0)
            wing_params = wing.get("parameters", {})
            b_mm = float(wing_params.get("wingspan", 0.0))
            b = b_mm / 1000.0 if b_mm > 0 else 0.0
            root_c = float(wing_params.get("root_chord", 0.0)) / 1000.0
            tip_c = float(wing_params.get("tip_chord", 0.0)) / 1000.0
            if b > 0 and (root_c > 0 or tip_c > 0):
                s_ref = b * (root_c + tip_c) / 2.0
                total_s_ref += s_ref
                max_b = max(max_b, b)

        ar = (max_b * max_b) / total_s_ref if total_s_ref > 0 else 0.0

        # 2. Fuselage length and mass
        fuse_len = 0.0
        if fuse_id:
            fuselage = by_id.get(fuse_id)
            if fuselage:
                total_mass += float(fuselage.get("mass", 0.0) or 0.0)
                fuse_params = fuselage.get("parameters", {})
                sections = fuse_params.get("sections", [])
                if sections:
                    x_vals = [float(s.get("x", 0.0)) for s in sections if isinstance(s, dict)]
                    if x_vals:
                        fuse_len = (max(x_vals) - min(x_vals)) / 1000.0

        self._set_property_value(self.metrics_table, "max_span", f"{max_b:.3f} m" if max_b > 0 else "-", editable=False)
        self._set_property_value(self.metrics_table, "total_area", f"{total_s_ref:.3f} m²" if total_s_ref > 0 else "-", editable=False)
        self._set_property_value(self.metrics_table, "aspect_ratio", f"{ar:.2f}" if ar > 0 else "-", editable=False)
        self._set_property_value(self.metrics_table, "fuselage_length", f"{fuse_len:.3f} m" if fuse_len > 0 else "-", editable=False)
        self._set_property_value(self.metrics_table, "total_mass", f"{total_mass:.3f} kg" if total_mass > 0 else "-", editable=False)

    def _update_general(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return

        key = self._property_key(self.general_table, row)
        val_text = self._property_text(self.general_table, row)

        def apply_name() -> None:
            if key == "name":
                self._assembly["name"] = val_text

        self._api.edit_component(
            self._assembly,
            f"Edit {key} of {self._assembly.get('name', 'assembly')}",
            apply_name,
        )

    def _on_fuselage_changed(self, fuse_id: str) -> None:
        if self._loading:
            return

        def apply_fuse() -> None:
            members = self._assembly.setdefault("members", {})
            if not fuse_id:
                members.pop("fuselage", None)
            else:
                members["fuselage"] = fuse_id

        self._api.edit_component(
            self._assembly,
            f"Update fuselage in {self._assembly.get('name', 'assembly')}",
            apply_fuse,
        )
        self._load_assembly()

    def _on_wing_toggled(self, wing_id: str, checked: bool) -> None:
        if self._loading:
            return

        def apply_wing() -> None:
            members = self._assembly.setdefault("members", {})
            current_wings = list(members.get("wings", []))
            if checked and wing_id not in current_wings:
                current_wings.append(wing_id)
            elif not checked and wing_id in current_wings:
                current_wings.remove(wing_id)
            members["wings"] = current_wings

        self._api.edit_component(
            self._assembly,
            f"Update wings in {self._assembly.get('name', 'assembly')}",
            apply_wing,
        )
        self._load_assembly()


__all__ = ["StructuralSystemEditor"]
