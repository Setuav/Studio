"""Mathematical utilities for airfoil branches, structured sampling, and 3D rotations."""

from __future__ import annotations

import math
from typing import Any

from .data import Point3D, Section


def mapping(value: object) -> dict[str, Any]:
    """Ensure value is a dictionary."""
    return value if isinstance(value, dict) else {}


def number(value: Any) -> float:
    """Safe float conversion."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def split_airfoil_upper_lower(
    coords: tuple[tuple[float, float], ...],
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Robustly split any closed airfoil coordinate loop into upper and lower curves (LE -> TE)."""
    le_idx = min(range(len(coords)), key=lambda i: coords[i][0])
    n = len(coords)
    ordered = [coords[(le_idx + i) % n] for i in range(n)]
    te_idx = max(range(len(ordered)), key=lambda i: ordered[i][0])

    path1 = ordered[: te_idx + 1]
    path2 = [ordered[0], *reversed(ordered[te_idx:])]

    avg_z1 = sum(p[1] for p in path1) / max(len(path1), 1)
    avg_z2 = sum(p[1] for p in path2) / max(len(path2), 1)

    if avg_z1 >= avg_z2:
        return path1, path2
    return path2, path1


def interp_branch_z(branch: list[tuple[float, float]], x_t: float) -> float:
    """Interpolate Z coordinate along a monotonically ordered airfoil branch (LE -> TE)."""
    if not branch:
        return 0.0
    if x_t <= branch[0][0]:
        return branch[0][1]
    if x_t >= branch[-1][0]:
        return branch[-1][1]
    for j in range(len(branch) - 1):
        p0, p1 = branch[j], branch[j + 1]
        if (p0[0] <= x_t <= p1[0]) or (p1[0] <= x_t <= p0[0]):
            dx = p1[0] - p0[0]
            frac = (x_t - p0[0]) / dx if abs(dx) > 1e-9 else 0.0
            return p0[1] + frac * (p1[1] - p0[1])
    return branch[-1][1]


def sample_structured_airfoil_round(
    coords: tuple[tuple[float, float], ...],
    x_h: float = 1.0,
    is_flap: bool = False,
    n_upper: int = 28,
    n_lower: int = 28,
    n_wall: int = 7,
) -> tuple[tuple[tuple[float, float], ...], tuple[float, float]]:
    """Sample structured 64-point loop with global chord alignment and round circular hinge socket/nose."""
    upper_branch, lower_branch = split_airfoil_upper_lower(coords)

    z_u_h = interp_branch_z(upper_branch, x_h)
    z_l_h = interp_branch_z(lower_branch, x_h)
    z_h = (z_u_h + z_l_h) * 0.5
    r_h = max((z_u_h - z_l_h) * 0.5, 0.0) if x_h < 0.999 else 0.0

    global_x_upper = [0.5 * (1.0 + math.cos(math.pi * i / (n_upper - 1))) for i in range(n_upper)]
    global_x_lower = [0.5 * (1.0 - math.cos(math.pi * i / (n_lower - 1))) for i in range(n_lower)]

    if not is_flap:
        # Main Wing Section (64 pts):
        upper_pts = []
        for i in range(n_upper):
            x_val = global_x_upper[i]
            x_clamped = min(x_val, x_h)
            z_val = interp_branch_z(upper_branch, x_clamped)
            upper_pts.append((x_clamped, z_val))

        le_pt = (0.0, upper_branch[0][1])

        lower_pts = []
        for i in range(1, n_lower + 1):
            x_val = global_x_lower[i - 1] if i <= n_lower else global_x_lower[-1]
            x_clamped = min(x_val, x_h)
            z_val = interp_branch_z(lower_branch, x_clamped)
            lower_pts.append((x_clamped, z_val))

        socket_pts = []
        if x_h < 0.999 and r_h > 1e-4:
            for i in range(1, n_wall + 1):
                theta = -math.pi * 0.5 + (i / n_wall) * math.pi
                x_c = x_h - r_h * math.cos(theta)
                z_c = z_h + r_h * math.sin(theta)
                socket_pts.append((x_c, z_c))
        else:
            z_te_l = interp_branch_z(lower_branch, 1.0)
            z_te_u = interp_branch_z(upper_branch, 1.0)
            for i in range(1, n_wall + 1):
                frac = i / n_wall
                socket_pts.append((1.0, z_te_l + frac * (z_te_u - z_te_l)))

        return (*upper_pts, le_pt, *lower_pts, *socket_pts), (x_h, z_h)
    else:
        # Flap Section (64 pts):
        flap_upper = []
        for i in range(n_upper):
            x_val = 1.0 - (1.0 - x_h) * (i / (n_upper - 1))
            z_val = interp_branch_z(upper_branch, x_val)
            flap_upper.append((x_val, z_val))

        flap_nose = []
        r_nose = r_h * 0.97
        for i in range(8):
            theta = math.pi * 0.5 - (i / 7.0) * math.pi
            x_c = x_h - r_nose * math.cos(theta)
            z_c = z_h + r_nose * math.sin(theta)
            flap_nose.append((x_c, z_c))

        flap_lower = []
        for i in range(1, n_lower + 1):
            x_val = x_h + (1.0 - x_h) * (i / n_lower)
            z_val = interp_branch_z(lower_branch, x_val)
            flap_lower.append((x_val, z_val))

        return tuple(flap_upper + flap_nose + flap_lower), (x_h, z_h)


def rotate_section_around_axis(
    section: Section,
    axis_pt: Point3D,
    axis_dir: Point3D,
    angle_deg: float,
) -> Section:
    """Rotate all points of a 3D section around an arbitrary 3D hinge axis by angle_deg."""
    length = math.sqrt(axis_dir[0] ** 2 + axis_dir[1] ** 2 + axis_dir[2] ** 2)
    if length < 1e-6:
        return section
    kx, ky, kz = axis_dir[0] / length, axis_dir[1] / length, axis_dir[2] / length
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    one_minus_cos = 1.0 - cos_a

    ox, oy, oz = axis_pt
    new_points: list[Point3D] = []

    for px, py, pz in section.points:
        vx, vy, vz = px - ox, py - oy, pz - oz
        dot = kx * vx + ky * vy + kz * vz
        cx = ky * vz - kz * vy
        cy = kz * vx - kx * vz
        cz = kx * vy - ky * vx

        rx = vx * cos_a + cx * sin_a + kx * dot * one_minus_cos
        ry = vy * cos_a + cy * sin_a + ky * dot * one_minus_cos
        rz = vz * cos_a + cz * sin_a + kz * dot * one_minus_cos

        new_points.append((rx + ox, ry + oy, rz + oz))

    return Section(tuple(new_points))


__all__ = [
    "interp_branch_z",
    "mapping",
    "number",
    "rotate_section_around_axis",
    "sample_structured_airfoil_round",
    "split_airfoil_upper_lower",
]
