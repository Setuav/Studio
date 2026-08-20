"""Planform sizing and driver group handling for the Lifting Surface Editor."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from setuav_studio.plugins.geometry.wing_planform_engine import (
    DRIVER_MODES,
    SWEEP_LOCATIONS,
    TWIST_LOCATIONS,
    compute_planform_metrics,
    get_driver_inputs_for_mode,
    solve_wing_planform,
)
from setuav_studio.ui.numeric_spinbox import set_table_spinbox


class PlanformMixin:
    """Driver groups and parametric planform sizing logic."""

    # -------------------------------------------------------------------------
    # UI Sections Creation
    # -------------------------------------------------------------------------

    def _create_driver_groups_section(self) -> None:
        """Driver Groups configuration table section."""
        layout = self._create_section("Driver Group", "fa6s.arrows-left-right-to-line")

        self.driver_groups_table = self._property_table([
            ("driver_mode", "Driver Mode"),
            ("sweep_loc", "Sweep Reference"),
            ("twist_axis", "Twist Axis"),
        ])
        layout.addWidget(self.driver_groups_table)

    def _create_planform_sizing_section(self) -> None:
        """Parametric Planform Sizing table section."""
        layout = self._create_section("Planform Sizing", "fa6s.ruler-combined")

        # Planform Parameters Table
        self.planform_table = self._property_table([
            ("area", "Planform Area (S)"),
            ("span", "Total Wingspan (b)"),
            ("aspect_ratio", "Aspect Ratio (AR)"),
            ("taper_ratio", "Taper Ratio (λ)"),
            ("root_chord", "Root Chord (c_root)"),
            ("tip_chord", "Tip Chord (c_tip)"),
            ("sweep", "Sweep Angle (Λ)"),
            ("washout", "Tip Twist / Washout (ε)"),
            ("mac", "Mean Aerodyn Chord (MAC)"),
        ])
        self.planform_table.cellChanged.connect(self._on_planform_parameter_edited)
        layout.addWidget(self.planform_table)

    # -------------------------------------------------------------------------
    # Planform Sizing & Driver Group Logic
    # -------------------------------------------------------------------------

    def _sync_driver_mode_from_project(self) -> None:
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)
        if project and isinstance(project.data.get("driver_groups"), list):
            for dg in project.data["driver_groups"]:
                if isinstance(dg, dict) and dg.get("id") in ("wing-drivers", f"{self._component.get('id')}-drivers"):
                    self._driver_mode = "area_ar_taper"
                    break

    def _load_driver_groups_table(self) -> None:
        # Driver Mode
        self._set_property_combo(
            self.driver_groups_table,
            "driver_mode",
            self._driver_mode,
            DRIVER_MODES,
            self._on_driver_mode_changed,
        )

        # Sweep Reference
        self._set_property_combo(
            self.driver_groups_table,
            "sweep_loc",
            str(self._sweep_loc),
            [(str(val), label) for val, label in SWEEP_LOCATIONS],
            self._on_sweep_loc_changed,
        )

        # Twist Axis Location
        twist_loc = float(self._geometry().get("twist_location", 0.25))
        self._set_property_combo(
            self.driver_groups_table,
            "twist_axis",
            str(twist_loc),
            [(str(val), label) for val, label in TWIST_LOCATIONS],
            self._on_twist_loc_changed,
        )

    def _on_driver_mode_changed(self, mode_val: str) -> None:
        if self._loading:
            return
        self._driver_mode = str(mode_val or "manual")
        self._refresh_planform_table()
        self._update_profile_actions()
        self._update_profiles_table_interactivity()
        if 0 <= self._profile_index < len(self._profiles()):
            self._load_profile(self._profile_index)

    def _on_sweep_loc_changed(self, loc_val_str: str) -> None:
        if self._loading:
            return
        try:
            self._sweep_loc = float(loc_val_str)
        except ValueError:
            self._sweep_loc = 0.25
        self._refresh_planform_table()

    def _on_twist_loc_changed(self, twist_val_str: str) -> None:
        if self._loading:
            return
        try:
            twist_loc = float(twist_val_str)
        except ValueError:
            twist_loc = 0.25

        def change() -> None:
            self._geometry()["twist_location"] = twist_loc

        self._edit_component("Change wing twist axis location", change)

    def _is_symmetric(self) -> bool:
        geom = self._geometry()
        return bool(geom.get("symmetric", True))

    def _y_offset(self) -> float:
        tf = self._component.get("transform")
        if isinstance(tf, dict):
            pos = tf.get("position")
            if isinstance(pos, dict):
                return float(pos.get("y", 0.0))
        return 0.0

    def _refresh_planform_table(self) -> None:
        profiles = self._profiles()
        metrics = compute_planform_metrics(
            profiles,
            self._sweep_loc,
            symmetric=self._is_symmetric(),
            y_offset=self._y_offset(),
        )
        active_driver_keys = [k for k, _l, _u in get_driver_inputs_for_mode(self._driver_mode)]

        was_loading = self._loading
        self._loading = True
        try:
            s_total = metrics["area"]
            s_m2 = s_total / 1e6
            s_dm2 = s_total / 1e4
            if "area" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "area",
                    s_total,
                    min_val=100.0,
                    step=1000.0,
                    decimals=1,
                    suffix="mm²",
                    on_changed=lambda val: self._on_planform_spinbox_changed("area", val),
                )
            else:
                self._set_planform_cell("area", f"{s_m2:.4f} m² ({s_dm2:.2f} dm²)", editable=False)

            if "span" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "span",
                    metrics["span"],
                    min_val=10.0,
                    step=50.0,
                    decimals=1,
                    suffix="mm",
                    on_changed=lambda val: self._on_planform_spinbox_changed("span", val),
                )
            else:
                self._set_planform_cell("span", f"{metrics['span']:.1f} mm", editable=False)

            if "aspect_ratio" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "aspect_ratio",
                    metrics["aspect_ratio"],
                    min_val=0.5,
                    max_val=50.0,
                    step=0.1,
                    decimals=2,
                    on_changed=lambda val: self._on_planform_spinbox_changed("aspect_ratio", val),
                )
            else:
                self._set_planform_cell("aspect_ratio", f"{metrics['aspect_ratio']:.2f}", editable=False)

            if "taper_ratio" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "taper_ratio",
                    metrics["taper_ratio"],
                    min_val=0.01,
                    max_val=5.0,
                    step=0.05,
                    decimals=3,
                    on_changed=lambda val: self._on_planform_spinbox_changed("taper_ratio", val),
                )
            else:
                self._set_planform_cell("taper_ratio", f"{metrics['taper_ratio']:.3f}", editable=False)

            if "root_chord" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "root_chord",
                    metrics["root_chord"],
                    min_val=5.0,
                    step=10.0,
                    decimals=1,
                    suffix="mm",
                    on_changed=lambda val: self._on_planform_spinbox_changed("root_chord", val),
                )
            else:
                self._set_planform_cell("root_chord", f"{metrics['root_chord']:.1f} mm", editable=False)

            if "tip_chord" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "tip_chord",
                    metrics["tip_chord"],
                    min_val=5.0,
                    step=10.0,
                    decimals=1,
                    suffix="mm",
                    on_changed=lambda val: self._on_planform_spinbox_changed("tip_chord", val),
                )
            else:
                self._set_planform_cell("tip_chord", f"{metrics['tip_chord']:.1f} mm", editable=False)

            if "sweep" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "sweep",
                    metrics["sweep"],
                    min_val=-80.0,
                    max_val=80.0,
                    step=1.0,
                    decimals=1,
                    suffix="°",
                    on_changed=lambda val: self._on_planform_spinbox_changed("sweep", val),
                )
            else:
                self._set_planform_cell("sweep", f"{metrics['sweep']:.1f}°", editable=False)

            if "washout" in active_driver_keys:
                self._set_property_spinbox(
                    self.planform_table,
                    "washout",
                    metrics["washout"],
                    min_val=-45.0,
                    max_val=45.0,
                    step=0.5,
                    decimals=1,
                    suffix="°",
                    on_changed=lambda val: self._on_planform_spinbox_changed("washout", val),
                )
            else:
                self._set_planform_cell("washout", f"{metrics['washout']:.1f}°", editable=False)

            self._set_planform_cell("mac", f"{metrics['mac']:.1f} mm", editable=False)

            self._update_profiles_table_interactivity()
        finally:
            self._loading = was_loading

    def _set_planform_cell(self, key: str, value: str, *, editable: bool) -> None:
        """Set property value with distinct visual styling for active drivers vs computed values."""
        for row in range(self.planform_table.rowCount()):
            if self._property_key(self.planform_table, row) != key:
                continue
            if self.planform_table.cellWidget(row, 1) is not None:
                self.planform_table.removeCellWidget(row, 1)
            item = self.planform_table.item(row, 1)
            if item is None:
                item = QTableWidgetItem()
                self.planform_table.setItem(row, 1, item)
            item.setText(value)
            label_item = self.planform_table.item(row, 0)
            if editable:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setForeground(QBrush(QColor("#ffffff")))
                if label_item:
                    label_item.setForeground(QBrush(QColor("#ffffff")))
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setForeground(QBrush(QColor("#777777")))
                if label_item:
                    label_item.setForeground(QBrush(QColor("#999999")))
            return

    def _on_planform_spinbox_changed(self, key: str, val_num: float) -> None:
        if self._loading:
            return
        if key not in ("sweep", "washout") and val_num <= 0:
            return

        profiles = self._profiles()
        is_sym = self._is_symmetric()
        y_off = self._y_offset()
        current_metrics = compute_planform_metrics(
            profiles,
            self._sweep_loc,
            symmetric=is_sym,
            y_offset=y_off,
        )
        inputs: dict[str, float] = {
            "area": current_metrics["area"],
            "span": current_metrics["span"],
            "aspect_ratio": current_metrics["aspect_ratio"],
            "taper_ratio": current_metrics["taper_ratio"],
            "root_chord": current_metrics["root_chord"],
            "tip_chord": current_metrics["tip_chord"],
            "sweep": current_metrics["sweep"],
            "washout": current_metrics["washout"],
        }
        inputs[key] = float(val_num)

        new_profiles, calculated_metrics = solve_wing_planform(
            self._driver_mode,
            inputs,
            profiles,
            self._sweep_loc,
            symmetric=is_sym,
            y_offset=y_off,
        )

        def change() -> None:
            profiles.clear()
            profiles.extend(deepcopy(new_profiles))
            self._sync_project_parameters(inputs, key)

        self._edit_component(f"Parametric wing resize ({key})", change)

        self._populate_profiles()
        self._refresh_planform_table()
        if 0 <= self._profile_index < len(profiles):
            self._load_profile(self._profile_index)

    def _on_planform_parameter_edited(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.planform_table, row)
        val_str = self._property_text(self.planform_table, row)
        val_num = self._parse_number(val_str)
        if val_num is not None:
            self._on_planform_spinbox_changed(key, val_num)

    def _sync_project_parameters(self, inputs: dict[str, float], edited_key: str) -> None:
        """Sync updated macro parameters to project.data['parameters'] if present."""
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)
        if not project or not isinstance(project.data.get("parameters"), dict):
            return
        params = project.data["parameters"]
        if "wing_area" in params and isinstance(params["wing_area"], dict):
            params["wing_area"]["value"] = inputs.get("area", 218700.0)
        if "wing_aspect_ratio" in params and isinstance(params["wing_aspect_ratio"], dict):
            params["wing_aspect_ratio"]["value"] = inputs.get("aspect_ratio", 5.33)

    def _update_profiles_table_interactivity(self) -> None:
        """Lock or unlock profiles table columns depending on driver mode."""
        is_manual = self._driver_mode == "manual"
        # Columns: 0=#, 1=Airfoil, 2=Span Y, 3=Chord
        for r in range(self.profiles_table.rowCount()):
            # Airfoil is always editable
            af_item = self.profiles_table.item(r, 1)
            if af_item:
                af_item.setFlags(af_item.flags() | Qt.ItemFlag.ItemIsEditable)
                af_item.setForeground(QBrush(QColor("#ffffff")))
            # Span Y and Chord depend on driver mode
            for c in (2, 3):
                item = self.profiles_table.item(r, c)
                if not item:
                    continue
                if is_manual:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    item.setForeground(QBrush(QColor("#ffffff")))
                else:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setForeground(QBrush(QColor("#777777")))

        # In section properties: chord, span_y, offset_x are locked when macro driver is active
        locked_keys = {"chord", "span_y", "offset_x"}
        for row in range(self.profile_properties_table.rowCount()):
            key = self._property_key(self.profile_properties_table, row)
            widget = self.profile_properties_table.cellWidget(row, 1)
            val_item = self.profile_properties_table.item(row, 1)
            lbl_item = self.profile_properties_table.item(row, 0)
            is_locked = (key in locked_keys) and not is_manual
            if widget is not None:
                widget.setEnabled(not is_locked)
            if val_item is not None:
                if is_locked:
                    val_item.setFlags(val_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    val_item.setForeground(QBrush(QColor("#777777")))
                else:
                    val_item.setFlags(val_item.flags() | Qt.ItemFlag.ItemIsEditable)
                    val_item.setForeground(QBrush(QColor("#ffffff")))
            if lbl_item is not None:
                lbl_item.setForeground(QBrush(QColor("#777777" if is_locked else "#ffffff")))