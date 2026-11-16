"""Loft primitive component: definition, editor, and 3D scene rendering."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QWidget

from setuav_studio.api import Component, ParameterField, TableParameterField
from setuav_studio.ui.viewport import ViewportProtocol
from setuav_studio.utilities.envelope import compute_loft_envelope

from .common import (
    DEBUG_LAYER,
    BaseDebugComponentEditor,
    parse_color_rgba,
    register_envelope,
    register_renderer,
    rotate_vector,
)

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

TYPE_DEBUG_LOFT = "org.setuav.debug:loft"

Point3D = tuple[float, float, float]


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


class LoftComponent(Component):
    """Loft primitive component definition with unit and parameter metadata."""

    COMPONENT_TYPE = TYPE_DEBUG_LOFT

    sweep = ParameterField(
        label="Sweep Angle",
        unit="°",
        field_type=float,
        default=5.0,
        min_value=-60.0,
        max_value=60.0,
        decimals=1,
        tooltip="Leading edge sweep angle in degrees",
    )
    dihedral = ParameterField(
        label="Dihedral Angle",
        unit="°",
        field_type=float,
        default=2.0,
        min_value=-45.0,
        max_value=45.0,
        decimals=1,
        tooltip="Dihedral angle in degrees",
    )
    color = ParameterField(
        label="Surface Color",
        field_type=str,
        default="#3498DB",
        widget_type="color",
        tooltip="Loft surface color in Hex",
    )
    stations = TableParameterField(
        key="sections",
        label="Stations",
        columns=(
            ParameterField(
                key="offset",
                label="Offset",
                unit="mm",
                field_type=float,
                default=0.0,
                decimals=1,
                tooltip="Spanwise station offset along Y",
            ),
            ParameterField(
                key="chord",
                label="Chord",
                unit="mm",
                field_type=float,
                default=150.0,
                min_value=1.0,
                decimals=1,
                tooltip="Chord length at this station",
            ),
            ParameterField(
                key="twist",
                label="Twist",
                unit="°",
                field_type=float,
                default=0.0,
                decimals=1,
                tooltip="Twist angle in degrees",
            ),
        ),
        default=(
            {"offset": 0.0, "chord": 180.0, "twist": 0.0},
            {"offset": 200.0, "chord": 135.0, "twist": 1.0},
            {"offset": 400.0, "chord": 90.0, "twist": 2.0},
        ),
        min_rows=2,
        tooltip="Parametric airfoil stations defining the loft",
    )


class LoftComponentEditor(BaseDebugComponentEditor):
    """Property editor for Loft primitive components."""

    def __init__(
        self, api: StudioAPI, component: dict[str, Any] | Component, parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=LoftComponent.get_fields(), parent=parent)


def create_loft_component(comp_id: str, name: str) -> LoftComponent:
    """Create data schema for a Loft debug component."""
    return LoftComponent(id=comp_id, name=name, mass=150.0)


def loft_section_loops(loft: LoftComponent) -> list[tuple[Point3D, ...]]:
    """Return the airfoil loops of the loft stations in the component frame."""
    sweep_rad = math.radians(float(loft.sweep))
    dih_rad = math.radians(float(loft.dihedral))
    loops: list[tuple[Point3D, ...]] = []
    for station in loft.stations:
        offset = float(station["offset"])
        chord = float(station["chord"])
        twist = float(station["twist"])
        st_x = offset * math.sin(sweep_rad)
        st_y = offset * math.cos(dih_rad)
        st_z = offset * math.sin(dih_rad)
        loop = naca_airfoil_loop(chord=chord, origin_x=st_x, y=st_y, origin_z=st_z)
        if abs(twist) > 1e-6:
            t_rad = math.radians(twist)
            loop = tuple(
                (
                    st_x + (lx - st_x) * math.cos(t_rad) + (lz - st_z) * math.sin(t_rad),
                    ly,
                    st_z - (lx - st_x) * math.sin(t_rad) + (lz - st_z) * math.cos(t_rad),
                )
                for lx, ly, lz in loop
            )
        loops.append(loop)
    return loops


def add_loft_to_viewport(
    viewport: ViewportProtocol,
    comp_id: str,
    name: str,
    params: dict[str, Any] | LoftComponent,
    px: float,
    py: float,
    pz: float,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    _envelope: dict[str, Any] | None = None,
) -> None:
    """Add or update a loft primitive in the 3D viewport.

    The viewport derives the loft's display envelope from its world-space sections.
    """
    loft = params if isinstance(params, LoftComponent) else LoftComponent(params)
    sec_loops = [
        tuple(
            (px + rx, py + ry, pz + rz)
            for rx, ry, rz in (rotate_vector(point, rotation) for point in loop)
        )
        for loop in loft_section_loops(loft)
    ]
    viewport.add_loft(
        comp_id,
        sections=sec_loops,
        name=name,
        layer=DEBUG_LAYER,
        color=parse_color_rgba(loft.color),
    )


def loft_envelope(params: dict[str, Any]) -> dict[str, Any] | None:
    """Exact envelope of the closed loft through the station airfoils.

    A loft with fewer than two stations has no volume and so no envelope.
    """
    loops = loft_section_loops(LoftComponent(params))
    if len(loops) < 2:
        return None
    return compute_loft_envelope(loops)


register_renderer(TYPE_DEBUG_LOFT, add_loft_to_viewport)
register_envelope(TYPE_DEBUG_LOFT, loft_envelope)
