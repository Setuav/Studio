"""Segments management section for the Fuselage Editor."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
)

from ...engine.fuselage_geometry import create_default_segment

if TYPE_CHECKING:
    from .editor import FuselageEditor


class SegmentsSectionMixin:
    """Manages fuselage longitudinal segments and method parameters."""

    def _create_segments_section(self: FuselageEditor) -> None:
        layout = self._create_section("Segments", "fa6s.layer-group")

        self.segments_table = self._table(["Tag", "Sections", "Method"])
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

    def _populate_segments(self: FuselageEditor) -> None:
        segments = self._segments()
        self.segments_table.setRowCount(len(segments))
        for row, segment in enumerate(segments):
            loft = segment.get("loft") if isinstance(segment.get("loft"), dict) else {}
            values = (
                str(segment.get("tag") or ""),
                str(len(segment.get("sections") or [])),
                str(loft.get("method") or "smooth"),
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
                [("smooth", "Smooth"), ("ruled", "Ruled")],
                lambda value, segment_index=row: self._update_segment_choice(
                    segment_index, "method", value
                ),
            )
        self._fit_table_height(self.segments_table, len(segments))

    def _load_segment(self: FuselageEditor, index: int) -> None:
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

    def _on_segment_selected(self: FuselageEditor, row: int, _column: int, *_previous: int) -> None:
        if self._loading:
            return
        if row >= 0:
            self._load_segment(row)
        else:
            self._segment_index = -1
            self._publish_section_selection()
        self._update_segment_actions()

    def _update_segment_cell(self: FuselageEditor, row: int, column: int) -> None:
        segments = self._segments()
        if self._loading or column != 0 or not 0 <= row < len(segments):
            return
        item = self.segments_table.item(row, column)
        if item is None:
            return
        segment = segments[row]
        value = item.text().strip()
        self._edit_component(
            "Edit fuselage segment",
            lambda: segment.__setitem__("tag", value),
        )

    def _update_segment_choice(self: FuselageEditor, index: int, key: str, value: str) -> None:
        segments = self._segments()
        allowed = {
            "method": {"smooth", "ruled"},
        }
        if self._loading or not 0 <= index < len(segments) or value not in allowed.get(key, set()):
            return
        segment = segments[index]

        def change() -> None:
            loft = self._object(segment, "loft")
            loft[key] = value
            loft["profile_correspondence"] = "cardinal_quadrants"

        self._edit_component("Edit fuselage segment", change)

    def _update_segment_sections_cell(self: FuselageEditor) -> None:
        if 0 <= self._segment_index < self.segments_table.rowCount():
            sections = self._sections()
            item = self.segments_table.item(self._segment_index, 1)
            if item is not None:
                item.setText(str(len(sections)))

    def _add_segment(self: FuselageEditor) -> None:
        segments = self._segments()
        insert_at = (
            self._segment_index + 1 if 0 <= self._segment_index < len(segments) else len(segments)
        )
        new_segment = self._new_segment(segments)
        self._edit_component(
            "Add fuselage segment",
            lambda: segments.insert(insert_at, new_segment),
        )
        self._reload_segments(insert_at)

    def _duplicate_segment(self: FuselageEditor) -> None:
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
        self._edit_component(
            "Duplicate fuselage segment",
            lambda: segments.insert(insert_at, duplicate),
        )
        self._reload_segments(insert_at)

    def _move_segment_up(self: FuselageEditor) -> None:
        self._move_segment(-1)

    def _move_segment_down(self: FuselageEditor) -> None:
        self._move_segment(1)

    def _move_segment(self: FuselageEditor, offset: int) -> None:
        segments = self._segments()
        source = self._segment_index
        target = source + offset
        if not 0 <= source < len(segments) or not 0 <= target < len(segments):
            return

        def change() -> None:
            segments.insert(target, segments.pop(source))

        self._edit_component(
            "Move fuselage segment",
            change,
        )
        self._reload_segments(target)

    def _delete_segment(self: FuselageEditor) -> None:
        segments = self._segments()
        index = self._segment_index
        if len(segments) <= 1 or not 0 <= index < len(segments):
            return
        self._edit_component(
            "Delete fuselage segment",
            lambda: segments.pop(index),
        )
        self._reload_segments(min(index, len(segments) - 1))

    def _reload_segments(self: FuselageEditor, selected_index: int) -> None:
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

    def _update_segment_actions(self: FuselageEditor) -> None:
        segments = self._segments()
        index = self._segment_index
        has_segment = 0 <= index < len(segments)
        self.add_segment_button.setEnabled(True)
        self.duplicate_segment_button.setEnabled(has_segment)
        self.move_segment_up_button.setEnabled(has_segment and index > 0)
        self.move_segment_down_button.setEnabled(has_segment and index < len(segments) - 1)
        self.delete_segment_button.setEnabled(has_segment and len(segments) > 1)

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

    def _segments(self: FuselageEditor) -> list[dict[str, Any]]:
        parameters = self._parameters()
        geometry = parameters.get("geometry")
        if not isinstance(geometry, dict):
            geometry = {}
            parameters["geometry"] = geometry
        segments = geometry.get("segments")
        if not isinstance(segments, list) or not all(
            isinstance(segment, dict) for segment in segments
        ):
            legacy_sections = geometry.pop("sections", None)
            loft = geometry.get("loft")
            loft_dict = (
                loft
                if isinstance(loft, dict)
                else {
                    "method": "smooth",
                    "profile_correspondence": "cardinal_quadrants",
                }
            )
            if isinstance(legacy_sections, list) and legacy_sections:
                segments = [
                    {
                        "tag": "main",
                        "loft": loft_dict,
                        "sections": legacy_sections,
                    }
                ]
            else:
                segments = [create_default_segment("main", 0.0, 500.0)]
            geometry["segments"] = segments

        legacy_sections = geometry.pop("sections", None)
        if isinstance(legacy_sections, list) and legacy_sections and segments:
            first_seg = segments[0]
            if not first_seg.get("sections"):
                first_seg["sections"] = legacy_sections

        for seg in segments:
            if not isinstance(seg.get("sections"), list):
                seg["sections"] = []

        return segments

    def _current_segment(self: FuselageEditor) -> dict[str, Any] | None:
        segments = self._segments()
        if 0 <= self._segment_index < len(segments):
            return segments[self._segment_index]
        if segments:
            self._segment_index = 0
            return segments[0]
        return None
