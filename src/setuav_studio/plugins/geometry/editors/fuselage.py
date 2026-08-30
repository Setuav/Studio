import contextlib
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.buttons import set_native_button
from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.numeric_spinbox import (
    NoWheelComboBox,
    NumericSpinBox,
    set_table_spinbox,
)
from setuav_studio.ui.property_tables import ExpressionPropertyCell, PropertyTableMixin
from setuav_studio_sdk import StudioAPI

from ..engine.fuselage_geometry import (
    FUSELAGE_PROFILE_TYPES,
    create_default_section,
    create_default_segment,
    get_default_profile,
)
from .fuselage_section_dialog import FuselageSectionDialog


class FuselageEditor(PropertyTableMixin, QWidget):
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

        self._load_component()

    def _on_units_changed(self) -> None:
        if not hasattr(self, "sections_table"):
            return
        self._populate_sections()
        if self._section_index >= 0:
            self._load_section(self._section_index)

    def _create_general_section(self) -> None:
        layout = self._create_section("General", "fa6s.circle-info")
        self.general_table = self._property_table([("name", "Name"), ("type", "Type")])
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _create_segments_section(self) -> None:
        layout = self._create_section("Segments", "fa6s.layer-group")

        self.segments_table = self._table(["Tag", "Sections", "Method", "Parameterization"])
        self.segments_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.segments_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.segments_table.setColumnWidth(1, 58)
        self.segments_table.currentCellChanged.connect(self._on_segment_selected)
        self.segments_table.cellChanged.connect(self._update_segment_cell)
        layout.addWidget(self.segments_table)

        segment_actions = QHBoxLayout()
        segment_actions.setContentsMargins(0, 2, 0, 2)
        segment_actions.setSpacing(2)
        self.add_segment_button = self._action_button("add", "Add segment", self._add_segment)
        self.duplicate_segment_button = self._action_button(
            "instance", "Duplicate segment", self._duplicate_segment
        )
        self.move_segment_up_button = self._action_button(
            "fa6s.arrow-up", "Move segment up", self._move_segment_up
        )
        self.move_segment_down_button = self._action_button(
            "fa6s.arrow-down", "Move segment down", self._move_segment_down
        )
        self.delete_segment_button = self._action_button(
            "remove", "Delete segment", self._delete_segment
        )
        for button in (
            self.add_segment_button,
            self.duplicate_segment_button,
            self.move_segment_up_button,
            self.move_segment_down_button,
            self.delete_segment_button,
        ):
            segment_actions.addWidget(button)
        segment_actions.addStretch()
        layout.addLayout(segment_actions)

    def _create_sections_section(self) -> None:
        layout = self._create_section("Sections", "mdi6.vector-polygon")

        self.sections_table = self._table(["#", "Profile", "X", "Size"])
        self.sections_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.sections_table.setColumnWidth(0, 32)
        self.sections_table.currentCellChanged.connect(self._on_section_selected)
        self.sections_table.doubleClicked.connect(self._on_section_double_clicked)
        layout.addWidget(self.sections_table)

        section_actions = QHBoxLayout()
        section_actions.setContentsMargins(0, 2, 0, 2)
        section_actions.setSpacing(2)
        self.inspect_section_button = self._action_button(
            "mdi6.eye-outline", "Inspect & Edit 2D Cross-Section...", self._inspect_section
        )
        set_native_button(self.inspect_section_button, "mdi6.eye-outline")
        self.add_section_button = self._action_button("add", "Add section", self._add_section)
        self.duplicate_section_button = self._action_button(
            "instance", "Duplicate section", self._duplicate_section
        )
        self.move_section_up_button = self._action_button(
            "fa6s.arrow-up", "Move section up", self._move_section_up
        )
        self.move_section_down_button = self._action_button(
            "fa6s.arrow-down", "Move section down", self._move_section_down
        )
        self.delete_section_button = self._action_button(
            "remove", "Delete section", self._delete_section
        )
        for button in (
            self.inspect_section_button,
            self.add_section_button,
            self.duplicate_section_button,
            self.move_section_up_button,
            self.move_section_down_button,
            self.delete_section_button,
        ):
            section_actions.addWidget(button)
        section_actions.addStretch()
        layout.addLayout(section_actions)

        transform_layout = self._create_section("Transform", "mdi6.axis-arrow")
        self.transform_table = QTableWidget(2, 3)
        self.transform_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.transform_table.setVerticalHeaderLabels(["Position", "Rotation"])
        self.transform_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.transform_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.transform_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.transform_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.transform_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.transform_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.transform_table.horizontalHeader().setFixedHeight(23)
        self.transform_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.transform_table.verticalHeader().setDefaultSectionSize(23)
        self.transform_table.verticalHeader().setMinimumWidth(82)
        self.transform_table.setFixedHeight(71)
        for row in range(2):
            for column in range(3):
                item = QTableWidgetItem("0.00")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.transform_table.setItem(row, column, item)
        self.transform_table.cellChanged.connect(self._update_section)
        transform_layout.addWidget(self.transform_table)

        properties_layout = self._create_section("Section Properties", "fa6s.sliders")

        self.inspect_2d_button = QPushButton("Inspect & Edit 2D Section...")
        set_native_button(self.inspect_2d_button, "mdi6.vector-polygon")
        self.inspect_2d_button.setToolTip("Open interactive 2D cross-section inspector & metrics")
        self.inspect_2d_button.clicked.connect(self._inspect_section)
        properties_layout.addWidget(self.inspect_2d_button)

        self.section_properties_table = self._property_table([])
        self.section_properties_table.cellChanged.connect(self._update_section_property)
        properties_layout.addWidget(self.section_properties_table)

        self.vertices_table = self._table(["Y", "Z", "Radius"])
        self.vertices_table.cellChanged.connect(self._update_vertices)
        properties_layout.addWidget(self.vertices_table)

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

    def _load_component(self) -> None:
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

        if self._segments():
            self.segments_table.selectRow(0)
            self._load_segment(0)
        else:
            self._update_section_actions()
        self._update_segment_actions()

    def _populate_segments(self) -> None:
        segments = self._segments()
        self.segments_table.setRowCount(len(segments))
        for row, segment in enumerate(segments):
            loft = segment.get("loft") if isinstance(segment.get("loft"), dict) else {}
            values = (
                str(segment.get("tag") or ""),
                str(len(segment.get("sections") or [])),
                str(loft.get("method") or "smooth"),
                str(loft.get("parameterization") or "centripetal"),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column != 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.segments_table.setItem(row, column, item)
            self._set_table_combo(
                self.segments_table,
                row,
                2,
                values[2],
                [("auto", "Auto"), ("smooth", "Smooth"), ("ruled", "Ruled")],
                lambda value, segment_index=row: self._update_segment_choice(
                    segment_index, "method", value
                ),
            )
            self._set_table_combo(
                self.segments_table,
                row,
                3,
                values[3],
                [
                    ("uniform", "Uniform"),
                    ("chord_length", "Chord Length"),
                    ("centripetal", "Centripetal"),
                ],
                lambda value, segment_index=row: self._update_segment_choice(
                    segment_index, "parameterization", value
                ),
            )
        self._fit_table_height(self.segments_table, len(segments))

    def _load_segment(self, index: int) -> None:
        segments = self._segments()
        if not 0 <= index < len(segments):
            self._segment_index = -1
            self.sections_table.setRowCount(0)
            self._update_segment_actions()
            self._update_section_actions()
            self._publish_section_selection()
            return

        self._loading = True
        self._segment_index = index
        self._section_index = -1
        self._populate_sections()
        self._loading = False

        sections = self._sections()
        if sections:
            self.sections_table.selectRow(0)
            self._load_section(0)
        else:
            self._update_section_actions()
            self._publish_section_selection()
        self._update_segment_actions()

    def _populate_sections(self) -> None:
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        length_sym = um.get_unit_symbol("length")
        sections = self._sections()
        self.sections_table.setRowCount(len(sections))
        for row, section in enumerate(sections):
            profile = section.get("profile")
            if not isinstance(profile, dict):
                profile = {}
            position = section.get("position")
            if not isinstance(position, dict):
                position = {}
            x_raw = float(position.get("x") or 0.0)
            disp_x = um.to_display(x_raw, "length")
            disp_x_str = (
                f"{disp_x:.1f} {length_sym}"
                if abs(disp_x - round(disp_x)) > 1e-4
                else f"{disp_x:.0f} {length_sym}"
            )
            values = (
                str(row + 1),
                str(profile.get("type") or ""),
                disp_x_str,
                self._profile_size(profile),
            )
            for column, value in enumerate(values):
                self.sections_table.setItem(row, column, QTableWidgetItem(value))
        self._fit_table_height(self.sections_table, len(sections))

    def _load_section(self, index: int) -> None:
        sections = self._sections()
        if not 0 <= index < len(sections):
            self._section_index = -1
            return

        self._loading = True
        self._section_index = index
        section = sections[index]
        position = self._object(section, "position")
        rotation = self._object(section, "rotation")
        profile = self._object(section, "profile")

        self._set_transform_values(
            (
                float(position.get("x") or 0),
                float(position.get("y") or 0),
                float(position.get("z") or 0),
            ),
            (
                float(rotation.get("x", rotation.get("roll", 0)) or 0),
                float(rotation.get("y", rotation.get("pitch", 0)) or 0),
                float(rotation.get("z", rotation.get("yaw", 0)) or 0),
            ),
        )
        self._populate_section_properties(profile)
        self._populate_vertices(profile)
        self._loading = False

    def _on_segment_selected(self, row: int, _column: int, *_previous: int) -> None:
        if self._loading:
            return
        if row >= 0:
            self._load_segment(row)
        else:
            self._segment_index = -1
            self._publish_section_selection()
        self._update_segment_actions()

    def _add_segment(self) -> None:
        segments = self._segments()
        insert_at = (
            self._segment_index + 1 if 0 <= self._segment_index < len(segments) else len(segments)
        )
        new_segment = self._new_segment(segments)
        self._api.edit_component(
            self._component,
            "Add fuselage segment",
            lambda: segments.insert(insert_at, new_segment),
        )
        self._reload_segments(insert_at)

    def _duplicate_segment(self) -> None:
        segments = self._segments()
        index = self._segment_index
        if not 0 <= index < len(segments):
            return
        insert_at = index + 1
        duplicate = deepcopy(segments[index])
        source_tag = str(duplicate.get("tag") or "segment")
        duplicate["tag"] = self._unique_segment_tag(
            segments,
            f"{source_tag}-copy",
        )
        self._api.edit_component(
            self._component,
            "Duplicate fuselage segment",
            lambda: segments.insert(insert_at, duplicate),
        )
        self._reload_segments(insert_at)

    def _move_segment_up(self) -> None:
        self._move_segment(-1)

    def _move_segment_down(self) -> None:
        self._move_segment(1)

    def _move_segment(self, offset: int) -> None:
        segments = self._segments()
        source = self._segment_index
        target = source + offset
        if not 0 <= source < len(segments) or not 0 <= target < len(segments):
            return

        def change() -> None:
            segments.insert(target, segments.pop(source))

        self._api.edit_component(
            self._component,
            "Move fuselage segment",
            change,
        )
        self._reload_segments(target)

    def _delete_segment(self) -> None:
        segments = self._segments()
        index = self._segment_index
        if len(segments) <= 1 or not 0 <= index < len(segments):
            return
        self._api.edit_component(
            self._component,
            "Delete fuselage segment",
            lambda: segments.pop(index),
        )
        self._reload_segments(min(index, len(segments) - 1))

    def _reload_segments(self, selected_index: int) -> None:
        self._loading = True
        self._populate_segments()
        segments = self._segments()
        if segments:
            selected_index = min(max(selected_index, 0), len(segments) - 1)
            self.segments_table.selectRow(selected_index)
        else:
            selected_index = -1
        self._loading = False
        if selected_index >= 0:
            self._load_segment(selected_index)
        else:
            self._segment_index = -1
            self.sections_table.setRowCount(0)
            self._update_section_actions()
        self._update_segment_actions()

    def _update_segment_actions(self) -> None:
        segments = self._segments()
        index = self._segment_index
        has_segment = 0 <= index < len(segments)
        self.add_segment_button.setEnabled(True)
        self.duplicate_segment_button.setEnabled(has_segment)
        self.move_segment_up_button.setEnabled(has_segment and index > 0)
        self.move_segment_down_button.setEnabled(has_segment and index < len(segments) - 1)
        self.delete_segment_button.setEnabled(has_segment and len(segments) > 1)

    def _on_section_selected(self, row: int, _column: int, *_previous: int) -> None:
        if self._loading:
            return
        if row >= 0:
            self._load_section(row)
        else:
            self._section_index = -1
        self._update_section_actions()
        self._publish_section_selection()

    def _publish_section_selection(self) -> None:
        component_id = self._component.get("id")
        if isinstance(component_id, str) and self._segment_index >= 0 and self._section_index >= 0:
            self._api.set_section_selection(
                (component_id, self._segment_index, self._section_index)
            )
        else:
            self._api.set_section_selection(None)

    def _add_section(self) -> None:
        sections = self._sections()
        if self._current_segment() is None:
            return
        insert_at = (
            self._section_index + 1 if 0 <= self._section_index < len(sections) else len(sections)
        )
        new_section = self._new_section(sections, insert_at)
        self._api.edit_component(
            self._component,
            "Add fuselage section",
            lambda: sections.insert(insert_at, new_section),
        )
        self._reload_sections(insert_at)

    def _duplicate_section(self) -> None:
        sections = self._sections()
        index = self._section_index
        if not 0 <= index < len(sections):
            return
        insert_at = index + 1
        duplicate = deepcopy(sections[index])
        self._api.edit_component(
            self._component,
            "Duplicate fuselage section",
            lambda: sections.insert(insert_at, duplicate),
        )
        self._reload_sections(insert_at)

    def _move_section_up(self) -> None:
        self._move_section(-1)

    def _move_section_down(self) -> None:
        self._move_section(1)

    def _move_section(self, offset: int) -> None:
        sections = self._sections()
        source = self._section_index
        target = source + offset
        if not 0 <= source < len(sections) or not 0 <= target < len(sections):
            return

        def change() -> None:
            sections.insert(target, sections.pop(source))

        self._api.edit_component(
            self._component,
            "Move fuselage section",
            change,
        )
        self._reload_sections(target)

    def _delete_section(self) -> None:
        sections = self._sections()
        index = self._section_index
        if len(sections) <= 2 or not 0 <= index < len(sections):
            return
        self._api.edit_component(
            self._component,
            "Delete fuselage section",
            lambda: sections.pop(index),
        )
        self._reload_sections(min(index, len(sections) - 1))

    def _reload_sections(self, selected_index: int) -> None:
        self._loading = True
        self._populate_sections()
        sections = self._sections()
        if sections:
            selected_index = min(max(selected_index, 0), len(sections) - 1)
            self.sections_table.selectRow(selected_index)
        else:
            selected_index = -1
        self._loading = False
        if selected_index >= 0:
            self._load_section(selected_index)
        else:
            self._section_index = -1
        self._update_section_actions()

    def _update_section_actions(self) -> None:
        sections = self._sections()
        index = self._section_index
        has_segment = self._current_segment() is not None
        has_section = 0 <= index < len(sections)
        self.inspect_section_button.setEnabled(has_section)
        self.inspect_2d_button.setEnabled(has_section)
        self.add_section_button.setEnabled(has_segment)
        self.duplicate_section_button.setEnabled(has_section)
        self.move_section_up_button.setEnabled(has_section and index > 0)
        self.move_section_down_button.setEnabled(has_section and index < len(sections) - 1)
        self.delete_section_button.setEnabled(has_section and len(sections) > 2)

    def _on_section_double_clicked(self, _index: Any = None) -> None:
        self._inspect_section()

    def _inspect_section(self) -> None:
        if self._segment_index < 0 or self._section_index < 0:
            return
        segs = self._segments()
        if not (0 <= self._segment_index < len(segs)):
            return
        secs = self._sections()
        if not (0 <= self._section_index < len(secs)):
            return

        dlg = FuselageSectionDialog(
            self._api,
            self._component,
            segment_index=self._segment_index,
            section_index=self._section_index,
            parent=self,
        )
        if dlg.exec():
            self._load_component()

    @classmethod
    def _new_section(
        cls,
        sections: list[dict[str, Any]],
        insert_at: int,
    ) -> dict[str, Any]:
        x = cls._new_section_x(sections, insert_at)
        return cls._default_section(x)

    @classmethod
    def _new_segment(cls, segments: list[dict[str, Any]]) -> dict[str, Any]:
        tag = cls._unique_segment_tag(segments, "segment")
        return create_default_segment(tag=tag, x_start=0.0, x_end=100.0)

    @staticmethod
    def _unique_segment_tag(
        segments: list[dict[str, Any]],
        base: str,
    ) -> str:
        existing = {str(segment.get("tag") or "") for segment in segments}
        if base not in existing:
            return base
        suffix = 2
        while f"{base}-{suffix}" in existing:
            suffix += 1
        return f"{base}-{suffix}"

    @classmethod
    def _default_section(cls, x: float) -> dict[str, Any]:
        section = create_default_section(x, "circle")
        section["rotation"] = {"x": 0.0, "y": 0.0, "z": 0.0}
        section["skin"] = {"continuity": "curvature", "symmetry": "all"}
        return section

    @staticmethod
    def _new_section_x(sections: list[dict[str, Any]], insert_at: int) -> float:
        def x_at(index: int) -> float:
            position = sections[index].get("position")
            if not isinstance(position, dict):
                return 0.0
            try:
                return float(position.get("x") or 0)
            except (TypeError, ValueError):
                return 0.0

        has_previous = insert_at > 0
        has_next = insert_at < len(sections)
        if has_previous and has_next:
            return (x_at(insert_at - 1) + x_at(insert_at)) / 2
        if has_previous:
            return x_at(insert_at - 1) + 100.0
        if has_next:
            return x_at(insert_at) - 100.0
        return 0.0

    def _update_general(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return

        key = self._property_key(self.general_table, row)
        value = self._property_text(self.general_table, row)
        if key != "name":
            return

        def change() -> None:
            if key == "name":
                self._component["name"] = value.strip()

        self._api.edit_component(self._component, "Edit fuselage properties", change)

    def _update_segment_cell(self, row: int, column: int) -> None:
        segments = self._segments()
        if self._loading or column != 0 or not 0 <= row < len(segments):
            return
        item = self.segments_table.item(row, column)
        if item is None:
            return
        segment = segments[row]
        value = item.text().strip()
        self._api.edit_component(
            self._component,
            "Edit fuselage segment",
            lambda: segment.__setitem__("tag", value),
        )

    def _change_profile_type(self, profile_type: str) -> None:
        section = self._current_section()
        if self._loading or section is None:
            return

        self._api.edit_component(
            self._component,
            "Change fuselage profile",
            lambda: section.__setitem__("profile", self._default_profile(profile_type)),
        )
        self._load_section(self._section_index)
        self._populate_sections()
        self.sections_table.selectRow(self._section_index)

    def _update_segment_choice(self, index: int, key: str, value: str) -> None:
        segments = self._segments()
        allowed = {
            "method": {"auto", "smooth", "ruled"},
            "parameterization": {"uniform", "chord_length", "centripetal"},
        }
        if self._loading or not 0 <= index < len(segments) or value not in allowed.get(key, set()):
            return
        segment = segments[index]

        def change() -> None:
            loft = self._object(segment, "loft")
            loft[key] = value
            loft["profile_correspondence"] = "cardinal_quadrants"

        self._api.edit_component(self._component, "Edit fuselage segment", change)

    def _update_section(self, *_args: object) -> None:
        section = self._current_section()
        if self._loading or section is None:
            return

        transform_values = self._transform_values()
        if transform_values is None:
            self._load_section(self._section_index)
            return
        position_values, rotation_values = transform_values

        def change() -> None:
            section["position"] = {
                "x": position_values[0],
                "y": position_values[1],
                "z": position_values[2],
            }
            section["rotation"] = {
                "x": rotation_values[0],
                "y": rotation_values[1],
                "z": rotation_values[2],
            }

        self._api.edit_component(self._component, "Edit section transform", change)
        self._refresh_section_row()

    def _update_section_property(self, row: int, column: int) -> None:
        section = self._current_section()
        if self._loading or section is None or column != 1:
            return
        key = self._property_key(self.section_properties_table, row)
        value = self._property_text(self.section_properties_table, row).strip()
        profile = self._object(section, "profile")

        if key == "type":
            if value not in self.PROFILE_TYPES:
                self._load_section(self._section_index)
                return
            self._change_profile_type(value)
            return
        if key == "orientation":
            if value not in {"up", "down"}:
                self._load_section(self._section_index)
                return
            converted: str | float = value
        elif key == "vertices":
            return
        else:
            number = self._parse_number(value)
            if number is None or number < 0:
                self._load_section(self._section_index)
                return
            converted = number

        self._api.edit_component(
            self._component,
            "Edit section profile",
            lambda: profile.__setitem__(key, converted),
        )
        self._refresh_section_row()

    def _update_section_choice(self, key: str, value: str) -> None:
        if self._loading:
            return
        if key == "type":
            if value in self.PROFILE_TYPES:
                self._change_profile_type(value)
            return
        if key != "orientation" or value not in {"up", "down"}:
            return

        section = self._current_section()
        if section is None:
            return
        profile = self._object(section, "profile")
        self._api.edit_component(
            self._component,
            "Edit section profile",
            lambda: profile.__setitem__(key, value),
        )
        self._refresh_section_row()

    def _set_transform_values(
        self,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float],
    ) -> None:
        for column, value in enumerate(position):
            set_table_spinbox(
                self.transform_table,
                0,
                column,
                value,
                step=5.0,
                decimals=2,
                quantity="length",
                suffix="mm",
                on_changed=lambda _v: self._update_section(0, 0),
            )
        for column, value in enumerate(rotation):
            set_table_spinbox(
                self.transform_table,
                1,
                column,
                value,
                min_val=-360.0,
                max_val=360.0,
                step=1.0,
                decimals=2,
                quantity="angle",
                suffix="°",
                on_changed=lambda _v: self._update_section(1, 0),
            )

    def _transform_values(
        self,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
        rows: list[tuple[float, float, float]] = []
        for row in range(2):
            vals: list[float] = []
            for column in range(3):
                w = self.transform_table.cellWidget(row, column)
                if isinstance(w, (QDoubleSpinBox, ExpressionPropertyCell)):
                    vals.append(float(w.value()))
                else:
                    item = self.transform_table.item(row, column)
                    try:
                        vals.append(float(item.text()) if item is not None else 0.0)
                    except (AttributeError, ValueError):
                        return None
            rows.append(tuple(vals))
        return rows[0], rows[1]

    def _update_vertices(self, row: int, column: int) -> None:
        if self._loading:
            return
        section = self._current_section()
        if section is None:
            return
        profile = self._object(section, "profile")
        vertices = profile.get("vertices")
        if not isinstance(vertices, list) or not 0 <= row < len(vertices):
            return
        w = self.vertices_table.cellWidget(row, column)
        if isinstance(w, (QDoubleSpinBox, ExpressionPropertyCell)):
            value = float(w.value())
        else:
            item = self.vertices_table.item(row, column)
            try:
                value = float(item.text()) if item is not None else 0.0
            except ValueError:
                return
        key = ("y", "z", "radius")[column]
        if isinstance(vertices[row], dict):
            self._api.edit_component(
                self._component,
                "Edit polygon vertex",
                lambda: vertices[row].__setitem__(key, value),
            )

    def _populate_section_properties(self, profile: dict[str, Any]) -> None:
        profile_type = str(profile.get("type") or "circle")
        fields: dict[str, list[tuple[str, str]]] = {
            "circle": [("diameter", "Diameter")],
            "ellipse": [("width", "Width"), ("height", "Height")],
            "rectangle": [
                ("width", "Width"),
                ("height", "Height"),
                ("corner_radius", "Corner radius"),
            ],
            "trapezoid": [
                ("top_width", "Top width"),
                ("bottom_width", "Bottom width"),
                ("height", "Height"),
                ("corner_radius", "Corner radius"),
            ],
            "triangle": [
                ("base_width", "Base width"),
                ("height", "Height"),
                ("orientation", "Orientation"),
                ("corner_radius", "Corner radius"),
            ],
            "polygon": [("vertices", "Vertices")],
        }
        definitions = [("type", "Profile"), *fields.get(profile_type, [])]
        self._configure_property_table(self.section_properties_table, definitions)
        for key, _label in definitions:
            if key == "type":
                continue
            elif key == "vertices":
                value = len(profile.get("vertices") or [])
                self._set_property_value(
                    self.section_properties_table,
                    key,
                    str(value),
                    editable=False,
                )
            elif key in (
                "diameter",
                "width",
                "height",
                "top_width",
                "bottom_width",
                "base_width",
                "corner_radius",
                "fillet_radius",
            ):
                raw_val = profile.get(f"{key}_expression") or profile.get(key, 0.0)
                self._set_property_expression(
                    self.section_properties_table,
                    key,
                    raw_val,
                    on_changed=lambda v, k=key: self._on_property_expression_changed(k, v),
                    api=self._api,
                    label=_label,
                    unit="mm",
                )
            else:
                self._set_property_value(
                    self.section_properties_table,
                    key,
                    profile.get(key, 0),
                )
        self._set_property_combo(
            self.section_properties_table,
            "type",
            profile_type,
            [(value, value.replace("_", " ").title()) for value in self.PROFILE_TYPES],
            lambda value: self._update_section_choice("type", value),
        )
        if profile_type == "triangle":
            self._set_property_combo(
                self.section_properties_table,
                "orientation",
                str(profile.get("orientation") or "up"),
                [("up", "Up"), ("down", "Down")],
                lambda value: self._update_section_choice("orientation", value),
            )

    def _on_property_expression_changed(self, key: str, value: Any) -> None:
        if self._loading:
            return
        section = self._current_section()
        if section is None:
            return
        profile = self._object(section, "profile")
        val_str = str(value).strip() if value is not None else ""

        num_val: float | None = None
        if val_str.startswith("=") or not val_str.replace(".", "", 1).replace("-", "", 1).isdigit():
            # Expression
            profile[f"{key}_expression"] = val_str
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
            profile.pop(f"{key}_expression", None)
            with contextlib.suppress(ValueError):
                num_val = float(val_str)

        if num_val is not None:
            profile[key] = num_val

            def change() -> None:
                pass

            self._api.edit_component(
                self._component,
                f"Change fuselage section {key}",
                change,
            )
            self._update_sections_table()
        self.vertices_table.setVisible(profile.get("type") == "polygon")

    def _on_property_spin_changed(self, key: str, value: float) -> None:
        if self._loading:
            return
        section = self._current_section()
        if section is None:
            return
        profile = self._object(section, "profile")
        self._api.edit_component(
            self._component,
            "Edit section profile",
            lambda: profile.__setitem__(key, float(value)),
        )
        self._refresh_section_row()

    def _populate_vertices(self, profile: dict[str, Any]) -> None:
        vertices = profile.get("vertices")
        if not isinstance(vertices, list):
            vertices = []
        self.vertices_table.setRowCount(len(vertices))
        for row, vertex in enumerate(vertices):
            if not isinstance(vertex, dict):
                continue
            set_table_spinbox(
                self.vertices_table,
                row,
                0,
                float(vertex.get("y") or 0.0),
                step=1.0,
                decimals=2,
                suffix="mm",
                on_changed=lambda val, r=row: self._on_vertex_spin_changed(r, 0, val),
            )
            set_table_spinbox(
                self.vertices_table,
                row,
                1,
                float(vertex.get("z") or 0.0),
                step=1.0,
                decimals=2,
                suffix="mm",
                on_changed=lambda val, r=row: self._on_vertex_spin_changed(r, 1, val),
            )
            set_table_spinbox(
                self.vertices_table,
                row,
                2,
                float(vertex.get("radius") or 0.0),
                min_val=0.0,
                step=0.5,
                decimals=2,
                suffix="mm",
                on_changed=lambda val, r=row: self._on_vertex_spin_changed(r, 2, val),
            )
        self._fit_table_height(self.vertices_table, len(vertices))

    def _on_vertex_spin_changed(self, row: int, column: int, value: float) -> None:
        if self._loading:
            return
        section = self._current_section()
        if section is None:
            return
        profile = self._object(section, "profile")
        vertices = profile.get("vertices")
        if not isinstance(vertices, list) or not 0 <= row < len(vertices):
            return
        key = ("y", "z", "radius")[column]
        if isinstance(vertices[row], dict):
            self._api.edit_component(
                self._component,
                "Edit polygon vertex",
                lambda: vertices[row].__setitem__(key, float(value)),
            )

    def _refresh_section_row(self) -> None:
        section = self._current_section()
        if section is None:
            return
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        length_sym = um.get_unit_symbol("length")
        position = section.get("position") if isinstance(section.get("position"), dict) else {}
        profile = section.get("profile") if isinstance(section.get("profile"), dict) else {}
        row = self._section_index
        x_raw = float(position.get("x") or 0.0)
        disp_x = um.to_display(x_raw, "length")
        disp_x_str = (
            f"{disp_x:.1f} {length_sym}"
            if abs(disp_x - round(disp_x)) > 1e-4
            else f"{disp_x:.0f} {length_sym}"
        )
        self.sections_table.item(row, 1).setText(str(profile.get("type") or ""))
        self.sections_table.item(row, 2).setText(disp_x_str)
        self.sections_table.item(row, 3).setText(self._profile_size(profile))

    def _parameters(self) -> dict[str, Any]:
        return self._object(self._component, "parameters")

    def _segments(self) -> list[dict[str, Any]]:
        geometry = self._parameters().get("geometry")
        if not isinstance(geometry, dict):
            return []
        segments = geometry.get("segments")
        if not isinstance(segments, list) or not all(
            isinstance(segment, dict) for segment in segments
        ):
            return []
        return segments

    def _sections(self) -> list[dict[str, Any]]:
        segment = self._current_segment()
        if segment is None:
            return []
        sections = segment.get("sections")
        if not isinstance(sections, list) or not all(
            isinstance(section, dict) for section in sections
        ):
            return []
        return sections

    def _current_segment(self) -> dict[str, Any] | None:
        segments = self._segments()
        if 0 <= self._segment_index < len(segments):
            return segments[self._segment_index]
        return None

    def _current_section(self) -> dict[str, Any] | None:
        sections = self._sections()
        if 0 <= self._section_index < len(sections):
            return sections[self._section_index]
        return None

    @staticmethod
    def _object(owner: dict[str, Any], key: str) -> dict[str, Any]:
        value = owner.get(key)
        if not isinstance(value, dict):
            value = {}
            owner[key] = value
        return value

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

    @staticmethod
    def _profile_size(profile: dict[str, Any]) -> str:
        from setuav_studio.units import get_unit_manager

        um = get_unit_manager()
        profile_type = profile.get("type")
        length_sym = um.get_unit_symbol("length")

        def _fmt(val: Any) -> str:
            try:
                num = float(val or 0.0)
                disp = um.to_display(num, "length")
                return f"{disp:.1f}" if abs(disp - round(disp)) > 1e-4 else f"{disp:.0f}"
            except (ValueError, TypeError):
                return str(val)

        if profile_type == "circle":
            return f"D {_fmt(profile.get('diameter', 0))} {length_sym}"
        if profile_type in {"ellipse", "rectangle"}:
            return f"{_fmt(profile.get('width', 0))} × {_fmt(profile.get('height', 0))} {length_sym}"
        if profile_type == "trapezoid":
            return f"{_fmt(profile.get('top_width', 0))} / {_fmt(profile.get('bottom_width', 0))} {length_sym}"
        if profile_type == "triangle":
            return f"{_fmt(profile.get('base_width', 0))} × {_fmt(profile.get('height', 0))} {length_sym}"
        if profile_type == "polygon":
            return f"{len(profile.get('vertices') or [])} vertices"
        return ""

    @staticmethod
    def _default_profile(profile_type: str) -> dict[str, Any]:
        return get_default_profile(profile_type)
