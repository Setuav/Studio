"""Wing planform sizing and overall angles for the Lifting Surface Editor."""

from __future__ import annotations

from typing import Any

from setuav_studio.model.expression import get_expression, set_expression
from setuav_studio.ui.widget.spinbox import evaluate_table_cell_input
from setuav_studio.utilities.transform import get_local_transform

from ...engine.lifting_surface_driver_solver import PLANFORM_PARAM_KEYS
from ...engine.lifting_surface_layout import (
    layout_planform,
    set_overall_angle,
    set_planform,
)
from ...engine.lifting_surface_planform_engine import SWEEP_LOCATIONS, TWIST_LOCATIONS
from .host import LiftingSurfaceEditorHost
from .planform_driver_table import DriverPlanformTable

# The overall angle rows: key and label.
_ANGLE_ROWS = {"sweep": "Sweep Angle", "dihedral": "Dihedral Angle", "twist": "Twist / Washout"}


class PlanformSectionMixin(LiftingSurfaceEditorHost):
    """The wing's planform drivers and its overall sweep, dihedral and twist.

    The values are measured from the sections. A number typed into a driver or an angle
    changes the sections at once; a formula is stored on the wing's planform and keeps
    changing them whenever it evaluates to a new value.
    """

    # -------------------------------------------------------------------------
    # UI Sections Creation
    # -------------------------------------------------------------------------

    def _create_planform_section(self) -> None:
        """Parametric Planform table (8 parameters with 3-driver checkbox system)."""
        layout = self._create_section("Planform", "fa6s.ruler-combined")
        self.planform_table = DriverPlanformTable(
            active_drivers=self._planform()["active_drivers"],
            on_driver_changed=self._on_planform_driver_changed,
            on_drivers_changed=self._on_planform_drivers_changed,
            api=self._api,
        )
        layout.addWidget(self.planform_table)

    def _create_angles_section(self) -> None:
        """Overall sweep, dihedral and twist with their reference chord locations."""
        layout = self._create_section("Angles", "fa6s.arrows-spin")

        self.angles_table = self._property_table(
            [
                ("sweep", "Sweep Angle"),
                ("sweep_loc", "Sweep Location"),
                ("dihedral", "Dihedral Angle"),
                ("twist", "Twist / Washout"),
                ("twist_axis", "Twist Axis Location"),
            ]
        )
        layout.addWidget(self.angles_table)

    # -------------------------------------------------------------------------
    # Planform Sizing & Angles Logic
    # -------------------------------------------------------------------------

    def _planform(self) -> dict[str, Any]:
        return self._geometry()["planform"]

    def _on_planform_drivers_changed(self, active_drivers: list[str]) -> None:
        if self._loading:
            return

        def change(geometry: dict[str, Any]) -> None:
            planform = geometry["planform"]
            planform["active_drivers"] = list(active_drivers)
            # A formula only drives the planform while its driver is active.
            for key in PLANFORM_PARAM_KEYS:
                if key not in active_drivers:
                    set_expression(planform, key, None)
                    planform.pop(key, None)

        self._edit_layout("Change active planform drivers", change)
        self._refresh_planform_table()

    def _on_planform_driver_changed(self, key: str, value: float, expression: str | None) -> None:
        if self._loading:
            return
        symmetric = self._is_symmetric()
        y_offset = self._y_offset()

        def change(geometry: dict[str, Any]) -> None:
            planform = geometry["planform"]
            set_expression(planform, key, expression)
            if expression is None:
                planform.pop(key, None)
                set_planform(geometry, {key: value}, symmetric=symmetric, y_offset=y_offset)
            else:
                planform[key] = value

        self._edit_layout(f"Change wing {key.replace('_', ' ')}", change)
        self._after_planform_edit()

    def _on_angle_changed(self, key: str, text: str) -> None:
        if self._loading:
            return
        parsed = evaluate_table_cell_input(
            text,
            self._api,
            cell=self._property_cell(self.angles_table, key),
            label=_ANGLE_ROWS[key],
        )
        if parsed is None:
            return
        value, expression = parsed

        def change(geometry: dict[str, Any]) -> None:
            planform = geometry["planform"]
            set_expression(planform, key, expression)
            if expression is None:
                planform.pop(key, None)
                set_overall_angle(geometry, key, value)
            else:
                planform[key] = value

        self._edit_layout(f"Change wing {key}", change)
        self._after_planform_edit()

    def _after_planform_edit(self) -> None:
        self._populate_sections()
        self._refresh_planform_table()
        if 0 <= self._section_index < len(self._get_sections()):
            self._load_section(self._section_index)
        self._refresh_control_surfaces()

    def _on_sweep_loc_changed(self, loc_val_str: str) -> None:
        if self._loading:
            return
        sw_loc = float(loc_val_str)

        def change(geometry: dict[str, Any]) -> None:
            geometry["sweep_location"] = sw_loc

        self._edit_layout("Change wing sweep location", change)
        self._refresh_planform_table()

    def _on_twist_loc_changed(self, twist_val_str: str) -> None:
        if self._loading:
            return
        twist_loc = float(twist_val_str)

        def change(geometry: dict[str, Any]) -> None:
            geometry["twist_location"] = twist_loc

        self._edit_layout("Change wing twist axis location", change)

    def _is_symmetric(self) -> bool:
        return self._geometry().get("mirror") is True

    def _y_offset(self) -> float:
        (_x, y_offset, _z), _rotation = get_local_transform(self._component)
        return y_offset

    def _refresh_planform_table(self) -> None:
        """Show the planform drivers and overall angles measured from the sections."""
        was_loading = self._loading
        self._loading = True
        try:
            geom = self._geometry()
            planform = geom["planform"]
            values = layout_planform(
                geom, symmetric=self._is_symmetric(), y_offset=self._y_offset()
            )
            self.planform_table.set_parameters(
                values,
                active_drivers=planform["active_drivers"],
                expressions={
                    key: expression
                    for key in PLANFORM_PARAM_KEYS
                    if (expression := get_expression(planform, key)) is not None
                },
            )

            for key, label in _ANGLE_ROWS.items():
                self._set_property_expression(
                    self.angles_table,
                    key,
                    get_expression(planform, key) or values[key],
                    raw_callback=True,
                    on_changed=lambda text, k=key: self._on_angle_changed(k, text),
                    label=label,
                    unit="deg",
                )
            self._set_property_combo(
                self.angles_table,
                "sweep_loc",
                str(float(geom["sweep_location"])),
                [(str(val), label) for val, label in SWEEP_LOCATIONS],
                self._on_sweep_loc_changed,
            )
            self._set_property_combo(
                self.angles_table,
                "twist_axis",
                str(float(geom.get("twist_location", 0.25))),
                [(str(val), label) for val, label in TWIST_LOCATIONS],
                self._on_twist_loc_changed,
            )
        finally:
            self._loading = was_loading
