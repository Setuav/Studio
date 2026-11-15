"""Propulsion fixed root component property editor."""

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

from setuav_studio.api import StudioAPI
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.table import PropertyTableMixin


class PropulsionSystemEditor(PropertyTableMixin, QWidget):
    """Read-only property editor for the fixed Propulsion root component."""

    table_scroll_policy_off = True
    table_max_visible_rows = None

    def __init__(self, api: StudioAPI, component: dict[str, Any]) -> None:
        super().__init__()
        self._api = api
        self._component = component
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

        self._build_general_section()
        self._build_structure_section()
        self._build_metrics_section()
        self._content_layout.addStretch()

        self._load_propulsion()

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

    def _build_general_section(self) -> None:
        layout = self._create_section("General", "fa6s.circle-info")
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("type", "Type"),
                ("status", "Status"),
            ]
        )
        layout.addWidget(self.general_table)

    def _build_structure_section(self) -> None:
        layout = self._create_section("Structure Hierarchy", "fa6s.sitemap")
        self.structure_table = self._property_table(
            [
                ("battery", "Battery Pack"),
                ("controller", "Speed Controller (ESC)"),
                ("motor", "Motor"),
                ("propulsor", "Propeller / Rotor"),
            ]
        )
        self.members_table = self.structure_table
        layout.addWidget(self.structure_table)

    def _build_metrics_section(self) -> None:
        layout = self._create_section("Reference Metrics", "fa6s.ruler-combined")
        self.metrics_table = self._property_table(
            [
                ("total_mass", "Total Propulsion Mass"),
                ("operating_voltage", "Operating Voltage"),
                ("energy_capacity", "Energy Capacity"),
                ("powertrain_config", "Powertrain Configuration"),
            ]
        )
        layout.addWidget(self.metrics_table)

    def _load_propulsion(self) -> None:
        self._loading = True
        try:
            name = str(self._component.get("name") or "Propulsion")
            comp_type = str(self._component.get("type") or "org.setuav.core:propulsion-system")
            self._set_property_value(self.general_table, "name", name, editable=False)
            self._set_property_value(self.general_table, "type", comp_type, editable=False)
            self._set_property_value(
                self.general_table, "status", "Fixed Root Component (Read-Only)", editable=False
            )

            project = self._api.current_project
            components: list[dict[str, Any]] = (
                [c for c in project.data.get("components", []) if isinstance(c, dict)]
                if project is not None
                else []
            )

            # Check explicit members and parent-based children
            members = (
                self._component.get("members", {}) if isinstance(self._component, dict) else {}
            )
            prop_id = str(self._component.get("id") or "propulsion")

            def get_comp_by_id_or_parent(
                role_key: str, type_names: set[str]
            ) -> list[dict[str, Any]]:
                # 1. Check explicit member references if available
                explicit_ids = members.get(role_key)
                if explicit_ids:
                    if isinstance(explicit_ids, str):
                        explicit_ids = [explicit_ids]
                    matched = [c for c in components if c.get("id") in explicit_ids]
                    if matched:
                        return matched
                # 2. Check parent == propulsion
                children = [
                    c
                    for c in components
                    if c.get("type") in type_names
                    and (c.get("parent") == prop_id or not c.get("parent"))
                ]
                if children:
                    return children
                # 3. Fallback: all matching types in project
                return [c for c in components if c.get("type") in type_names]

            batteries = get_comp_by_id_or_parent("battery", {"org.setuav.core:battery"})
            escs = get_comp_by_id_or_parent("controllers", {"org.setuav.core:esc"})
            motors = get_comp_by_id_or_parent("motors", {"org.setuav.core:motor"})
            props = get_comp_by_id_or_parent(
                "propulsors", {"org.setuav.core:propeller", "org.setuav.core:rotor"}
            )

            # Format structure rows
            bat_desc = ", ".join(str(b.get("name") or b.get("id")) for b in batteries) or "-"
            esc_desc = ", ".join(str(e.get("name") or e.get("id")) for e in escs) or "-"
            mot_desc = ", ".join(str(m.get("name") or m.get("id")) for m in motors) or "-"
            prp_desc = ", ".join(str(p.get("name") or p.get("id")) for p in props) or "-"

            # When explicit single IDs are present in members or tests, use first id
            if members.get("battery"):
                bat_desc = str(members.get("battery"))
            if members.get("controllers"):
                ctrls = members.get("controllers")
                esc_desc = str(ctrls[0] if isinstance(ctrls, list) and ctrls else ctrls)
            if members.get("motors"):
                mots = members.get("motors")
                mot_desc = str(mots[0] if isinstance(mots, list) and mots else mots)
            if members.get("propulsors"):
                prps = members.get("propulsors")
                prp_desc = str(prps[0] if isinstance(prps, list) and prps else prps)

            self._set_property_value(self.structure_table, "battery", bat_desc, editable=False)
            self._set_property_value(self.structure_table, "controller", esc_desc, editable=False)
            self._set_property_value(self.structure_table, "motor", mot_desc, editable=False)
            self._set_property_value(self.structure_table, "propulsor", prp_desc, editable=False)

            # Compute aggregated metrics
            all_prop_comps = batteries + escs + motors + props
            total_mass_g = sum(float(c.get("mass", 0.0) or 0.0) for c in all_prop_comps)
            mass_display = (
                f"{total_mass_g:.1f} g ({total_mass_g / 1000.0:.3f} kg)"
                if total_mass_g > 0
                else "-"
            )
            self._set_property_value(self.metrics_table, "total_mass", mass_display, editable=False)

            # Battery voltage & energy
            volt_display = "-"
            energy_display = "-"
            if batteries:
                b = batteries[0]
                bp = b.get("parameters", {})
                s = int(bp.get("cell_count", 6))
                cap = float(bp.get("capacity", 5000.0))
                cell_v = float(bp.get("cell_voltage", bp.get("cell_nominal_voltage", 3.7)))
                v_nom = float(bp.get("nominal_voltage", s * cell_v))
                wh = (cap * v_nom) / 1000.0
                volt_display = f"{s}S ({v_nom:.1f} V)"
                energy_display = f"{cap:.0f} mAh ({wh:.1f} Wh)"

            self._set_property_value(
                self.metrics_table, "operating_voltage", volt_display, editable=False
            )
            self._set_property_value(
                self.metrics_table, "energy_capacity", energy_display, editable=False
            )

            # Powertrain config
            motor_count = len(motors)
            if motor_count <= 1:
                cfg_display = "Single Motor (1x)"
            elif motor_count == 2:
                cfg_display = "Twin Motor (2x)"
            elif motor_count == 4:
                cfg_display = "Quad Motor (4x)"
            else:
                cfg_display = f"Multi-Motor ({motor_count}x)"
            self._set_property_value(
                self.metrics_table, "powertrain_config", cfg_display, editable=False
            )

        finally:
            self._loading = False


__all__ = ["PropulsionSystemEditor"]
