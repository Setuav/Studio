"""Motor component property editor with PyThrust database catalog picker."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDialog, QPushButton, QWidget

from plugins.electrical_propulsion.catalog_dialog import ComponentCatalogDialog
from plugins.electrical_propulsion.models.motor import MotorModel
from setuav_studio.api import StudioAPI
from setuav_studio.ui.editor.component import BaseComponentEditor
from setuav_studio.ui.widget.button import set_native_button


class MotorEditor(BaseComponentEditor):
    """Property editor for brushless and DC motors (org.setuav.core:motor)."""

    FIELDS = MotorModel.get_scalar_fields()

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)

    def _create_custom_sections(self) -> None:
        self._create_mount_section()
        self._load_mount()

    def _create_general_section(self) -> None:
        catalog_btn = QPushButton("Catalog…", self)
        set_native_button(catalog_btn, "fa6s.database")
        catalog_btn.clicked.connect(self._open_catalog)

        layout = self._create_section("General", "fa6s.circle-info", action_widget=catalog_btn)
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("type", "Type"),
                ("mass", "Mass"),
                ("manufacturer", "Manufacturer"),
                ("model", "Model"),
            ]
        )
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _create_mount_section(self) -> None:
        layout = self._create_section("Mount", "fa6s.crosshairs")
        self.mount_table = self._property_table(
            [
                ("target_id", "Mount Target"),
                ("position", "Position"),
                ("offset_x", "Offset X (mm)"),
                ("offset_y", "Offset Y (mm)"),
                ("offset_z", "Offset Z (mm)"),
                ("orientation_roll", "Roll Angle (°)"),
                ("orientation_pitch", "Pitch Angle (°)"),
                ("orientation_yaw", "Yaw Angle (°)"),
                ("clearance", "Clearance Status"),
            ]
        )
        self.mount_table.cellChanged.connect(self._update_mount_cell)
        layout.addWidget(self.mount_table)

    def _load_mount(self) -> None:
        if not hasattr(self, "mount_table"):
            return
        self._loading = True
        try:
            params = self._component.setdefault("parameters", {})
            mount = params.setdefault("mount", {})
            current_target = str(mount.get("target_id") or "")
            current_pos = str(mount.get("position") or "front")

            # Collect geometry mount targets directly from project components
            target_options: list[tuple[str, str]] = [("", "-- Select Target --")]
            if self._api.project is not None:
                comps = self._api.project.data.get("components", [])
                for c in comps:
                    if isinstance(c, dict):
                        ctype = str(c.get("type", ""))
                        cid = str(c.get("id", ""))
                        cname = str(c.get("name", cid))
                        if ctype in (
                            "org.setuav.core:lifting-surface",
                            "org.setuav.core:fuselage",
                            "org.setuav.core:airframe",
                        ):
                            target_options.append(
                                (cid, f"{cname} ({cid})" if cname != cid else cid)
                            )

            if current_target and not any(opt[0] == current_target for opt in target_options):
                target_options.insert(1, (current_target, f"⚠ {current_target} (Not Found)"))

            self._set_property_combo(
                self.mount_table,
                "target_id",
                current_target,
                target_options,
                self._on_target_changed,
            )

            pos_options = [("front", "Front"), ("rear", "Rear")]
            self._set_property_combo(
                self.mount_table,
                "position",
                current_pos,
                pos_options,
                self._on_position_changed,
            )

            offset = mount.setdefault("offset", {"x": 0.0, "y": 0.0, "z": 0.0})
            self._set_property_value(self.mount_table, "offset_x", str(offset.get("x", 0.0)))
            self._set_property_value(self.mount_table, "offset_y", str(offset.get("y", 0.0)))
            self._set_property_value(self.mount_table, "offset_z", str(offset.get("z", 0.0)))

            ori = mount.setdefault("orientation", {"roll": 0.0, "pitch": 0.0, "yaw": 0.0})
            self._set_property_value(
                self.mount_table, "orientation_roll", str(ori.get("roll", 0.0))
            )
            self._set_property_value(
                self.mount_table, "orientation_pitch", str(ori.get("pitch", 0.0))
            )
            self._set_property_value(self.mount_table, "orientation_yaw", str(ori.get("yaw", 0.0)))

            self._refresh_clearance()
        finally:
            self._loading = False

    def _update_mount_cell(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.mount_table, row)
        field_map = {
            "offset_x": ("offset", "x"),
            "offset_y": ("offset", "y"),
            "offset_z": ("offset", "z"),
            "orientation_roll": ("orientation", "roll"),
            "orientation_pitch": ("orientation", "pitch"),
            "orientation_yaw": ("orientation", "yaw"),
        }
        if key not in field_map:
            return

        val_str = self._property_text(self.mount_table, row)
        try:
            val_float = float(val_str)
        except ValueError:
            return

        group, sub_key = field_map[key]

        def apply() -> None:
            params = self._component.setdefault("parameters", {})
            mount = params.setdefault("mount", {})
            target_dict = mount.setdefault(group, {})
            target_dict[sub_key] = val_float

        self._api.edit_component(self._component, f"Update motor mount {key}", apply)
        self._refresh_clearance()
        self._api.publish("project.modified")
        self._api.notify_project_content_changed()

    def _on_target_changed(self, target_id: str) -> None:
        if self._loading:
            return

        def apply() -> None:
            params = self._component.setdefault("parameters", {})
            mount = params.setdefault("mount", {})
            mount["target_id"] = target_id

        self._api.edit_component(self._component, f"Set motor mount target '{target_id}'", apply)
        self._refresh_clearance()
        self._api.publish("project.modified")
        self._api.notify_project_content_changed()

    def _on_position_changed(self, position: str) -> None:
        if self._loading:
            return

        def apply() -> None:
            params = self._component.setdefault("parameters", {})
            mount = params.setdefault("mount", {})
            mount["position"] = position

        self._api.edit_component(self._component, f"Set motor mount position '{position}'", apply)
        self._refresh_clearance()
        self._api.publish("project.modified")
        self._api.notify_project_content_changed()

    def _refresh_clearance(self) -> None:
        if not hasattr(self, "mount_table"):
            return
        params = self._component.get("parameters", {})
        mount = params.get("mount", {})
        target_id = str(mount.get("target_id") or "")

        if not target_id:
            self._set_property_value(
                self.mount_table, "clearance", "No target selected", editable=False
            )
            return

        self._set_property_value(
            self.mount_table, "clearance", f"Attached to {target_id}", editable=False
        )

    def _load_component(self) -> None:
        super()._load_component()
        self._set_property_value(
            self.general_table,
            "manufacturer",
            str(self._component.get("manufacturer") or ""),
            editable=False,
        )
        self._set_property_value(
            self.general_table,
            "model",
            str(self._component.get("model") or ""),
            editable=False,
        )
        self._load_mount()

    def _open_catalog(self) -> None:
        dialog = ComponentCatalogDialog(component_type="motor", parent=self.window())
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_motor:
            m = dialog.selected_motor

            def apply_catalog_motor() -> None:
                self._component["name"] = m.name
                self._component["manufacturer"] = m.manufacturer
                self._component["model"] = m.name
                self._component["mass"] = m.weight_g
                params = self._component.setdefault("parameters", {})
                params["kv"] = float(m.kv)
                params["resistance"] = float(m.resistance)
                params["no_load_current"] = float(m.io or 0.0)
                params["max_current"] = float(m.max_current)
                params["max_power"] = float(m.max_power)

            self._api.edit_component(
                self._component, f"Apply catalog motor '{m.name}'", apply_catalog_motor
            )
            self._load_component()
