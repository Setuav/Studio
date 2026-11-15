"""Airframe fixed root component property editor."""

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


class AirframeEditor(PropertyTableMixin, QWidget):
    """Read-only property editor for the fixed Airframe root component."""

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

        self._load_airframe()

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
                ("max_span", "Max Span"),
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

            project = self._api.project
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
                if geom.get("mirror"):
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
