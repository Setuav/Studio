"""Visual primitive generation and demonstration helpers for the Debug plugin."""

from __future__ import annotations

import math
from typing import Any

DEBUG_LAYER = "debug"

Point3D = tuple[float, float, float]


def _naca_airfoil_loop(
    chord: float,
    origin_x: float,
    y: float,
    origin_z: float,
    thickness: float = 0.12,
    points_per_side: int = 16,
) -> tuple[Point3D, ...]:
    """Generate a closed 3D NACA 00xx airfoil loop."""
    pts: list[Point3D] = []
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


def add_debug_box(viewport: Any) -> None:
    """Add a sample 3D Box primitive."""
    viewport.add_box(
        object_id="debug.box",
        center=(0.0, 0.0, 80.0),
        size=(200.0, 140.0, 80.0),
        name="Debug Box",
        layer=DEBUG_LAYER,
        color=(0.2, 0.6, 1.0, 0.7),
        wireframe=True,
        solid=True,
    )
    viewport.fit_view()


def add_debug_cylinder(viewport: Any) -> None:
    """Add a sample 3D Cylinder primitive."""
    viewport.add_cylinder(
        object_id="debug.cylinder",
        start=(-180.0, 0.0, 60.0),
        end=(180.0, 0.0, 60.0),
        radius=40.0,
        name="Debug Cylinder",
        layer=DEBUG_LAYER,
        color=(0.85, 0.35, 0.25, 0.85),
        wireframe=True,
        solid=True,
        segments=32,
    )
    viewport.fit_view()


def add_debug_ring(viewport: Any) -> None:
    """Add a sample circular Ring / Propeller Disk wireframe."""
    viewport.add_ring(
        object_id="debug.ring",
        center=(0.0, 0.0, 120.0),
        normal=(0.0, 0.0, 1.0),
        radius=130.0,
        name="Debug Ring",
        layer=DEBUG_LAYER,
        color=(1.0, 0.75, 0.1, 1.0),
        segments=48,
    )
    viewport.fit_view()


def add_debug_plane(viewport: Any) -> None:
    """Add a sample bounded flat Plane primitive."""
    viewport.add_plane(
        object_id="debug.plane",
        center=(0.0, 0.0, 0.0),
        normal=(0.0, 0.0, 1.0),
        width=400.0,
        height=300.0,
        name="Debug Plane",
        layer=DEBUG_LAYER,
        color=(0.2, 0.8, 0.4, 0.45),
        wireframe=True,
        solid=True,
    )
    viewport.fit_view()


def add_debug_lines(viewport: Any) -> None:
    """Add sample Line Segments (3D coordinate triad and frame)."""
    lines: list[tuple[Point3D, Point3D]] = [
        # X-axis line (longitudinal)
        ((0.0, 0.0, 0.0), (300.0, 0.0, 0.0)),
        # Y-axis line (lateral)
        ((0.0, 0.0, 0.0), (0.0, 300.0, 0.0)),
        # Z-axis line (vertical)
        ((0.0, 0.0, 0.0), (0.0, 0.0, 300.0)),
        # Frame box
        ((300.0, 0.0, 0.0), (300.0, 300.0, 0.0)),
        ((0.0, 300.0, 0.0), (300.0, 300.0, 0.0)),
        ((300.0, 0.0, 0.0), (300.0, 0.0, 300.0)),
        ((0.0, 300.0, 0.0), (0.0, 300.0, 300.0)),
        ((0.0, 0.0, 300.0), (300.0, 0.0, 300.0)),
        ((0.0, 0.0, 300.0), (0.0, 300.0, 300.0)),
        ((300.0, 300.0, 0.0), (300.0, 300.0, 300.0)),
        ((300.0, 0.0, 300.0), (300.0, 300.0, 300.0)),
        ((0.0, 300.0, 300.0), (300.0, 300.0, 300.0)),
    ]
    viewport.add_lines(
        object_id="debug.lines",
        lines=lines,
        name="Debug Lines",
        layer=DEBUG_LAYER,
        color=(0.95, 0.9, 0.15, 1.0),
    )
    viewport.fit_view()


