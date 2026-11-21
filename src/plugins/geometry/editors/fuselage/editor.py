"""Component property editor for org.setuav.core:fuselage."""

from __future__ import annotations

import weakref
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api import StudioAPI
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.button import set_native_button
from setuav_studio.ui.widget.spinbox import NoWheelComboBox
from setuav_studio.ui.widget.table import PropertyTableMixin

from ...engine.fuselage_geometry import FUSELAGE_PROFILE_TYPES
from .general_section import GeneralSectionMixin
from .sections_section import SectionsSectionMixin
from .segments_section import SegmentsSectionMixin


class FuselageEditor(
    GeneralSectionMixin,
    SegmentsSectionMixin,
    SectionsSectionMixin,
    PropertyTableMixin,
    QWidget,
):
    """Component property editor for org.setuav.core:fuselage."""

    table_combo_cls = NoWheelComboBox
    table_scroll_policy_off = True
    table_max_visible_rows = None
    table_property_text_spinbox = True

    PROFILE_TYPES = FUSELAGE_PROFILE_TYPES

    def __init__(self, api: StudioAPI, component: dict[str, Any]) -> None:
        super().__init__()
        self._api = api
        self._component = component
        self._segment_index = -1
        self._section_index = -1
        self._loading = False
        self._suppress_content_reload = False

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
        self._create_segments_section()
        self._create_sections_section()
        self._content_layout.addStretch()

        from setuav_studio.units import get_unit_manager

        get_unit_manager().units_changed.connect(self._on_units_changed)

        self_ref = weakref.ref(self)

        def _on_content_changed(_project: Any = None) -> None:
            editor = self_ref()
            if editor is not None:
                editor._on_project_content_changed()

        self._api.on_project_content_changed(_on_content_changed)
        self.destroyed.connect(
            lambda _obj=None, a=self._api, fn=_on_content_changed: (
                a.remove_project_content_listener(fn)
            )
        )

        self._load_component()

    def _on_project_content_changed(self) -> None:
        if self._loading or self._suppress_content_reload:
            return
        self._load_component(preserve_selection=True)

    def _on_units_changed(self) -> None:
        if not hasattr(self, "sections_table"):
            return
        self._populate_sections()
        if self._section_index >= 0:
            self._load_section(self._section_index)

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

    @staticmethod
    def _action_button(
        icon_name: str,
        tooltip: str,
        callback: Callable[[], None],
    ) -> QToolButton:
        button = QToolButton()
        set_native_button(button, icon_name)
        button.setToolTip(tooltip)
        button.setFixedSize(24, 24)
        button.setAutoRaise(True)
        button.clicked.connect(callback)
        return button

    def _load_component(self, *, preserve_selection: bool = False) -> None:
        prev_seg = self._segment_index if preserve_selection else 0
        prev_sec = self._section_index if preserve_selection else 0
        self._loading = True
        self._set_property_value(self.general_table, "name", str(self._component.get("name") or ""))
        self._set_property_value(
            self.general_table,
            "type",
            str(self._component.get("type") or ""),
            editable=False,
        )
        self._populate_segments()
        self._loading = False

        segments = self._segments()
        if segments:
            seg_idx = min(max(prev_seg, 0), len(segments) - 1)
            self.segments_table.selectRow(seg_idx)
            self._load_segment(seg_idx)
            sections = self._sections()
            if sections and preserve_selection and prev_sec >= 0:
                sec_idx = min(prev_sec, len(sections) - 1)
                self.sections_table.selectRow(sec_idx)
                self._load_section(sec_idx)
        else:
            self._update_section_actions()
        self._update_segment_actions()

    def _edit_component(self, description: str, change_fn: Callable[[], Any]) -> None:
        self._suppress_content_reload = True
        try:
            self._api.edit_component(self._component, description, change_fn)
        finally:
            self._suppress_content_reload = False

    def _parameters(self) -> dict[str, Any]:
        return self._object(self._component, "parameters")

    @staticmethod
    def _object(owner: dict[str, Any], key: str) -> dict[str, Any]:
        value = owner.get(key)
        if not isinstance(value, dict):
            value = {}
            owner[key] = value
        return value
