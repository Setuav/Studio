"""Attachment (transform) handling for the Lifting Surface Editor."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)

from setuav_studio.ui.numeric_spinbox import set_table_spinbox


class AttachmentMixin:
    """Component attachment / mount transform handling for lifting surfaces."""

    # -------------------------------------------------------------------------
    # UI Sections Creation
    # -------------------------------------------------------------------------

    def _create_attachment_section(self) -> None:
        """Component attachment / mount transform on the fuselage or parent."""
        layout = self._create_section("Attachment (Transform)", "mdi6.axis-arrow")

        self.attachment_table = QTableWidget(2, 3)
        self.attachment_table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        self.attachment_table.setVerticalHeaderLabels(["Position (mm)", "Rotation (°)"])
        self.attachment_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.attachment_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.attachment_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.attachment_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.attachment_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.attachment_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.attachment_table.horizontalHeader().setFixedHeight(23)
        self.attachment_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.attachment_table.verticalHeader().setDefaultSectionSize(23)
        self.attachment_table.verticalHeader().setMinimumWidth(82)
        self.attachment_table.setAlternatingRowColors(True)
        self.attachment_table.setFixedHeight(71)
        for row in range(2):
            for column in range(3):
                item = QTableWidgetItem("0.00")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.attachment_table.setItem(row, column, item)
        self.attachment_table.cellChanged.connect(self._update_attachment_transform)
        layout.addWidget(self.attachment_table)

        self.attachment_options_table = self._property_table([
            ("mirror", "Symmetry / Mirror"),
        ])
        layout.addWidget(self.attachment_options_table)

    # -------------------------------------------------------------------------
    # Attachment / Component Transform Handling
    # -------------------------------------------------------------------------

    def _load_attachment_transform(self) -> None:
        transform = self._component.get("transform")
        transform = transform if isinstance(transform, dict) else {}
        pos = transform.get("position")
        pos = pos if isinstance(pos, dict) else {}
        rot = transform.get("rotation")
        rot = rot if isinstance(rot, dict) else {}

        pos_vals = (
            float(pos.get("x", 0.0)),
            float(pos.get("y", 0.0)),
            float(pos.get("z", 0.0)),
        )
        rot_vals = (
            float(rot.get("roll") if "roll" in rot else rot.get("x", 0.0)),
            float(rot.get("pitch") if "pitch" in rot else rot.get("y", 0.0)),
            float(rot.get("yaw") if "yaw" in rot else rot.get("z", 0.0)),
        )

        for col, val in enumerate(pos_vals):
            set_table_spinbox(
                self.attachment_table,
                0,
                col,
                val,
                step=5.0,
                decimals=2,
                suffix="mm",
                on_changed=lambda _v: self._on_attachment_spinbox_changed(),
            )
        for col, val in enumerate(rot_vals):
            set_table_spinbox(
                self.attachment_table,
                1,
                col,
                val,
                min_val=-360.0,
                max_val=360.0,
                step=1.0,
                decimals=2,
                suffix="°",
                on_changed=lambda _v: self._on_attachment_spinbox_changed(),
            )

        # Symmetry / Mirror
        is_mirror = "true" if self._geometry().get("mirror") is True else "false"
        self._set_property_combo(
            self.attachment_options_table,
            "mirror",
            is_mirror,
            [("false", "Single (No Mirror)"), ("true", "Bilateral (Mirror XZ)")],
            lambda val: self._update_mirror(val == "true"),
        )

    def _update_mirror(self, is_mirrored: bool) -> None:
        if self._loading:
            return

        def change() -> None:
            if is_mirrored:
                self._geometry()["mirror"] = True
            else:
                self._geometry().pop("mirror", None)

        self._edit_component("Toggle bilateral wing mirror", change)

    def _on_attachment_spinbox_changed(self) -> None:
        if self._loading:
            return
        vals_pos = []
        for col in range(3):
            w = self.attachment_table.cellWidget(0, col)
            vals_pos.append(float(w.value()) if isinstance(w, QDoubleSpinBox) else 0.0)
        vals_rot = []
        for col in range(3):
            w = self.attachment_table.cellWidget(1, col)
            vals_rot.append(float(w.value()) if isinstance(w, QDoubleSpinBox) else 0.0)

        def change() -> None:
            tf = self._component.get("transform")
            if not isinstance(tf, dict):
                tf = {}
                self._component["transform"] = tf
            tf["position"] = {"x": vals_pos[0], "y": vals_pos[1], "z": vals_pos[2]}
            tf["rotation"] = {"roll": vals_rot[0], "pitch": vals_rot[1], "yaw": vals_rot[2]}

        self._edit_component("Edit wing attachment transform", change)
        self._refresh_planform_table()

    def _update_attachment_transform(self, _row: int, _col: int) -> None:
        pass

    def _update_attach_to(self, new_parent: str | None) -> None:
        if self._loading:
            return

        def change() -> None:
            self._component["attach_to"] = new_parent

        self._edit_component("Change component attach_to", change)