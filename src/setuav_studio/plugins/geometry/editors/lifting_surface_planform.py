"""Wing Planform Sizing & Angles handling for the Lifting Surface Editor."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Qt

from ..engine.wing_driver_solver import compute_all_8_parameters
from ..engine.wing_planform_engine import (
    SWEEP_LOCATIONS,
    TWIST_LOCATIONS,
    compute_planform_metrics,
    set_wing_global_dihedral,
    set_wing_global_sweep,
    set_wing_global_twist,
    solve_wing_planform,
)
from .wing_driver_table import DriverPlanformTable


class PlanformMixin:
    """8-Variable 3-Driver Wing Planform Sizing and Wing Angles/Alignment logic."""

    # -------------------------------------------------------------------------
    # UI Sections Creation
    # -------------------------------------------------------------------------

    def _create_planform_sizing_section(self) -> None:
        """Parametric Wing Planform table (8 parameters with 3-driver checkbox system)."""
        layout = self._create_section("Wing Planform", "fa6s.ruler-combined")

        self.planform_table = DriverPlanformTable(
            default_drivers=["area", "aspect_ratio", "taper_ratio"],
            on_values_changed=self._on_wing_driver_values_changed,
            api=getattr(self, "_api", None),
        )
        layout.addWidget(self.planform_table)

    def _create_wing_angles_section(self) -> None:
        """Global Wing Sweep, Dihedral, Twist/Washout, and Reference Axes table section."""
        layout = self._create_section("Wing Angles", "fa6s.arrows-spin")

        self.wing_angles_table = self._property_table(
            [
                ("sweep", "Sweep Angle (°)"),
                ("sweep_loc", "Sweep Location"),
                ("sweep_curvature", "Sweep Curvature (mm)"),
                ("dihedral", "Dihedral Angle (°)"),
                ("twist", "Twist / Washout (°)"),
                ("twist_axis", "Twist Axis Location"),
            ]
        )
        layout.addWidget(self.wing_angles_table)

    # -------------------------------------------------------------------------
    # Planform Sizing & Angles Logic
    # -------------------------------------------------------------------------

    def _sync_driver_mode_from_project(self) -> None:
        pass

    def _load_driver_groups_table(self) -> None:
        pass

    def _on_driver_mode_changed(self, mode_val: str) -> None:
        pass

    def _on_sweep_loc_changed(self, loc_val_str: str) -> None:
        if self._loading:
            return
        try:
            sw_loc = float(loc_val_str)
        except ValueError:
            sw_loc = 0.25
        self._sweep_loc = sw_loc

        def change() -> None:
            self._geometry()["sweep_location"] = sw_loc

        self._edit_component("Change wing sweep location", change)
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
        """Recalculate all 8 planform parameters and update the interactive driver table."""
        was_loading = self._loading
        self._loading = True
        try:
            profiles = self._profiles()
            if len(profiles) < 2:
                return

            geom = self._geometry()
            sw_loc = float(geom.get("sweep_location", getattr(self, "_sweep_loc", 0.25)))
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
            driver_exprs = geom.get("driver_expressions", {})
            self.planform_table.set_parameters(
                planform_8,
                expressions=driver_exprs,
                is_symmetric=self._is_symmetric(),
                y_offset=self._y_offset(),
            )

            # 2. Update Wing Angles & Alignment Table
            if hasattr(self, "wing_angles_table"):
                sw_val = geom.get("sweep_expression") or float(metrics.get("sweep", 0.0))
                self._set_property_expression(
                    self.wing_angles_table,
                    "sweep",
                    sw_val,
                    on_changed=lambda val: self._on_wing_angle_changed("sweep", val),
                    label="Sweep Angle",
                )
                self._set_property_combo(
                    self.wing_angles_table,
                    "sweep_loc",
                    str(sw_loc),
                    [(str(val), label) for val, label in SWEEP_LOCATIONS],
                    self._on_sweep_loc_changed,
                )
                sw_curv = geom.get("sweep_curvature_expression") or float(
                    geom.get("sweep_curvature", 0.0)
                )
                self._set_property_expression(
                    self.wing_angles_table,
                    "sweep_curvature",
                    sw_curv,
                    on_changed=lambda val: self._on_wing_angle_changed("sweep_curvature", val),
                    label="Sweep Curvature",
                )
                di_val = geom.get("dihedral_expression") or float(metrics.get("dihedral", 0.0))
                self._set_property_expression(
                    self.wing_angles_table,
                    "dihedral",
                    di_val,
                    on_changed=lambda val: self._on_wing_angle_changed("dihedral", val),
                    label="Dihedral Angle",
                )
                tw_val = geom.get("twist_expression") or float(metrics.get("washout", 0.0))
                self._set_property_expression(
                    self.wing_angles_table,
                    "twist",
                    tw_val,
                    on_changed=lambda val: self._on_wing_angle_changed("twist", val),
                    label="Twist / Washout",
                )
                twist_loc = float(self._geometry().get("twist_location", 0.25))
                self._set_property_combo(
                    self.wing_angles_table,
                    "twist_axis",
                    str(twist_loc),
                    [(str(val), label) for val, label in TWIST_LOCATIONS],
                    self._on_twist_loc_changed,
                )

            self._update_profiles_table_interactivity()
        finally:
            self._loading = was_loading

    def _on_wing_angle_changed(self, key: str, value: Any) -> None:
        if self._loading:
            return
        profiles = self._profiles()
        sw_loc = getattr(self, "_sweep_loc", 0.25)
        geom = self._geometry()
        metrics = compute_planform_metrics(
            profiles,
            sw_loc,
            symmetric=self._is_symmetric(),
            y_offset=self._y_offset(),
        )

        num_val: float | None = None
        val_str = str(value).strip() if value is not None else ""

        if val_str.startswith("=") or not val_str.replace(".", "", 1).replace("-", "", 1).isdigit():
            # Expression formula
            geom[f"{key}_expression"] = val_str
            api = getattr(self, "_api", None)
            if api is not None and getattr(api, "current_project", None) is not None:
                try:
                    from setuav_studio.plugins.core.expressions import ExpressionEvaluator

                    evaluator = ExpressionEvaluator()
                    scope = api.current_project.get_scope(api=api)
                    expr = val_str.lstrip("=").strip()
                    res = evaluator.evaluate(expr, scope)
                    if isinstance(res, (int, float)):
                        num_val = float(res)
                except Exception:
                    pass
        else:
            geom.pop(f"{key}_expression", None)
            try:
                num_val = float(val_str)
            except ValueError:
                pass

        if num_val is None:
            return

        if key in ("sweep", "sweep_curvature"):
            sweep_val = float(num_val if key == "sweep" else metrics.get("sweep", 0.0))
            curv_val = float(
                num_val if key == "sweep_curvature" else geom.get("sweep_curvature", 0.0)
            )
            new_profiles = set_wing_global_sweep(
                profiles, sweep_val, sw_loc, sweep_curvature=curv_val
            )
            geom["sweep_curvature"] = curv_val
        elif key == "dihedral":
            new_profiles = set_wing_global_dihedral(profiles, num_val)
        elif key == "twist":
            new_profiles = set_wing_global_twist(profiles, num_val)
        else:
            return

        def change() -> None:
            profiles.clear()
            profiles.extend(deepcopy(new_profiles))

        self._edit_component(f"Change wing {key}", change)
        self._populate_sections()
        self._refresh_planform_table()
        if 0 <= getattr(self, "_section_index", -1) < len(self._get_sections()):
            self._load_section(self._section_index)

    def _on_wing_driver_values_changed(self, new_metrics: dict[str, float]) -> None:
        if self._loading:
            return

        profiles = self._profiles()
        is_sym = self._is_symmetric()
        y_off = self._y_offset()
        sw_loc = getattr(self, "_sweep_loc", 0.25)
        geom = self._geometry()

        # Preserve driver expressions in component parameters
        driver_exprs = self.planform_table.get_driver_expressions()
        if driver_exprs:
            geom["driver_expressions"] = driver_exprs
        else:
            geom.pop("driver_expressions", None)

        inputs = {
            "span": new_metrics["span"],
            "root_chord": new_metrics["root_chord"],
            "tip_chord": new_metrics["tip_chord"],
            "sweep": 0.0,
        }

        new_profiles, _ = solve_wing_planform(
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
            self._sync_project_parameters(new_metrics, "planform")

        self._edit_component("Parametric wing resize", change)

        self._populate_sections()
        if 0 <= getattr(self, "_section_index", -1) < len(self._get_sections()):
            self._load_section(self._section_index)
        elif self._get_sections():
            self._load_section(0)

        if hasattr(self, "_sync_control_surfaces_with_wing"):
            self._sync_control_surfaces_with_wing()

    def _on_planform_spinbox_changed(self, key: str, val_num: float) -> None:
        if self._loading:
            return
        inputs = self.planform_table.get_current_values()
        inputs[key] = float(val_num)
        self._on_wing_driver_values_changed(inputs)

    def _on_planform_parameter_edited(self, row: int, column: int) -> None:
        pass

    def _sync_project_parameters(self, inputs: dict[str, float], edited_key: str) -> None:
        """Sync updated macro parameters to project.data['parameters'] if present."""
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)
        if not project or not isinstance(project.data.get("parameters"), dict):
            return
        params = project.data["parameters"]
        comp_id = str(self._component.get("id") or "")
        is_main_wing = comp_id in ("main-wing", "wing", "wing-1", "")

        if is_main_wing:
            if "wing_area" in params and isinstance(params["wing_area"], dict) and "area" in inputs:
                params["wing_area"]["value"] = float(inputs["area"])
            if (
                "wing_aspect_ratio" in params
                and isinstance(params["wing_aspect_ratio"], dict)
                and "aspect_ratio" in inputs
            ):
                params["wing_aspect_ratio"]["value"] = float(inputs["aspect_ratio"])
            if "wingspan" in params and isinstance(params["wingspan"], dict) and "span" in inputs:
                params["wingspan"]["value"] = float(inputs["span"])
        else:
            comp_area_key = f"{comp_id}_area"
            if (
                comp_area_key in params
                and isinstance(params[comp_area_key], dict)
                and "area" in inputs
            ):
                params[comp_area_key]["value"] = float(inputs["area"])
            comp_span_key = f"{comp_id}_span"
            if (
                comp_span_key in params
                and isinstance(params[comp_span_key], dict)
                and "span" in inputs
            ):
                params[comp_span_key]["value"] = float(inputs["span"])

    def _update_profiles_table_interactivity(self) -> None:
        """Ensure sections table is fully interactive."""
        table = getattr(self, "sections_table", None)
        if table is not None:
            for r in range(table.rowCount()):
                for c in range(1, table.columnCount()):
                    try:
                        item = table.item(r, c)
                        if item:
                            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    except RuntimeError:
                        pass
