"""Motor component property editor with PyThrust database catalog picker."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDialog, QPushButton, QWidget

from plugins.electrical_propulsion.catalog_dialog import ComponentCatalogDialog
from setuav_studio.ui.editor.component import BaseComponentEditor
from setuav_studio.ui.widget.button import set_native_button
from setuav_studio_sdk import ParameterField, StudioAPI


class MotorEditor(BaseComponentEditor):
    """Property editor for brushless and DC motors (org.setuav.core:motor)."""

    FIELDS = (
        ParameterField(
            key="kv",
            label="Velocity Constant (KV)",
            unit="RPM/V",
            field_type=float,
            default=900.0,
            min_value=10.0,
            max_value=20000.0,
            decimals=0,
            tooltip="Motor velocity constant in revolutions per minute per volt.",
        ),
        ParameterField(
            key="resistance",
            label="Internal Resistance (Rm)",
            unit="Ω",
            field_type=float,
            default=0.055,
            min_value=0.0001,
            max_value=10.0,
            decimals=4,
            tooltip="Phase-to-phase internal winding resistance.",
        ),
        ParameterField(
            key="no_load_current",
            label="No-Load Current (I0)",
            unit="A",
            field_type=float,
            default=1.1,
            min_value=0.01,
            max_value=50.0,
            decimals=2,
            tooltip="Idle no-load current at reference test voltage.",
        ),
        ParameterField(
            key="max_current",
            label="Max Current",
            unit="A",
            field_type=float,
            default=40.0,
            min_value=0.1,
            max_value=1000.0,
            decimals=1,
            tooltip="Maximum continuous/peak current rating.",
        ),
        ParameterField(
            key="max_power",
            label="Max Power",
            unit="W",
            field_type=float,
            default=800.0,
            min_value=1.0,
            max_value=100000.0,
            decimals=0,
            tooltip="Maximum electrical power handling limit.",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)
        # Remove previous stretch to keep Mount section before bottom stretch
        for i in range(self._content_layout.count()):
            item = self._content_layout.itemAt(i)
            if item and item.spacerItem() is not None:
                self._content_layout.removeItem(item)
                break
        self._create_mount_section()
        self._content_layout.addStretch()
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

            # Get geometry mount targets
            targets: list[Any] = []
            try:
                from plugins.geometry import get_mount_targets

                targets = get_mount_targets(self._api.current_project)
            except Exception:
                pass

            target_options: list[tuple[str, str]] = [("", "-- Select Target --")]
            for t in targets:
                tid = getattr(t, "id", str(t))
                tname = getattr(t, "name", tid)
                target_options.append((tid, f"{tname} ({tid})" if tname != tid else tid))

            # Include current target if not in available targets list
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
            self._set_property_value(self.mount_table, "orientation_roll", str(ori.get("roll", 0.0)))
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

        self._api.edit_component(
            self._component, f"Set motor mount target '{target_id}'", apply
        )
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

        self._api.edit_component(
            self._component, f"Set motor mount position '{position}'", apply
        )
        self._refresh_clearance()
        self._api.publish("project.modified")
        self._api.notify_project_content_changed()

    def _get_associated_propeller_diameter_mm(self) -> float:
        proj = self._api.current_project
        if not proj:
            return 250.0
        cid = str(self._component.get("id", ""))
        data = getattr(proj, "data", proj) if isinstance(proj, object) else {}
        assemblies = data.get("assemblies", []) if isinstance(data, dict) else []
        components = data.get("components", []) if isinstance(data, dict) else []
        comp_map = {c.get("id"): c for c in components if isinstance(c, dict)}

        for asm in assemblies:
            if not isinstance(asm, dict):
                continue
            members = asm.get("members", {})
            if cid in members.get("motors", []):
                prop_ids = members.get("propulsors", [])
                if prop_ids and prop_ids[0] in comp_map:
                    prop = comp_map[prop_ids[0]]
                    p_params = prop.get("parameters", {})
                    d = float(p_params.get("diameter_m") or p_params.get("diameter") or 0.25)
                    return d * 1000.0 if d < 2.0 else d

        for c in components:
            if isinstance(c, dict) and c.get("type") in (
                "org.setuav.core:propeller",
                "org.setuav.core:rotor",
            ):
                p_params = c.get("parameters", {})
                d = float(p_params.get("diameter_m") or p_params.get("diameter") or 0.25)
                return d * 1000.0 if d < 2.0 else d

        return 250.0

    def _refresh_clearance(self) -> None:
        if not hasattr(self, "mount_table"):
            return
        params = self._component.get("parameters", {})
        mount = params.get("mount", {})
        target_id = str(mount.get("target_id") or "")
        position = str(mount.get("position") or "front")
        offset = mount.get("offset") or {}
        orientation = mount.get("orientation") or {}

        if not target_id:
            self._set_property_value(
                self.mount_table, "clearance", "No target selected", editable=False
            )
            return

        prop_dia = self._get_associated_propeller_diameter_mm()
        try:
            from plugins.geometry import check_propeller_clearance

            info = check_propeller_clearance(
                self._api.current_project,
                target_id=target_id,
                position=position,
                offset=offset,
                orientation=orientation,
                propeller_diameter=prop_dia,
            )
            status_text = info.get("message", "Checked")
            prefix = "✓ " if not info.get("has_collision") and info.get("valid") else "⚠ "
            self._set_property_value(
                self.mount_table, "clearance", f"{prefix}{status_text}", editable=False
            )
        except Exception as ex:
            self._set_property_value(
                self.mount_table, "clearance", f"⚠ Check failed: {ex}", editable=False
            )

    def _load_component(self) -> None:
        super()._load_component()
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
                params["no_load_current"] = float(m.io)
                params["max_current"] = float(m.max_current)
                if m.max_power:
                    params["max_power"] = float(m.max_power)
                params["mass"] = float(m.weight_g)

            self._api.edit_component(
                self._component,
                f"Apply catalog motor '{m.manufacturer} {m.name}'",
                apply_catalog_motor,
            )
            self._load_component()
