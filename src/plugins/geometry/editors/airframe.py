"""Airframe fixed root component property editor."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api import StudioAPI
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.table import PropertyTableMixin


class AirframeEditor(PropertyTableMixin, QWidget):
    """Read-only property editor for the fixed Airframe root component."""

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

        container = QWidget()
        self._main_layout = QVBoxLayout(container)
        self._main_layout.setContentsMargins(12, 12, 12, 12)
        self._main_layout.setSpacing(16)

        self._build_header()
        self._build_general_section()
        self._build_structure_section()
        self._build_metrics_section()

        self._main_layout.addStretch()
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._load_airframe()

    def _build_header(self) -> None:
        header = QFrame()
        header.setObjectName("editor_header")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        title = QLabel("Airframe")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        subtitle = QLabel(
            "Fixed root assembly for airframe geometry (fuselages, wings, control surfaces)"
        )
        subtitle.setStyleSheet("color: #888888; font-size: 11px;")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        self._main_layout.addWidget(header)

    def _create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout:
        section = QFrame()
        section.setObjectName("editor_section")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QLabel(title)
        header.setStyleSheet("font-weight: bold; font-size: 12px;")
        if icon_name:
            set_label_icon(header, icon_name)
        layout.addWidget(header)
        self._main_layout.addWidget(section)
        return layout

    def _build_general_section(self) -> None:
        layout = self._create_section("General Information", "fa6s.circle-info")
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
                ("fuselages", "Fuselages"),
                ("wings", "Lifting Surfaces"),
                ("control_surfaces", "Control Surfaces"),
            ]
        )
        layout.addWidget(self.structure_table)

    def _build_metrics_section(self) -> None:
        layout = self._create_section("Reference Metrics", "fa6s.ruler-combined")
        self.metrics_table = self._property_table(
            [
                ("total_mass", "Total Airframe Mass"),
                ("max_span", "Max Wingspan"),
                ("primary_fuselage_length", "Primary Fuselage Length"),
            ]
        )
        layout.addWidget(self.metrics_table)

    def _load_airframe(self) -> None:
        self._loading = True
        try:
            self._set_property_value(
                self.general_table,
                "name",
                str(self._component.get("name") or "Airframe"),
                editable=False,
            )
            self._set_property_value(
                self.general_table,
                "type",
                str(self._component.get("type") or "org.setuav.core:airframe"),
                editable=False,
            )
            self._set_property_value(
                self.general_table, "status", "Fixed Root Component (Read-Only)", editable=False
            )

            project = self._api.current_project
            components: list[dict[str, Any]] = (
                [c for c in project.data.get("components", []) if isinstance(c, dict)]
                if project is not None
                else []
            )

            fuselages = [c for c in components if c.get("type") == "org.setuav.core:fuselage"]
            wings = [c for c in components if c.get("type") == "org.setuav.core:lifting-surface"]
            ctrl_surfaces = [
                c for c in components if c.get("type") == "org.setuav.core:control-surface"
            ]

            fuse_names = ", ".join(str(f.get("name") or f.get("id")) for f in fuselages) or "None"
            wing_names = ", ".join(str(w.get("name") or w.get("id")) for w in wings) or "None"
            ctrl_names = (
                ", ".join(str(cs.get("name") or cs.get("id")) for cs in ctrl_surfaces) or "None"
            )

            self._set_property_value(
                self.structure_table,
                "fuselages",
                f"{len(fuselages)} ({fuse_names})",
                editable=False,
            )
            self._set_property_value(
                self.structure_table, "wings", f"{len(wings)} ({wing_names})", editable=False
            )
            self._set_property_value(
                self.structure_table,
                "control_surfaces",
                f"{len(ctrl_surfaces)} ({ctrl_names})",
                editable=False,
            )

            # Mass calculation (sum of all geometry components under airframe)
            total_mass = sum(
                float(c.get("mass") or 0.0) for c in (*fuselages, *wings, *ctrl_surfaces)
            )
            self._set_property_value(
                self.metrics_table, "total_mass", f"{total_mass:.1f} g", editable=False
            )

            # Max wingspan calculation
            max_span = 0.0
            for w in wings:
                params = w.get("parameters", {})
                geom = params.get("geometry", {}) if isinstance(params, dict) else {}
                profiles = geom.get("profiles", []) if isinstance(geom, dict) else []
                span_y = max(
                    (
                        float(p.get("position", {}).get("y", 0.0))
                        for p in profiles
                        if isinstance(p, dict)
                    ),
                    default=0.0,
                )
                if geom.get("mirror") or geom.get("symmetric"):
                    span_y *= 2.0
                max_span = max(max_span, span_y)

            span_display = f"{max_span / 1000.0:.3f} m" if max_span > 0 else "-"
            self._set_property_value(self.metrics_table, "max_span", span_display, editable=False)

            # Fuselage length
            fuse_len = 0.0
            if fuselages:
                prim = fuselages[0]
                env = prim.get("envelope", {})
                size = env.get("size_mm", {}) if isinstance(env, dict) else {}
                fuse_len = float(size.get("x", 0.0))
            fuse_display = f"{fuse_len / 1000.0:.3f} m" if fuse_len > 0 else "-"
            self._set_property_value(
                self.metrics_table, "primary_fuselage_length", fuse_display, editable=False
            )
        finally:
            self._loading = False


__all__ = ["AirframeEditor"]
