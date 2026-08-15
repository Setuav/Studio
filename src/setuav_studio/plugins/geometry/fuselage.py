from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class FuselageEditor(QWidget):
    PROFILE_TYPES = (
        "circle",
        "ellipse",
        "rectangle",
        "trapezoid",
        "triangle",
        "polygon",
    )

    def __init__(self, component: dict[str, Any]) -> None:
        super().__init__()
        self._component = component
        self._segment_index = -1
        self._section_index = -1
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(4, 4, 4, 4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._create_general_section()
        self._create_segments_section()
        self._create_sections_section()
        self._content_layout.addStretch()
        self._load_component()

    def _create_general_section(self) -> None:
        group = QGroupBox("General")
        form = QFormLayout(group)

        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._update_general)
        form.addRow("Name:", self.name_edit)

        self.type_label = QLabel()
        self.type_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.type_label.setWordWrap(True)
        form.addRow("Type:", self.type_label)

        self.mass_spin = self._number_box(" g", 0, 1_000_000)
        self.mass_spin.valueChanged.connect(self._update_general)
        form.addRow("Mass:", self.mass_spin)

        self._content_layout.addWidget(group)

    def _create_segments_section(self) -> None:
        segments_group = QGroupBox("Segments")
        layout = QVBoxLayout(segments_group)

        self.segments_table = self._table(["Tag", "Sections", "Loft"])
        self.segments_table.setMaximumHeight(180)
        self.segments_table.currentCellChanged.connect(self._on_segment_selected)
        layout.addWidget(self.segments_table)

        selected_group = QGroupBox("Selected Segment")
        form = QFormLayout(selected_group)

        self.segment_tag_edit = QLineEdit()
        self.segment_tag_edit.editingFinished.connect(self._update_segment)
        form.addRow("Tag:", self.segment_tag_edit)

        self.loft_method_combo = QComboBox()
        self.loft_method_combo.addItems(["auto", "smooth", "ruled"])
        self.loft_method_combo.currentTextChanged.connect(self._update_segment)
        form.addRow("Method:", self.loft_method_combo)

        self.parameterization_combo = QComboBox()
        self.parameterization_combo.addItems(["uniform", "chord_length", "centripetal"])
        self.parameterization_combo.currentTextChanged.connect(self._update_segment)
        form.addRow("Parameterization:", self.parameterization_combo)

        correspondence = QLabel("cardinal_quadrants")
        correspondence.setWordWrap(True)
        form.addRow("Profile matching:", correspondence)

        layout.addWidget(selected_group)
        self._content_layout.addWidget(segments_group)

    def _create_sections_section(self) -> None:
        sections_group = QGroupBox("Sections")
        layout = QVBoxLayout(sections_group)

        self.sections_table = self._table(["#", "Profile", "X", "Size"])
        self.sections_table.setMaximumHeight(180)
        self.sections_table.currentCellChanged.connect(self._on_section_selected)
        layout.addWidget(self.sections_table)

        selected_group = QGroupBox("Selected Section")
        self.section_form = QFormLayout(selected_group)

        self.profile_type_combo = QComboBox()
        self.profile_type_combo.addItems(self.PROFILE_TYPES)
        self.profile_type_combo.currentTextChanged.connect(self._change_profile_type)
        self.section_form.addRow("Profile:", self.profile_type_combo)

        self.pos_x = self._number_box(" mm", -1_000_000, 1_000_000)
        self.pos_y = self._number_box(" mm", -1_000_000, 1_000_000)
        self.pos_z = self._number_box(" mm", -1_000_000, 1_000_000)
        self.section_form.addRow("Position X:", self.pos_x)
        self.section_form.addRow("Position Y:", self.pos_y)
        self.section_form.addRow("Position Z:", self.pos_z)

        self.rot_x = self._number_box("°", -180, 180)
        self.rot_y = self._number_box("°", -180, 180)
        self.rot_z = self._number_box("°", -180, 180)
        self.section_form.addRow("Rotation X:", self.rot_x)
        self.section_form.addRow("Rotation Y:", self.rot_y)
        self.section_form.addRow("Rotation Z:", self.rot_z)

        self.diameter = self._number_box(" mm", 0, 1_000_000)
        self.width = self._number_box(" mm", 0, 1_000_000)
        self.height = self._number_box(" mm", 0, 1_000_000)
        self.corner_radius = self._number_box(" mm", 0, 1_000_000)
        self.top_width = self._number_box(" mm", 0, 1_000_000)
        self.bottom_width = self._number_box(" mm", 0, 1_000_000)
        self.base_width = self._number_box(" mm", 0, 1_000_000)
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["up", "down"])

        self.section_form.addRow("Diameter:", self.diameter)
        self.section_form.addRow("Width:", self.width)
        self.section_form.addRow("Height:", self.height)
        self.section_form.addRow("Corner radius:", self.corner_radius)
        self.section_form.addRow("Top width:", self.top_width)
        self.section_form.addRow("Bottom width:", self.bottom_width)
        self.section_form.addRow("Base width:", self.base_width)
        self.section_form.addRow("Orientation:", self.orientation_combo)

        self.vertices_table = self._table(["Y", "Z", "Radius"])
        self.vertices_table.setMaximumHeight(180)
        self.vertices_table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.vertices_table.cellChanged.connect(self._update_vertices)
        self.section_form.addRow("Vertices:", self.vertices_table)

        for widget in (
            self.pos_x,
            self.pos_y,
            self.pos_z,
            self.rot_x,
            self.rot_y,
            self.rot_z,
            self.diameter,
            self.width,
            self.height,
            self.corner_radius,
            self.top_width,
            self.bottom_width,
            self.base_width,
        ):
            widget.valueChanged.connect(self._update_section)
        self.orientation_combo.currentTextChanged.connect(self._update_section)

        layout.addWidget(selected_group)
        self._content_layout.addWidget(sections_group)

    def _load_component(self) -> None:
        self._loading = True
        self.name_edit.setText(str(self._component.get("name") or ""))
        self.type_label.setText(str(self._component.get("type") or ""))
        self.mass_spin.setValue(float(self._parameters().get("mass") or 0))
        self._populate_segments()
        self._loading = False

        if self._segments():
            self.segments_table.selectRow(0)
            self._load_segment(0)

    def _populate_segments(self) -> None:
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
                self.segments_table.setItem(row, column, QTableWidgetItem(value))

    def _load_segment(self, index: int) -> None:
        segments = self._segments()
        if not 0 <= index < len(segments):
            self._segment_index = -1
            self.sections_table.setRowCount(0)
            return

        self._loading = True
        self._segment_index = index
        self._section_index = -1
        segment = segments[index]
        loft = segment.get("loft")
        if not isinstance(loft, dict):
            loft = {}
        self.segment_tag_edit.setText(str(segment.get("tag") or ""))
        self.loft_method_combo.setCurrentText(str(loft.get("method") or "smooth"))
        self.parameterization_combo.setCurrentText(
            str(loft.get("parameterization") or "centripetal")
        )
        self._populate_sections()
        self._loading = False

        sections = self._sections()
        if sections:
            self.sections_table.selectRow(0)
            self._load_section(0)

    def _populate_sections(self) -> None:
        sections = self._sections()
        self.sections_table.setRowCount(len(sections))
        for row, section in enumerate(sections):
            profile = section.get("profile")
            if not isinstance(profile, dict):
                profile = {}
            position = section.get("position")
            if not isinstance(position, dict):
                position = {}
            values = (
                str(row + 1),
                str(profile.get("type") or ""),
                str(position.get("x") or 0),
                self._profile_size(profile),
            )
            for column, value in enumerate(values):
                self.sections_table.setItem(row, column, QTableWidgetItem(value))

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
        profile_type = str(profile.get("type") or "circle")

        self.profile_type_combo.setCurrentText(profile_type)
        self.pos_x.setValue(float(position.get("x") or 0))
        self.pos_y.setValue(float(position.get("y") or 0))
        self.pos_z.setValue(float(position.get("z") or 0))
        self.rot_x.setValue(float(rotation.get("x") or 0))
        self.rot_y.setValue(float(rotation.get("y") or 0))
        self.rot_z.setValue(float(rotation.get("z") or 0))
        self.diameter.setValue(float(profile.get("diameter") or 0))
        self.width.setValue(float(profile.get("width") or 0))
        self.height.setValue(float(profile.get("height") or 0))
        self.corner_radius.setValue(float(profile.get("corner_radius") or 0))
        self.top_width.setValue(float(profile.get("top_width") or 0))
        self.bottom_width.setValue(float(profile.get("bottom_width") or 0))
        self.base_width.setValue(float(profile.get("base_width") or 0))
        self.orientation_combo.setCurrentText(str(profile.get("orientation") or "up"))
        self._populate_vertices(profile)
        self._set_profile_rows(profile_type)
        self._loading = False

    def _on_segment_selected(self, row: int, _column: int, *_previous: int) -> None:
        if not self._loading and row >= 0:
            self._load_segment(row)

    def _on_section_selected(self, row: int, _column: int, *_previous: int) -> None:
        if not self._loading and row >= 0:
            self._load_section(row)

    def _update_general(self, *_args: object) -> None:
        if self._loading:
            return
        self._component["name"] = self.name_edit.text().strip()
        self._parameters()["mass"] = self.mass_spin.value()

    def _update_segment(self, *_args: object) -> None:
        segment = self._current_segment()
        if self._loading or segment is None:
            return
        segment["tag"] = self.segment_tag_edit.text().strip()
        loft = self._object(segment, "loft")
        loft["method"] = self.loft_method_combo.currentText()
        loft["parameterization"] = self.parameterization_combo.currentText()
        loft["profile_correspondence"] = "cardinal_quadrants"
        self._refresh_segment_row()

    def _change_profile_type(self, profile_type: str) -> None:
        section = self._current_section()
        if self._loading or section is None:
            return
        section["profile"] = self._default_profile(profile_type)
        self._load_section(self._section_index)
        self._populate_sections()
        self.sections_table.selectRow(self._section_index)

    def _update_section(self, *_args: object) -> None:
        section = self._current_section()
        if self._loading or section is None:
            return

        section["position"] = {
            "x": self.pos_x.value(),
            "y": self.pos_y.value(),
            "z": self.pos_z.value(),
        }
        section["rotation"] = {
            "x": self.rot_x.value(),
            "y": self.rot_y.value(),
            "z": self.rot_z.value(),
        }

        profile = self._object(section, "profile")
        profile_type = str(profile.get("type") or "circle")
        fields = {
            "circle": {"diameter": self.diameter.value()},
            "ellipse": {"width": self.width.value(), "height": self.height.value()},
            "rectangle": {
                "width": self.width.value(),
                "height": self.height.value(),
                "corner_radius": self.corner_radius.value(),
            },
            "trapezoid": {
                "top_width": self.top_width.value(),
                "bottom_width": self.bottom_width.value(),
                "height": self.height.value(),
                "corner_radius": self.corner_radius.value(),
            },
            "triangle": {
                "base_width": self.base_width.value(),
                "height": self.height.value(),
                "orientation": self.orientation_combo.currentText(),
                "corner_radius": self.corner_radius.value(),
            },
        }
        if profile_type in fields:
            profile.clear()
            profile["type"] = profile_type
            profile.update(fields[profile_type])
        self._refresh_section_row()

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
        item = self.vertices_table.item(row, column)
        try:
            value = float(item.text()) if item is not None else 0.0
        except ValueError:
            return
        key = ("y", "z", "radius")[column]
        if isinstance(vertices[row], dict):
            vertices[row][key] = value

    def _set_profile_rows(self, profile_type: str) -> None:
        visible = {
            self.diameter: profile_type == "circle",
            self.width: profile_type in {"ellipse", "rectangle"},
            self.height: profile_type in {"ellipse", "rectangle", "trapezoid", "triangle"},
            self.corner_radius: profile_type in {"rectangle", "trapezoid", "triangle"},
            self.top_width: profile_type == "trapezoid",
            self.bottom_width: profile_type == "trapezoid",
            self.base_width: profile_type == "triangle",
            self.orientation_combo: profile_type == "triangle",
            self.vertices_table: profile_type == "polygon",
        }
        for widget, is_visible in visible.items():
            self.section_form.setRowVisible(widget, is_visible)

    def _populate_vertices(self, profile: dict[str, Any]) -> None:
        vertices = profile.get("vertices")
        if not isinstance(vertices, list):
            vertices = []
        self.vertices_table.setRowCount(len(vertices))
        for row, vertex in enumerate(vertices):
            if not isinstance(vertex, dict):
                continue
            for column, key in enumerate(("y", "z", "radius")):
                self.vertices_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(str(vertex.get(key) or 0)),
                )

    def _refresh_segment_row(self) -> None:
        segment = self._current_segment()
        if segment is None:
            return
        loft = segment.get("loft") if isinstance(segment.get("loft"), dict) else {}
        self.segments_table.item(self._segment_index, 0).setText(str(segment.get("tag") or ""))
        self.segments_table.item(self._segment_index, 2).setText(str(loft.get("method") or ""))

    def _refresh_section_row(self) -> None:
        section = self._current_section()
        if section is None:
            return
        position = section.get("position") if isinstance(section.get("position"), dict) else {}
        profile = section.get("profile") if isinstance(section.get("profile"), dict) else {}
        row = self._section_index
        self.sections_table.item(row, 1).setText(str(profile.get("type") or ""))
        self.sections_table.item(row, 2).setText(str(position.get("x") or 0))
        self.sections_table.item(row, 3).setText(self._profile_size(profile))

    def _parameters(self) -> dict[str, Any]:
        return self._object(self._component, "parameters")

    def _segments(self) -> list[dict[str, Any]]:
        geometry = self._parameters().get("geometry")
        if not isinstance(geometry, dict):
            return []
        segments = geometry.get("segments")
        if not isinstance(segments, list):
            return []
        return [segment for segment in segments if isinstance(segment, dict)]

    def _sections(self) -> list[dict[str, Any]]:
        segment = self._current_segment()
        if segment is None:
            return []
        sections = segment.get("sections")
        if not isinstance(sections, list):
            return []
        return [section for section in sections if isinstance(section, dict)]

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

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    @staticmethod
    def _number_box(suffix: str, minimum: float, maximum: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setDecimals(2)
        box.setSuffix(suffix)
        return box

    @staticmethod
    def _profile_size(profile: dict[str, Any]) -> str:
        profile_type = profile.get("type")
        if profile_type == "circle":
            return f'D {profile.get("diameter", 0)}'
        if profile_type in {"ellipse", "rectangle"}:
            return f'{profile.get("width", 0)} × {profile.get("height", 0)}'
        if profile_type == "trapezoid":
            return f'{profile.get("top_width", 0)} / {profile.get("bottom_width", 0)}'
        if profile_type == "triangle":
            return f'{profile.get("base_width", 0)} × {profile.get("height", 0)}'
        if profile_type == "polygon":
            return f'{len(profile.get("vertices") or [])} vertices'
        return ""

    @staticmethod
    def _default_profile(profile_type: str) -> dict[str, Any]:
        defaults: dict[str, dict[str, Any]] = {
            "circle": {"type": "circle", "diameter": 100.0},
            "ellipse": {"type": "ellipse", "width": 100.0, "height": 100.0},
            "rectangle": {
                "type": "rectangle",
                "width": 100.0,
                "height": 100.0,
                "corner_radius": 0.0,
            },
            "trapezoid": {
                "type": "trapezoid",
                "top_width": 80.0,
                "bottom_width": 100.0,
                "height": 100.0,
                "corner_radius": 0.0,
            },
            "triangle": {
                "type": "triangle",
                "base_width": 100.0,
                "height": 100.0,
                "orientation": "up",
                "corner_radius": 0.0,
            },
            "polygon": {
                "type": "polygon",
                "vertices": [
                    {"y": -50.0, "z": -50.0, "radius": 0.0},
                    {"y": 50.0, "z": -50.0, "radius": 0.0},
                    {"y": 0.0, "z": 50.0, "radius": 0.0},
                ],
            },
        }
        return defaults.get(profile_type, defaults["circle"]).copy()
