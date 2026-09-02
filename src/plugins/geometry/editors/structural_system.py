"""Structural / Airframe System assembly property editor styled after Setuav standards."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.widget.table import PropertyTableMixin
from setuav_studio_sdk import StudioAPI


class StructuralSystemEditor(PropertyTableMixin, QWidget):
    """Property editor for structural-system assemblies."""

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
        self._create_members_section()
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

    def _create_members_section(self) -> None:
        layout = self._create_section("Airframe Members", "fa6s.link")
        self.members_table = self._property_table(
            [
                ("fuselage", "Fuselage"),
                ("main_wing", "Main Wing"),
                ("horizontal_tail", "Horizontal Tail"),
                ("vertical_tail", "Vertical Tail"),
                ("canard", "Canard"),
            ]
        )
        layout.addWidget(self.members_table)

    def _create_metrics_section(self) -> None:
        layout = self._create_section("Airframe Reference Metrics", "fa6s.ruler-combined")
        self.metrics_table = self._property_table(
            [
                ("wing_span", "Wing Span (b)"),
                ("wing_area", "Reference Area (S_ref)"),
                ("aspect_ratio", "Aspect Ratio (AR)"),
                ("mac", "Mean Aero Chord (MAC)"),
                ("fuselage_length", "Fuselage Length"),
                ("htail_volume", "HTail Volume Ratio (Vh)"),
                ("vtail_volume", "VTail Volume Ratio (Vv)"),
                ("total_mass", "Estimated Airframe Mass"),
            ]
        )
        layout.addWidget(self.metrics_table)

    def _load_assembly(self) -> None:
        self._loading = True
        try:
            self._set_property_value(
                self.general_table, "name", self._assembly.get("name", "Structural System")
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
                (c["id"], c.get("name", c["id"]))
                for c in components
                if c.get("type") == "org.setuav.core:lifting-surface"
            ]

            none_opt = [("", "-- None --")]

            members = self._assembly.get("members", {})
            fuse_id = str(members.get("fuselage") or "")
            wing_id = str(members.get("main_wing") or "")
            htail_id = str(members.get("horizontal_tail") or "")
            vtail_id = str(members.get("vertical_tail") or "")
            canard_id = str(members.get("canard") or "")

            self._set_property_combo(
                self.members_table,
                "fuselage",
                fuse_id,
                none_opt + [(f[0], f[1]) for f in fuselages],
                lambda val: self._on_member_changed("fuselage", val),
            )
            self._set_property_combo(
                self.members_table,
                "main_wing",
                wing_id,
                none_opt + [(w[0], w[1]) for w in wings],
                lambda val: self._on_member_changed("main_wing", val),
            )
            self._set_property_combo(
                self.members_table,
                "horizontal_tail",
                htail_id,
                none_opt + [(w[0], w[1]) for w in wings],
                lambda val: self._on_member_changed("horizontal_tail", val),
            )
            self._set_property_combo(
                self.members_table,
                "vertical_tail",
                vtail_id,
                none_opt + [(w[0], w[1]) for w in wings],
                lambda val: self._on_member_changed("vertical_tail", val),
            )
            self._set_property_combo(
                self.members_table,
                "canard",
                canard_id,
                none_opt + [(w[0], w[1]) for w in wings],
                lambda val: self._on_member_changed("canard", val),
            )

            self._compute_and_display_metrics(components, members)
        finally:
            self._loading = False

    def _compute_and_display_metrics(
        self, components: list[dict[str, Any]], members: dict[str, Any]
    ) -> None:
        by_id = {c.get("id"): c for c in components}

        main_wing = by_id.get(members.get("main_wing"))
        fuselage = by_id.get(members.get("fuselage"))
        htail = by_id.get(members.get("horizontal_tail"))
        vtail = by_id.get(members.get("vertical_tail"))

        b, s_ref, ar, mac, wing_x = self._compute_wing_metrics(main_wing)
        fuse_len = self._compute_fuselage_length(fuselage)
        vh_str = self._compute_htail_volume(htail, s_ref, mac, wing_x)
        vv_str = self._compute_vtail_volume(vtail, s_ref, b, wing_x)
        total_m = sum(
            float(c.get("mass", 0.0) or 0.0) for c in (main_wing, fuselage, htail, vtail) if c
        )

        self._set_property_value(
            self.metrics_table, "wing_span", f"{b:.3f} m" if b > 0 else "-", editable=False
        )
        self._set_property_value(
            self.metrics_table, "wing_area", f"{s_ref:.3f} m²" if s_ref > 0 else "-", editable=False
        )
        self._set_property_value(
            self.metrics_table, "aspect_ratio", f"{ar:.2f}" if ar > 0 else "-", editable=False
        )
        self._set_property_value(
            self.metrics_table, "mac", f"{mac:.3f} m" if mac > 0 else "-", editable=False
        )
        self._set_property_value(
            self.metrics_table,
            "fuselage_length",
            f"{fuse_len:.3f} m" if fuse_len > 0 else "-",
            editable=False,
        )
        self._set_property_value(self.metrics_table, "htail_volume", vh_str, editable=False)
        self._set_property_value(self.metrics_table, "vtail_volume", vv_str, editable=False)
        self._set_property_value(
            self.metrics_table,
            "total_mass",
            f"{total_m:.3f} kg" if total_m > 0 else "-",
            editable=False,
        )

    def _compute_wing_metrics(
        self, main_wing: dict[str, Any] | None
    ) -> tuple[float, float, float, float, float]:
        if not main_wing:
            return 0.0, 0.0, 0.0, 0.0, 0.0
        wing_params = main_wing.get("parameters", {})
        b_mm = float(wing_params.get("wingspan", 0.0))
        b = b_mm / 1000.0 if b_mm > 0 else 0.0
        root_c = float(wing_params.get("root_chord", 0.0)) / 1000.0
        tip_c = float(wing_params.get("tip_chord", 0.0)) / 1000.0
        s_ref, ar, mac = 0.0, 0.0, 0.0
        if b > 0 and (root_c > 0 or tip_c > 0):
            s_ref = b * (root_c + tip_c) / 2.0
            ar = (b * b) / s_ref if s_ref > 0 else 0.0
            mac = (root_c + tip_c) / 2.0
        transform = main_wing.get("transform", {})
        wing_x = float(transform.get("translation", [0.0, 0.0, 0.0])[0]) / 1000.0
        return b, s_ref, ar, mac, wing_x

    def _compute_fuselage_length(self, fuselage: dict[str, Any] | None) -> float:
        if not fuselage:
            return 0.0
        fuse_params = fuselage.get("parameters", {})
        sections = fuse_params.get("sections", [])
        if not sections:
            return 0.0
        x_vals = [float(s.get("x", 0.0)) for s in sections if isinstance(s, dict)]
        return (max(x_vals) - min(x_vals)) / 1000.0 if x_vals else 0.0

    def _compute_htail_volume(
        self, htail: dict[str, Any] | None, s_ref: float, mac: float, wing_x: float
    ) -> str:
        if not htail or s_ref <= 0 or mac <= 0:
            return "-"
        ht_params = htail.get("parameters", {})
        ht_b = float(ht_params.get("wingspan", 0.0)) / 1000.0
        ht_rc = float(ht_params.get("root_chord", 0.0)) / 1000.0
        ht_tc = float(ht_params.get("tip_chord", 0.0)) / 1000.0
        s_ht = ht_b * (ht_rc + ht_tc) / 2.0
        ht_x = float(htail.get("transform", {}).get("translation", [0.0, 0.0, 0.0])[0]) / 1000.0
        l_ht = abs(ht_x - wing_x)
        return f"{(s_ht * l_ht) / (s_ref * mac):.3f}" if l_ht > 0 else "-"

    def _compute_vtail_volume(
        self, vtail: dict[str, Any] | None, s_ref: float, b: float, wing_x: float
    ) -> str:
        if not vtail or s_ref <= 0 or b <= 0:
            return "-"
        vt_params = vtail.get("parameters", {})
        vt_b = float(vt_params.get("wingspan", 0.0)) / 1000.0
        vt_rc = float(vt_params.get("root_chord", 0.0)) / 1000.0
        vt_tc = float(vt_params.get("tip_chord", 0.0)) / 1000.0
        s_vt = vt_b * (vt_rc + vt_tc) / 2.0
        vt_x = float(vtail.get("transform", {}).get("translation", [0.0, 0.0, 0.0])[0]) / 1000.0
        l_vt = abs(vt_x - wing_x)
        return f"{(s_vt * l_vt) / (s_ref * b):.3f}" if l_vt > 0 else "-"

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

    def _on_member_changed(self, role: str, member_id: str) -> None:
        if self._loading:
            return

        def apply_members() -> None:
            members = self._assembly.setdefault("members", {})
            if not member_id:
                members.pop(role, None)
            else:
                members[role] = member_id

        self._api.edit_component(
            self._assembly,
            f"Update {role} in {self._assembly.get('name', 'assembly')}",
            apply_members,
        )
        self._load_assembly()


__all__ = ["StructuralSystemEditor"]