def add_debug_triangles(viewport: Any) -> None:
    """Add a sample faceted 3D mesh (Pyramid) using Triangles primitive."""
    apex: Point3D = (0.0, 0.0, 160.0)
    b1: Point3D = (-120.0, -90.0, 0.0)
    b2: Point3D = (120.0, -90.0, 0.0)
    b3: Point3D = (120.0, 90.0, 0.0)
    b4: Point3D = (-120.0, 90.0, 0.0)

    triangles: list[tuple[Point3D, Point3D, Point3D]] = [
        # Base quad (two triangles)
        (b1, b2, b3),
        (b1, b3, b4),
        # 4 lateral faces
        (b1, b2, apex),
        (b2, b3, apex),
        (b3, b4, apex),
        (b4, b1, apex),
    ]
    viewport.add_triangles(
        object_id="debug.triangles",
        triangles=triangles,
        name="Debug Triangles (Pyramid)",
        layer=DEBUG_LAYER,
        color=(0.65, 0.35, 0.85, 0.8),
        solid=True,
    )
    viewport.fit_view()


def add_debug_loft(viewport: Any) -> None:
    """Add a sample tapered swept wing loft using Loft primitive."""
    sec_root = _naca_airfoil_loop(chord=300.0, origin_x=0.0, y=0.0, origin_z=50.0)
    sec_mid = _naca_airfoil_loop(chord=200.0, origin_x=60.0, y=250.0, origin_z=65.0)
    sec_tip = _naca_airfoil_loop(chord=100.0, origin_x=120.0, y=500.0, origin_z=80.0)

    viewport.add_loft(
        object_id="debug.loft",
        sections=[sec_root, sec_mid, sec_tip],
        name="Debug Wing Loft",
        layer=DEBUG_LAYER,
        color=(1.0, 0.82, 0.10, 0.95),
        interpolation="smooth",
        parameterization="centripetal",
        station_spacing=10.0,
        closed_ends=True,
        wireframe=True,
        solid=True,
    )
    viewport.fit_view()


def add_debug_points(viewport: Any) -> None:
    """Add a sample Point Cloud (rendered as 3D crosshairs)."""
    points: list[Point3D] = []
    # A double helix / spiral
    for deg in range(0, 720, 15):
        rad = math.radians(deg)
        r = 120.0
        z = deg * 0.4
        points.append((r * math.cos(rad), r * math.sin(rad), z))
    viewport.add_points(
        object_id="debug.points",
        points=points,
        name="Debug Point Cloud",
        layer=DEBUG_LAYER,
        color=(1.0, 0.35, 0.1, 1.0),
        size=6.0,
    )
    viewport.fit_view()


def add_debug_arrows(viewport: Any) -> None:
    """Add sample directional Vector Arrows."""
    arrows: list[tuple[Point3D, Point3D]] = [
        # Lift vector (Z-up)
        ((0.0, 0.0, 50.0), (0.0, 0.0, 250.0)),
        # Thrust vector (X-forward)
        ((-150.0, 0.0, 50.0), (100.0, 0.0, 50.0)),
        # Side force vector (Y-spanwise)
        ((0.0, 0.0, 50.0), (0.0, 180.0, 50.0)),
    ]
    viewport.add_arrows(
        object_id="debug.arrows",
        arrows=arrows,
        name="Debug Arrows",
        layer=DEBUG_LAYER,
        color=(0.1, 0.85, 0.85, 1.0),
    )
    viewport.fit_view()


