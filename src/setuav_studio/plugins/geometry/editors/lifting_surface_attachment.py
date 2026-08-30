"""Attachment (transform) handling for the Lifting Surface Editor."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
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
        self.attachment_table.setVerticalHeaderLabels(["Position", "Rotation"])
        self.attachment_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.attachment_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.attachment_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.attachment_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.attachment_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.attachment_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
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

        self.attachment_options_table = self._property_table(
            [
                ("mirror", "Symmetry / Mirror"),
            ]
        )
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

        axes = ("x", "y", "z")
        rot_keys = (("roll", "x"), ("pitch", "y"), ("yaw", "z"))

        for col, axis in enumerate(axes):
            raw_pos = pos.get(f"{axis}_expression") or float(pos.get(axis, 0.0))
            set_table_spinbox(
                self.attachment_table,
                0,
                col,
                raw_pos,
                step=5.0,
                decimals=2,
                suffix="mm",
                on_changed=lambda _v, a=axis: self._on_attachment_spinbox_changed("pos", a, _v),
                api=getattr(self, "_api", None),
                label=f"Position {axis.upper()}",
            )

        for col, (rk1, rk2) in enumerate(rot_keys):
            rot_val = float(rot.get(rk1) if rk1 in rot else rot.get(rk2, 0.0))
            raw_rot = rot.get(f"{rk1}_expression") or rot.get(f"{rk2}_expression") or rot_val
            set_table_spinbox(
                self.attachment_table,
                1,
                col,
                raw_rot,
                min_val=-360.0,
                max_val=360.0,
                step=1.0,
                decimals=2,
                suffix="°",
                on_changed=lambda _v, r=rk1: self._on_attachment_spinbox_changed("rot", r, _v),
                api=getattr(self, "_api", None),
                label=f"Rotation {rk1.title()}",
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

    def _on_attachment_spinbox_changed(self, kind: str, axis: str, value: Any) -> None:
        if self._loading:
            return
        vals_pos = []
        for col in range(3):
            w = self.attachment_table.cellWidget(0, col)
            vals_pos.append(float(w.value()) if hasattr(w, "value") else 0.0)
        vals_rot = []
        for col in range(3):
            w = self.attachment_table.cellWidget(1, col)
            vals_rot.append(float(w.value()) if hasattr(w, "value") else 0.0)

        val_str = str(value).strip() if value is not None else ""
        is_expr = val_str.startswith("=") or not val_str.replace(".", "", 1).replace("-", "", 1).isdigit()

        def change() -> None:
            tf = self._component.get("transform")
            if not isinstance(tf, dict):
                tf = {}
                self._component["transform"] = tf
            pos_dict = tf.setdefault("position", {})
            rot_dict = tf.setdefault("rotation", {})

            pos_dict["x"] = vals_pos[0]
            pos_dict["y"] = vals_pos[1]
            pos_dict["z"] = vals_pos[2]

            rot_dict["roll"] = vals_rot[0]
            rot_dict["pitch"] = vals_rot[1]
            rot_dict["yaw"] = vals_rot[2]

            if kind == "pos":
                if is_expr:
                    pos_dict[f"{axis}_expression"] = val_str
                else:
                    pos_dict.pop(f"{axis}_expression", None)
            elif kind == "rot":
                if is_expr:
                    rot_dict[f"{axis}_expression"] = val_str
                else:
                    rot_dict.pop(f"{axis}_expression", None)

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
