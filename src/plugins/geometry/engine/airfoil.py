"""Airfoil geometry generators, UIUC DAT parser, and authentic preset library.

A canonical airfoil spec is either a NACA 4- or 5-digit code string (``"2412"``,
``"23012"``) or a ``{"type": "coordinates", "name": str, "points": [[x, z], ...]}``
mapping.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

AIRFOIL_SAMPLES = 64
AIRFOILS_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "airfoils"

_NACA_CODE = re.compile(r"[0-9]{4}|[0-9]{5}")
_NACA4_CODE = re.compile(r"[0-9]{4}")
_NACA5_CODE = re.compile(r"[0-9]{5}")

# Mean-line constants (m, k1) of the NACA 5-digit series keyed by the camber-position digit.
_NACA5_MEAN_LINES: dict[int, tuple[float, float]] = {
    1: (0.0580, 361.4),
    2: (0.1260, 51.64),
    3: (0.2025, 15.793),
    4: (0.2900, 6.520),
    5: (0.3910, 3.191),
}


def naca4(code: str, samples: int = AIRFOIL_SAMPLES) -> tuple[tuple[float, float], ...]:
    """Generate normalized (x, z) coordinates for NACA 4-digit airfoil."""
    if _NACA4_CODE.fullmatch(code) is None:
        raise ValueError(f"NACA 4-digit code must be exactly four digits, got {code!r}")
    camber = int(code[0]) / 100.0
    camber_position = int(code[1]) / 10.0
    thickness = int(code[2:4]) / 100.0

    upper: list[tuple[float, float]] = []
    lower: list[tuple[float, float]] = []
    for index in range(samples + 1):
        x = 0.5 * (1.0 - math.cos(math.pi * index / samples))
        yt = (
            5.0
            * thickness
            * (
                0.2969 * math.sqrt(max(x, 1e-9))
                - 0.1260 * x
                - 0.3516 * x**2
                + 0.2843 * x**3
                - 0.1015 * x**4
            )
        )
        yc = 0.0
        slope = 0.0
        if camber_position > 0.0:
            if x < camber_position:
                yc = camber / camber_position**2 * (2 * camber_position * x - x**2)
                slope = 2 * camber / camber_position**2 * (camber_position - x)
            else:
                remaining = 1.0 - camber_position
                yc = (
                    camber
                    / remaining**2
                    * (1 - 2 * camber_position + 2 * camber_position * x - x**2)
                )
                slope = 2 * camber / remaining**2 * (camber_position - x)
        angle = math.atan(slope)
        upper.append((x - yt * math.sin(angle), yc + yt * math.cos(angle)))
        if 0 < index < samples:
            lower.append((x + yt * math.sin(angle), yc - yt * math.cos(angle)))
    return tuple(upper + list(reversed(lower)))


def naca5(code: str, samples: int = AIRFOIL_SAMPLES) -> tuple[tuple[float, float], ...]:
    """Generate normalized coordinates for NACA 5-digit airfoil (e.g. 23012, 24012)."""
    m, k1 = _naca5_mean_line(code)
    thickness = int(code[3:5]) / 100.0

    upper: list[tuple[float, float]] = []
    lower: list[tuple[float, float]] = []
    for i in range(samples + 1):
        x = 0.5 * (1.0 - math.cos(math.pi * i / samples))
        yt = (
            5.0
            * thickness
            * (
                0.2969 * math.sqrt(max(x, 1e-9))
                - 0.1260 * x
                - 0.3516 * x**2
                + 0.2843 * x**3
                - 0.1015 * x**4
            )
        )
        if x < m:
            yc = (k1 / 6.0) * (x**3 - 3 * m * x**2 + m**2 * (3 - m) * x)
            dycdx = (k1 / 6.0) * (3 * x**2 - 6 * m * x + m**2 * (3 - m))
        else:
            yc = (k1 * m**3 / 6.0) * (1 - x)
            dycdx = -(k1 * m**3 / 6.0)
        theta = math.atan(dycdx)
        upper.append((x - yt * math.sin(theta), yc + yt * math.cos(theta)))
        if 0 < i < samples:
            lower.append((x + yt * math.sin(theta), yc - yt * math.cos(theta)))
    return tuple(upper + list(reversed(lower)))


def _naca5_mean_line(code: str) -> tuple[float, float]:
    if _NACA5_CODE.fullmatch(code) is None:
        raise ValueError(f"NACA 5-digit code must be exactly five digits, got {code!r}")
    mean_line = _NACA5_MEAN_LINES.get(int(code[1]))
    if mean_line is None:
        raise ValueError(
            f"NACA 5-digit code {code!r} has camber-position digit {code[1]}; expected 1-5"
        )
    return mean_line


def biconvex(
    thickness: float = 0.10, samples: int = AIRFOIL_SAMPLES
) -> tuple[tuple[float, float], ...]:
    """Generate symmetric parabolic biconvex airfoil."""
    upper: list[tuple[float, float]] = []
    lower: list[tuple[float, float]] = []
    for i in range(samples + 1):
        x = 0.5 * (1.0 - math.cos(math.pi * i / samples))
        yt = 2.0 * thickness * x * (1.0 - x)
        upper.append((x, yt))
        if 0 < i < samples:
            lower.append((x, -yt))
    return tuple(upper + list(reversed(lower)))


def parse_airfoil_dat(content: str) -> tuple[str, tuple[tuple[float, float], ...]]:
    """Parse standard Selig/UIUC or Lednicer .dat coordinate format and normalize to [0, 1]."""
    raw_lines = [line.strip() for line in content.splitlines()]
    non_empty = [line for line in raw_lines if line]
    if not non_empty:
        raise ValueError("Airfoil file is empty")

    name = non_empty[0].strip()

    n_upper, n_lower = _lednicer_counts(non_empty)
    is_lednicer = n_upper > 0 or n_lower > 0

    if is_lednicer:
        # Lednicer format: upper surface (LE -> TE), then lower surface (LE -> TE)
        data_points = _coordinate_lines(non_empty[2:])
        upper = data_points[:n_upper]  # LE -> TE
        lower = data_points[n_upper : n_upper + n_lower]  # LE -> TE
    else:
        # Selig format: single continuous loop TE -> LE -> TE
        loop = _coordinate_lines(non_empty[1:])
        if len(loop) < 3:
            raise ValueError(f"Airfoil {name!r} has fewer than 3 coordinate points")
        le_idx = min(range(len(loop)), key=lambda i: loop[i][0])
        upper = list(reversed(loop[: le_idx + 1]))  # LE -> TE
        lower = loop[le_idx:]  # LE -> TE

    if not upper or not lower:
        raise ValueError(f"Airfoil {name!r} is missing upper or lower surface coordinates")

    # Normalize to [0, 1] range preserving exact leading edge (0, z_LE)
    all_pts = upper + lower
    min_x = min(p[0] for p in all_pts)
    max_x = max(p[0] for p in all_pts)
    chord = max(max_x - min_x, 1e-6)

    upper_norm = [((p[0] - min_x) / chord, p[1] / chord) for p in upper]
    lower_norm = [((p[0] - min_x) / chord, p[1] / chord) for p in lower]

    if upper_norm[0][0] > 0.0:
        upper_norm.insert(0, (0.0, upper_norm[0][1]))
    if lower_norm[0][0] > 0.0:
        lower_norm.insert(0, (0.0, lower_norm[0][1]))

    z_le = (upper_norm[0][1] + lower_norm[0][1]) * 0.5
    upper_norm[0] = (0.0, z_le)
    lower_norm[0] = (0.0, z_le)

    loop_clean = tuple(list(reversed(upper_norm)) + lower_norm[1:])
    return name, loop_clean


def _lednicer_counts(lines: list[str]) -> tuple[int, int]:
    if len(lines) <= 1:
        return 0, 0
    parts = lines[1].replace(",", " ").split()
    if len(parts) != 2:
        return 0, 0
    try:
        upper, lower = float(parts[0]), float(parts[1])
    except ValueError:
        return 0, 0
    looks_like_counts = (upper > 5 or lower > 5) and (upper.is_integer() or lower.is_integer())
    return (int(upper), int(lower)) if looks_like_counts else (0, 0)


def _coordinate_lines(lines: list[str]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for line in lines:
        parts = line.replace(",", " ").split()
        if len(parts) < 2:
            continue
        try:
            points.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue
    return points


def compute_airfoil_metrics(
    points: tuple[tuple[float, float], ...] | list[tuple[float, float]],
) -> dict[str, float]:
    """Compute geometric properties: max thickness, max camber, TE gap."""
    if len(points) < 4:
        return {
            "max_thickness": 0.12,
            "max_camber": 0.0,
            "te_gap": 0.0,
            "thickness_x": 0.3,
            "camber_x": 0.4,
        }

    min_x_idx = min(range(len(points)), key=lambda i: points[i][0])
    max_x_idx = max(range(len(points)), key=lambda i: points[i][0])

    if min_x_idx < max_x_idx:
        seg1 = points[min_x_idx : max_x_idx + 1]
        seg2 = list(points[max_x_idx:]) + list(points[: min_x_idx + 1])
    else:
        seg1 = points[max_x_idx : min_x_idx + 1]
        seg2 = list(points[min_x_idx:]) + list(points[: max_x_idx + 1])

    avg_z1 = sum(p[1] for p in seg1) / max(len(seg1), 1)
    avg_z2 = sum(p[1] for p in seg2) / max(len(seg2), 1)
    if avg_z1 >= avg_z2:
        upper, lower = seg1, seg2
    else:
        upper, lower = seg2, seg1

    max_thickness = 0.0
    thickness_x = 0.3
    max_camber = 0.0
    camber_x = 0.4

    for s in range(1, 50):
        x_target = s / 50.0
        u_z = _interpolate_z_at_x(upper, x_target)
        l_z = _interpolate_z_at_x(lower, x_target)
        t = u_z - l_z
        c = (u_z + l_z) / 2.0
        if t > max_thickness:
            max_thickness = t
            thickness_x = x_target
        if abs(c) > abs(max_camber):
            max_camber = c
            camber_x = x_target

    te_gap = math.dist(points[0], points[-1])
    return {
        "max_thickness": max_thickness,
        "thickness_x": thickness_x,
        "max_camber": max_camber,
        "camber_x": camber_x,
        "te_gap": te_gap,
    }


def apply_airfoil_shaping(
    coords: tuple[tuple[float, float], ...],
    te_thickness: float = 0.0,
    thickness_scale: float = 1.0,
    camber_scale: float = 1.0,
) -> tuple[tuple[float, float], ...]:
    """Apply trailing-edge blunting, thickness scaling, and camber scaling to normalized airfoil coords.

    Args:
        coords: Normalized (x, z) closed-loop airfoil coordinates.
        te_thickness: Target TE gap as a fraction of chord (e.g. 0.004 = 0.4%). 0 = no change.
        thickness_scale: Multiplier for half-thickness (1.0 = no change, 1.2 = 20% thicker).
        camber_scale: Multiplier for camber line offset (1.0 = no change).
    Returns:
        Modified normalized coordinate tuple.
    """
    if not coords:
        return coords
    if (
        abs(te_thickness) < 1e-6
        and abs(thickness_scale - 1.0) < 1e-6
        and abs(camber_scale - 1.0) < 1e-6
    ):
        return coords

    # Split into upper / lower branches from LE to TE
    le_idx = min(range(len(coords)), key=lambda i: coords[i][0])
    n = len(coords)
    # Build upper (LE->TE going up) and lower (LE->TE going down)
    ordered = [coords[(le_idx + i) % n] for i in range(n)]
    te_idx = max(range(len(ordered)), key=lambda i: ordered[i][0])
    upper = ordered[: te_idx + 1]  # LE -> TE (upper side)
    lower = [ordered[0], *reversed(ordered[te_idx:])]  # LE -> TE (lower side)

    avg_u = sum(p[1] for p in upper) / max(len(upper), 1)
    avg_l = sum(p[1] for p in lower) / max(len(lower), 1)
    if avg_u < avg_l:
        upper, lower = lower, upper

    # Sample camberline and half-thickness on a common x-grid
    x_grid = sorted({p[0] for p in upper} | {p[0] for p in lower})

    result_upper: list[tuple[float, float]] = []
    result_lower: list[tuple[float, float]] = []

    for x in x_grid:
        zu = _interpolate_z_at_x(upper, x)
        zl = _interpolate_z_at_x(lower, x)
        camber = (zu + zl) * 0.5
        half_t = (zu - zl) * 0.5

        # Apply TE blunting: linearly increase TE gap from LE to TE
        te_add = te_thickness * 0.5 * x
        new_half_t = max(half_t * thickness_scale, 0.0) + te_add
        new_camber = camber * camber_scale

        result_upper.append((x, new_camber + new_half_t))
        result_lower.append((x, new_camber - new_half_t))

    # Reconstruct closed loop: upper reversed (TE->LE) + lower (LE->TE), drop duplicates
    loop = list(reversed(result_upper)) + result_lower[1:]
    return tuple(loop)


def _interpolate_z_at_x(
    points: tuple[tuple[float, float], ...] | list[tuple[float, float]], x_target: float
) -> float:
    if not points:
        return 0.0
    best_dist = 1e9
    best_z = 0.0
    for i in range(len(points) - 1):
        x0, z0 = points[i]
        x1, z1 = points[i + 1]
        if (x0 <= x_target <= x1) or (x1 <= x_target <= x0):
            dx = x1 - x0
            if abs(dx) > 1e-7:
                frac = (x_target - x0) / dx
                return z0 + frac * (z1 - z0)
        d = abs(x0 - x_target)
        if d < best_dist:
            best_dist = d
            best_z = z0
    return best_z


def _load_uiuc_file(filename: str) -> tuple[tuple[float, float], ...]:
    _, pts = parse_airfoil_dat((AIRFOILS_DATA_DIR / filename).read_text(encoding="utf-8"))
    return pts


# =============================================================================
# BUILT-IN AIRFOIL PRESET LIBRARY (UIUC Verified)
# =============================================================================

PRESET_AIRFOILS: dict[str, dict[str, Any]] = {
    # General Aviation & Trainer
    "NACA 2412": {
        "category": "General Aviation",
        "description": "Standard cambered wing for trainer and light aircraft (t/c = 12%)",
        "type": "naca",
        "code": "2412",
        "generator": lambda: naca4("2412"),
    },
    "NACA 2414": {
        "category": "General Aviation",
        "description": "Thick root wing for structural depth (t/c = 14%)",
        "type": "naca",
        "code": "2414",
        "generator": lambda: naca4("2414"),
    },
    "NACA 4412": {
        "category": "General Aviation",
        "description": "High camber general aviation airfoil (t/c = 12%, max camber 4%)",
        "type": "naca",
        "code": "4412",
        "generator": lambda: naca4("4412"),
    },
    "NACA 4415": {
        "category": "General Aviation",
        "description": "Thick high-lift general aviation airfoil (t/c = 15%)",
        "type": "naca",
        "code": "4415",
        "generator": lambda: naca4("4415"),
    },
    "Clark-Y": {
        "category": "General Aviation",
        "description": "Classic flat-bottom airfoil with benign stall and high lift (UIUC)",
        "type": "file",
        "file": "clarky.dat",
        "generator": lambda: _load_uiuc_file("clarky.dat"),
    },
    # High Lift & UAV
    "Selig S1223": {
        "category": "High Lift UAV",
        "description": "Extreme high-lift low Reynolds airfoil for heavy-lift UAVs (Cl_max > 2.0, UIUC)",
        "type": "file",
        "file": "s1223.dat",
        "generator": lambda: _load_uiuc_file("s1223.dat"),
    },
    "Selig S8036": {
        "category": "High Lift UAV",
        "description": "Low Reynolds number high-lift airfoil for UAV applications (16% thickness, UIUC)",
        "type": "file",
        "file": "s8036.dat",
        "generator": lambda: _load_uiuc_file("s8036.dat"),
    },
    "Selig S9027": {
        "category": "High Lift UAV",
        "description": "Low Reynolds number sailplane and glider wing airfoil (UIUC)",
        "type": "file",
        "file": "s9027.dat",
        "generator": lambda: _load_uiuc_file("s9027.dat"),
    },
    "Eppler E423": {
        "category": "High Lift UAV",
        "description": "High maximum lift coefficient airfoil for heavy-lift cargo RC/UAV (UIUC)",
        "type": "file",
        "file": "e423.dat",
        "generator": lambda: _load_uiuc_file("e423.dat"),
    },
    "Wortmann FX 63-137": {
        "category": "High Lift UAV",
        "description": "High lift-to-drag ratio long-endurance sailplane and UAV wing (UIUC)",
        "type": "file",
        "file": "fx63137.dat",
        "generator": lambda: _load_uiuc_file("fx63137.dat"),
    },
    "Drela AG24": {
        "category": "High Lift UAV",
        "description": "Mark Drela low Re high L/D thermal soaring and glider airfoil (UIUC)",
        "type": "file",
        "file": "ag24.dat",
        "generator": lambda: _load_uiuc_file("ag24.dat"),
    },
    # Tailless & Flying Wing (Reflexed)
    "MH 45": {
        "category": "Tailless & Flying Wing",
        "description": "Reflexed trailing edge airfoil for stable tailless flying wings (Cm0 > 0, UIUC)",
        "type": "file",
        "file": "mh45.dat",
        "generator": lambda: _load_uiuc_file("mh45.dat"),
    },
    "MH 60": {
        "category": "Tailless & Flying Wing",
        "description": "High speed reflexed airfoil for tailless delta and flying wing UAVs (UIUC)",
        "type": "file",
        "file": "mh60.dat",
        "generator": lambda: _load_uiuc_file("mh60.dat"),
    },
    "NACA 23012": {
        "category": "Tailless & Flying Wing",
        "description": "Very low pitching moment (Cm0 ≈ -0.01) high speed transport airfoil",
        "type": "naca",
        "code": "23012",
        "generator": lambda: naca5("23012"),
    },
    # Symmetric & Empennage (Tail & Aerobatic)
    "NACA 0012": {
        "category": "Symmetric & Tail",
        "description": "Standard symmetric airfoil for vertical/horizontal stabilizers",
        "type": "naca",
        "code": "0012",
        "generator": lambda: naca4("0012"),
    },
    "NACA 0009": {
        "category": "Symmetric & Tail",
        "description": "Thin symmetric airfoil for low drag empennage fins",
        "type": "naca",
        "code": "0009",
        "generator": lambda: naca4("0009"),
    },
    "NACA 0006": {
        "category": "Symmetric & Tail",
        "description": "Very thin symmetric airfoil for high speed control surfaces",
        "type": "naca",
        "code": "0006",
        "generator": lambda: naca4("0006"),
    },
    "NACA 0015": {
        "category": "Symmetric & Tail",
        "description": "Thick symmetric airfoil for aerobatic aircraft and thick fins",
        "type": "naca",
        "code": "0015",
        "generator": lambda: naca4("0015"),
    },
}


def sample_airfoil_points(spec: object) -> tuple[tuple[float, float], ...]:
    """Sample normalized (x, z) coordinates for a canonical airfoil spec."""
    if isinstance(spec, str):
        code = _naca_code(spec)
        return naca5(code) if len(code) == 5 else naca4(code)
    _, points = _coordinate_spec(spec)
    return _normalized_coordinates(points)


def airfoil_label(spec: object) -> str:
    """Return the display label of a canonical airfoil spec."""
    if isinstance(spec, str):
        code = _naca_code(spec)
        for name, preset in PRESET_AIRFOILS.items():
            if preset["type"] == "naca" and preset["code"] == code:
                return name
        return f"NACA {code}"
    name, _ = _coordinate_spec(spec)
    return name


def preset_airfoil_spec(name: str) -> str | dict[str, Any]:
    """Return the canonical airfoil spec of a built-in preset."""
    preset = PRESET_AIRFOILS[name]
    if preset["type"] == "naca":
        return str(preset["code"])
    return {
        "type": "coordinates",
        "name": name,
        "points": [list(point) for point in preset["generator"]()],
    }


def _naca_code(spec: str) -> str:
    if _NACA_CODE.fullmatch(spec) is None:
        raise ValueError(
            f"Airfoil spec {spec!r} is not a NACA 4- or 5-digit code such as '2412' or '23012'"
        )
    if len(spec) == 5:
        _naca5_mean_line(spec)
    return spec


def _coordinate_spec(spec: object) -> tuple[str, list[tuple[float, float]]]:
    if not isinstance(spec, dict) or spec.get("type") != "coordinates":
        raise _unsupported_spec(spec)
    name = spec.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("Coordinates airfoil spec requires a non-empty 'name'")
    raw_points = spec.get("points")
    if not isinstance(raw_points, list) or len(raw_points) < 3:
        raise ValueError(f"Coordinates airfoil {name!r} requires at least 3 [x, z] points")
    points: list[tuple[float, float]] = []
    for point in raw_points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(
                f"Coordinates airfoil {name!r} has a point that is not [x, z]: {point!r}"
            )
        points.append((float(point[0]), float(point[1])))
    return name, points


def _unsupported_spec(spec: object) -> ValueError:
    if spec is None:
        subject = "Missing airfoil spec"
    elif isinstance(spec, dict):
        subject = f"Unsupported airfoil spec mapping with type {spec.get('type')!r}"
    else:
        subject = f"Unsupported airfoil spec of type {type(spec).__name__}"
    return ValueError(
        f"{subject}: expected a NACA 4- or 5-digit code string such as '2412' or a "
        "{'type': 'coordinates', 'name': str, 'points': [[x, z], ...]} mapping"
    )


def _normalized_coordinates(
    points: list[tuple[float, float]],
) -> tuple[tuple[float, float], ...]:
    min_x = min(point[0] for point in points)
    chord = max(max(point[0] for point in points) - min_x, 1e-6)
    normalized = [((x - min_x) / chord, z / chord) for x, z in points]
    leading_edge = min(range(len(normalized)), key=lambda index: normalized[index][0])
    normalized[leading_edge] = (0.0, normalized[leading_edge][1])
    return tuple(normalized)
