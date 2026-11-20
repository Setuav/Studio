"""Wing Planform Sizing & Angles handling for the Lifting Surface Editor."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from setuav_studio.model.expression import get_expression, set_expression
from setuav_studio.ui.widget.spinbox import evaluate_table_cell_input

from ...engine.lifting_surface_driver_solver import compute_all_8_parameters
from ...engine.lifting_surface_planform_engine import (
    SWEEP_LOCATIONS,
    TWIST_LOCATIONS,
    compute_planform_metrics,
    set_global_dihedral,
    set_global_sweep,
    set_global_twist,
    solve_planform,
)
from .host import LiftingSurfaceEditorHost
from .planform_driver_table import DriverPlanformTable


class PlanformSectionMixin(LiftingSurfaceEditorHost):
    """8-Variable 3-Driver Lifting Surface Planform Sizing and Angles/Alignment logic."""

    # -------------------------------------------------------------------------
    # UI Sections Creation
    # -------------------------------------------------------------------------

    def _create_planform_section(self) -> None:
        """Parametric Planform table (8 parameters with 3-driver checkbox system)."""
        layout = self._create_section("Planform", "fa6s.ruler-combined")

        geom = self._geometry()
        init_drivers = geom.get("active_drivers") or ["span", "root_chord", "tip_chord"]
        self.planform_table = DriverPlanformTable(
            default_drivers=init_drivers,
            on_values_changed=self._on_planform_driver_values_changed,
            on_drivers_changed=self._on_planform_drivers_changed,
            api=self._api,
        )
        layout.addWidget(self.planform_table)

    def _create_angles_section(self) -> None:
        """Global Sweep, Dihedral, Twist/Washout, and Reference Axes table section."""
        layout = self._create_section("Angles", "fa6s.arrows-spin")

        self.angles_table = self._property_table(
            [
                ("sweep", "Sweep Angle"),
                ("sweep_loc", "Sweep Location"),
                ("sweep_curvature", "Sweep Curvature"),
                ("dihedral", "Dihedral Angle"),
                ("twist", "Twist / Washout"),
                ("twist_axis", "Twist Axis Location"),
            ]
        )
        layout.addWidget(self.angles_table)

    # -------------------------------------------------------------------------
    # Planform Sizing & Angles Logic
    # -------------------------------------------------------------------------

    def _on_planform_drivers_changed(self, active_drivers: list[str]) -> None:
        if self._loading:
            return

        def change() -> None:
            geom = self._geometry()
            geom["active_drivers"] = list(active_drivers)
            driver_exprs = self.planform_table.get_driver_expressions()
            if driver_exprs:
                geom["driver_expressions"] = dict(driver_exprs)
            else:
                geom.pop("driver_expressions", None)

        self._edit_component("Change active planform drivers", change)

    def _on_sweep_loc_changed(self, loc_val_str: str) -> None:
        if self._loading:
            return
        sw_loc = float(loc_val_str)
        self._sweep_loc = sw_loc

        def change() -> None:
            self._geometry()["sweep_location"] = sw_loc

        self._edit_component("Change wing sweep location", change)
        self._refresh_planform_table()

    def _on_twist_loc_changed(self, twist_val_str: str) -> None:
        if self._loading:
            return
        twist_loc = float(twist_val_str)

        def change() -> None:
            self._geometry()["twist_location"] = twist_loc

        self._edit_component("Change wing twist axis location", change)

    def _is_symmetric(self) -> bool:
        geom = self._geometry()
        return bool(geom.get("mirror", False))

    def _y_offset(self) -> float:
        tf = self._component.get("transform")
        if isinstance(tf, dict):
            pos = tf.get("position")
            if isinstance(pos, dict):
                return float(pos.get("y", 0.0))
        return 0.0

    def _refresh_planform_table(self) -> None:
        """Recalculate all 8 planform parameters and update the interactive driver table."""
        was_loading = self._loading
        self._loading = True
        try:
            profiles = self._profiles()
            if len(profiles) < 2:
                return

            geom = self._geometry()
            sw_loc = float(geom.get("sweep_location", self._sweep_loc))
            self._sweep_loc = sw_loc

            metrics = compute_planform_metrics(
                profiles,
                sw_loc,
                symmetric=self._is_symmetric(),
                y_offset=self._y_offset(),
            )

            # 1. Update 8-Parameter 3-Driver Table
            planform_8 = compute_all_8_parameters(
                metrics["span"],
                metrics["root_chord"],
                metrics["tip_chord"],
                is_symmetric=self._is_symmetric(),
                y_offset=self._y_offset(),
            )
            active_drivers = geom.get("active_drivers")
            driver_exprs = geom.get("driver_expressions", {})
            self.planform_table.set_parameters(
                planform_8,
                active_drivers=active_drivers,
                expressions=driver_exprs,
                is_symmetric=self._is_symmetric(),
                y_offset=self._y_offset(),
            )

            # 2. Update Angles & Alignment Table
            if hasattr(self, "angles_table"):
                sw_val = (
                    get_expression(geom, "sweep")
                    or geom.get("sweep")
                    or float(metrics.get("sweep", 0.0))
                )
                self._set_property_expression(
                    self.angles_table,
                    "sweep",
                    sw_val,
                    target_data=geom,
                    raw_callback=True,
                    on_changed=lambda val: self._on_angle_changed("sweep", val),
                    label="Sweep Angle",
                    unit="deg",
                )
                self._set_property_combo(
                    self.angles_table,
                    "sweep_loc",
                    str(sw_loc),
                    [(str(val), label) for val, label in SWEEP_LOCATIONS],
                    self._on_sweep_loc_changed,
                )
                sw_curv = get_expression(geom, "sweep_curvature") or float(
                    geom.get("sweep_curvature", 0.0)
                )
                self._set_property_expression(
                    self.angles_table,
                    "sweep_curvature",
                    sw_curv,
                    target_data=geom,
                    raw_callback=True,
                    on_changed=lambda val: self._on_angle_changed("sweep_curvature", val),
                    label="Sweep Curvature",
                    unit="mm",
                )
                di_val = get_expression(geom, "dihedral") or float(metrics.get("dihedral", 0.0))
                self._set_property_expression(
                    self.angles_table,
                    "dihedral",
                    di_val,
                    target_data=geom,
                    raw_callback=True,
                    on_changed=lambda val: self._on_angle_changed("dihedral", val),
                    label="Dihedral Angle",
                    unit="deg",
                )
                tw_val = get_expression(geom, "twist") or float(metrics.get("washout", 0.0))
                self._set_property_expression(
                    self.angles_table,
                    "twist",
                    tw_val,
                    target_data=geom,
                    raw_callback=True,
                    on_changed=lambda val: self._on_angle_changed("twist", val),
                    label="Twist / Washout",
                    unit="deg",
                )
                twist_loc = float(self._geometry().get("twist_location", 0.25))
                self._set_property_combo(
                    self.angles_table,
                    "twist_axis",
                    str(twist_loc),
                    [(str(val), label) for val, label in TWIST_LOCATIONS],
                    self._on_twist_loc_changed,
                )
        finally:
            self._loading = was_loading

    def _on_angle_changed(self, key: str, value: Any) -> None:
        if self._loading:
            return
        profiles = self._profiles()
        sw_loc = self._sweep_loc
        geom = self._geometry()
        metrics = compute_planform_metrics(
            profiles,
            sw_loc,
            symmetric=self._is_symmetric(),
            y_offset=self._y_offset(),
        )

        cell = (
            self._property_cell(self.angles_table, key) if hasattr(self, "angles_table") else None
        )
        parsed = evaluate_table_cell_input(value, self._api, cell=cell, label=key)
        if parsed is None:
            return
        num_val, expr_to_store = parsed

        if key in ("sweep", "sweep_curvature"):
            sweep_val = float(
                num_val if key == "sweep" else (geom.get("sweep") or metrics.get("sweep", 0.0))
            )
            curv_val = float(
                num_val if key == "sweep_curvature" else geom.get("sweep_curvature", 0.0)
            )
            new_profiles = set_global_sweep(profiles, sweep_val, sw_loc, sweep_curvature=curv_val)

            def change() -> None:
                g = self._geometry()
                set_expression(g, key, expr_to_store)
                g["profiles"] = deepcopy(new_profiles)
                g["sweep"] = sweep_val
                g["sweep_curvature"] = curv_val
        elif key == "dihedral":
            new_profiles = set_global_dihedral(profiles, num_val)

            def change() -> None:
                g = self._geometry()
                set_expression(g, key, expr_to_store)
                g["profiles"] = deepcopy(new_profiles)
                g["dihedral"] = num_val
        elif key == "twist":
            new_profiles = set_global_twist(profiles, num_val)

            def change() -> None:
                g = self._geometry()
                set_expression(g, key, expr_to_store)
                g["profiles"] = deepcopy(new_profiles)
                g["washout"] = num_val
                g["twist"] = num_val
        else:
            return

        self._edit_component(f"Change {key}", change)
        self._populate_sections()
        self._refresh_planform_table()
        if 0 <= self._section_index < len(self._get_sections()):
            self._load_section(self._section_index)

    def _on_planform_driver_values_changed(self, new_metrics: dict[str, float]) -> None:
        if self._loading:
            return

        profiles = self._profiles()
        is_sym = self._is_symmetric()
        y_off = self._y_offset()
        sw_loc = self._sweep_loc

        metrics = compute_planform_metrics(
            profiles,
            sw_loc,
            symmetric=is_sym,
            y_offset=y_off,
        )

        inputs = {
            "span": new_metrics["span"],
            "root_chord": new_metrics["root_chord"],
            "tip_chord": new_metrics["tip_chord"],
            "sweep": float(metrics.get("sweep", 0.0)),
        }

        new_profiles, _ = solve_planform(
            "span_root_tip",
            inputs,
            profiles,
            sw_loc,
            symmetric=is_sym,
            y_offset=y_off,
        )

        def change() -> None:
            profiles.clear()
            profiles.extend(deepcopy(new_profiles))
            geom = self._geometry()
            geom["active_drivers"] = list(self.planform_table.get_active_drivers())
            driver_exprs = self.planform_table.get_driver_expressions()
            if driver_exprs:
                geom["driver_expressions"] = dict(driver_exprs)
            else:
                geom.pop("driver_expressions", None)

        self._edit_component("Parametric wing resize", change)

        self._populate_sections()
        self._refresh_planform_table()
        if 0 <= self._section_index < len(self._get_sections()):
            self._load_section(self._section_index)
        elif self._get_sections():
            self._load_section(0)

        self._refresh_control_surfaces()