def add_debug_scene(viewport: Any) -> None:
    """Add a complete assembled UAV demonstration scene using all primitives."""
    # 1. Fuselage cylinder
    viewport.add_cylinder(
        object_id="debug.scene.fuselage",
        start=(-300.0, 0.0, 60.0),
        end=(350.0, 0.0, 60.0),
        radius=45.0,
        name="Fuselage",
        layer=DEBUG_LAYER,
        color=(0.85, 0.35, 0.25, 0.9),
        wireframe=True,
        solid=True,
        segments=32,
    )

    # 2. Right wing loft
    r_root = _naca_airfoil_loop(chord=280.0, origin_x=-50.0, y=30.0, origin_z=60.0)
    r_mid = _naca_airfoil_loop(chord=190.0, origin_x=0.0, y=280.0, origin_z=75.0)
    r_tip = _naca_airfoil_loop(chord=110.0, origin_x=60.0, y=550.0, origin_z=90.0)
    viewport.add_loft(
        object_id="debug.scene.wing_right",
        sections=[r_root, r_mid, r_tip],
        name="Right Wing",
        layer=DEBUG_LAYER,
        color=(1.0, 0.82, 0.10, 0.95),
        interpolation="smooth",
        parameterization="centripetal",
        station_spacing=10.0,
        closed_ends=True,
        wireframe=True,
        solid=True,
    )

    # 3. Left wing loft
    l_root = _naca_airfoil_loop(chord=280.0, origin_x=-50.0, y=-30.0, origin_z=60.0)
    l_mid = _naca_airfoil_loop(chord=190.0, origin_x=0.0, y=-280.0, origin_z=75.0)
    l_tip = _naca_airfoil_loop(chord=110.0, origin_x=60.0, y=-550.0, origin_z=90.0)
    viewport.add_loft(
        object_id="debug.scene.wing_left",
        sections=[l_root, l_mid, l_tip],
        name="Left Wing",
        layer=DEBUG_LAYER,
        color=(1.0, 0.82, 0.10, 0.95),
        interpolation="smooth",
        parameterization="centripetal",
        station_spacing=10.0,
        closed_ends=True,
        wireframe=True,
        solid=True,
    )

    # 4. Propeller disk rings
    viewport.add_ring(
        object_id="debug.scene.prop_right",
        center=(40.0, 200.0, 100.0),
        normal=(0.0, 0.0, 1.0),
        radius=110.0,
        name="Right Propeller Disk",
        layer=DEBUG_LAYER,
        color=(0.2, 0.7, 1.0, 1.0),
        segments=40,
    )
    viewport.add_ring(
        object_id="debug.scene.prop_left",
        center=(40.0, -200.0, 100.0),
        normal=(0.0, 0.0, 1.0),
        radius=110.0,
        name="Left Propeller Disk",
        layer=DEBUG_LAYER,
        color=(0.2, 0.7, 1.0, 1.0),
        segments=40,
    )

    # 5. Avionics/Payload bounding box
    viewport.add_box(
        object_id="debug.scene.payload",
        center=(-20.0, 0.0, 60.0),
        size=(120.0, 70.0, 60.0),
        name="Avionics Payload",
        layer=DEBUG_LAYER,
        color=(0.2, 0.6, 1.0, 0.5),
        wireframe=True,
        solid=True,
    )

    # 6. Nose sensor point
    viewport.add_points(
        object_id="debug.scene.sensors",
        points=[(360.0, 0.0, 60.0)],
        name="Pitot Sensor",
        layer=DEBUG_LAYER,
        color=(1.0, 0.2, 0.2, 1.0),
        size=8.0,
    )

    # 7. Velocity vector arrow
    viewport.add_arrows(
        object_id="debug.scene.velocity",
        arrows=[((360.0, 0.0, 60.0), (500.0, 0.0, 60.0))],
        name="Velocity Vector",
        layer=DEBUG_LAYER,
        color=(0.1, 0.9, 0.4, 1.0),
    )

    viewport.fit_view()


def clear_debug_objects(viewport: Any) -> None:
    """Remove all debug primitives from the viewport."""
    viewport.clear(layer=DEBUG_LAYER)
    viewport.fit_view()
