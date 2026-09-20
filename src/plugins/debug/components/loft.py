"""Loft primitive component: definition, editor, and 3D scene rendering."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QWidget

from setuav_studio_sdk import ParameterField, ViewportProtocol

from .common import (
    DEBUG_LAYER,
    BaseDebugComponentEditor,
    parse_color_rgba,
    register_renderer,
    rotate_vector,
)

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI

TYPE_DEBUG_LOFT = "org.setuav.debug:loft"


def naca_airfoil_loop(
    chord: float = 200.0,
    origin_x: float = 0.0,
    y: float = 0.0,
    origin_z: float = 0.0,
    thickness: float = 0.12,
    points_per_side: int = 16,
) -> tuple[tuple[float, float, float], ...]:
    """Generate a closed loop of (x, y, z) points describing a symmetric NACA airfoil."""
    pts: list[tuple[float, float, float]] = []
    # Upper surface: trailing edge to leading edge
    for i in range(points_per_side, -1, -1):
        x_frac = (1.0 - math.cos(i * math.pi / points_per_side)) / 2.0
        yt = (
            5.0
            * thickness
            * (
                0.2969 * math.sqrt(x_frac)
                - 0.1260 * x_frac
                - 0.3516 * (x_frac**2)
                + 0.2843 * (x_frac**3)
                - 0.1015 * (x_frac**4)
            )
        )
        px = origin_x + x_frac * chord
        pz = origin_z + yt * chord
        pts.append((px, y, pz))
    # Lower surface: leading edge back to trailing edge
    for i in range(1, points_per_side + 1):
        x_frac = (1.0 - math.cos(i * math.pi / points_per_side)) / 2.0
        yt = (
            5.0
            * thickness
            * (
                0.2969 * math.sqrt(x_frac)
                - 0.1260 * x_frac
                - 0.3516 * (x_frac**2)
                + 0.2843 * (x_frac**3)
                - 0.1015 * (x_frac**4)
            )
        )
        px = origin_x + x_frac * chord
        pz = origin_z - yt * chord
        pts.append((px, y, pz))
    return tuple(pts)


class LoftComponentEditor(BaseDebugComponentEditor):
    """Property editor for Loft primitive components."""

    FIELDS = (
        ParameterField(
            key="span",
            label="Wingspan",
            unit="mm",
            field_type=float,
            default=400.0,
            min_value=1.0,
            max_value=50000.0,
            decimals=1,
            tooltip="Span distance along Y axis",
        ),
        ParameterField(
            key="root_chord",
            label="Root Chord",
            unit="mm",
            field_type=float,
            default=180.0,
            min_value=1.0,
            max_value=10000.0,
            decimals=1,
            tooltip="Chord length at root section",
        ),
        ParameterField(
            key="tip_chord",
            label="Tip Chord",
            unit="mm",
            field_type=float,
            default=90.0,
            min_value=1.0,
            max_value=10000.0,
            decimals=1,
            tooltip="Chord length at tip section",
        ),
        ParameterField(
            key="sweep",
            label="Sweep Angle",
            unit="°",
            field_type=float,
            default=5.0,
            min_value=-60.0,
            max_value=60.0,
            decimals=1,
            tooltip="Leading edge sweep angle in degrees",
        ),
        ParameterField(
            key="dihedral",
            label="Dihedral Angle",
            unit="°",
            field_type=float,
            default=2.0,
            min_value=-45.0,
            max_value=45.0,
            decimals=1,
            tooltip="Dihedral angle in degrees",
        ),
        ParameterField(
            key="color",
            label="Surface Color",
            field_type=str,
            default="#3498DB",
            widget_type="color",
            tooltip="Loft surface color in Hex",
        ),
    )

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)


def create_loft_component(comp_id: str, name: str) -> dict[str, Any]:
    """Create data schema for a Loft debug component."""
    return {
        "kind": "component",
        "id": comp_id,
        "name": name,
        "type": TYPE_DEBUG_LOFT,
        "parent": None,
        "mass": 150.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "parameters": {
            "span": 400.0,
            "root_chord": 180.0,
            "tip_chord": 90.0,
            "sweep": 5.0,
            "dihedral": 2.0,
            "color": "#3498DB",
        },
    }


def add_loft_to_viewport(
    viewport: ViewportProtocol,
    comp_id: str,
    name: str,
    params: dict[str, Any],
    px: float,
    py: float,
    pz: float,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    envelope: dict[str, Any] | None = None,
) -> None:
    """Add or update a loft primitive in the 3D viewport."""
    span = float(params.get("span", 400.0))
    rc = float(params.get("root_chord", 180.0))
    tc = float(params.get("tip_chord", 90.0))
    sweep_deg = float(params.get("sweep", 5.0))
    dihedral_deg = float(params.get("dihedral", 2.0))
    color = parse_color_rgba(params.get("color", "#3498DB"))
    sweep_rad = math.radians(sweep_deg)
    dih_rad = math.radians(dihedral_deg)
    tip_x = px + span * math.sin(sweep_rad)
    tip_y = py + span * math.cos(dih_rad)
    tip_z = pz + span * math.sin(dih_rad)
    mid_x = (px + tip_x) / 2.0
    mid_y = (py + tip_y) / 2.0
    mid_z = (pz + tip_z) / 2.0
    mid_chord = (rc + tc) / 2.0
    sec_root = naca_airfoil_loop(chord=rc, origin_x=px, y=py, origin_z=pz)
    sec_mid = naca_airfoil_loop(chord=mid_chord, origin_x=mid_x, y=mid_y, origin_z=mid_z)
    sec_tip = naca_airfoil_loop(chord=tc, origin_x=tip_x, y=tip_y, origin_z=tip_z)

    if abs(rotation[0]) > 1e-6 or abs(rotation[1]) > 1e-6 or abs(rotation[2]) > 1e-6:

        def rot_loop(
            loop: tuple[tuple[float, float, float], ...],
        ) -> tuple[tuple[float, float, float], ...]:
            res: list[tuple[float, float, float]] = []
            for x, y, z in loop:
                rx, ry, rz = rotate_vector((x - px, y - py, z - pz), rotation)
                res.append((px + rx, py + ry, pz + rz))
            return tuple(res)

        sec_root = rot_loop(sec_root)
        sec_mid = rot_loop(sec_mid)
        sec_tip = rot_loop(sec_tip)

    viewport.add_loft(
        comp_id,
        sections=[sec_root, sec_mid, sec_tip],
        name=name,
        layer=DEBUG_LAYER,
        color=color,
        envelope=envelope,
    )


register_renderer(TYPE_DEBUG_LOFT, add_loft_to_viewport)
