"""Airfoil geometry generators, UIUC DAT parser, and authentic preset library.

A canonical airfoil spec is either a NACA 4- or 5-digit code string (``"2412"``,
``"23012"``) or a ``{"type": "coordinates", "name": str, "points": [[x, z], ...]}``
mapping.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

AIRFOIL_SAMPLES = 64
AIRFOILS_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "airfoils"

# Smallest closed coordinate loop accepted as an airfoil: trailing edge, one surface point,
# leading edge.
_MIN_AIRFOIL_POINTS = 3

_NACA_CODE = re.compile(r"[0-9]{4}|[0-9]{5}")
_NACA4_CODE = re.compile(r"[0-9]{4}")
_NACA5_CODE = re.compile(r"[0-9]{5}")

# The NACA 5-digit mean-line constants are tabulated for this design lift coefficient.
_NACA5_TABULATED_DESIGN_CL = 0.3
# Standard mean-line constants (r, k1) keyed by the camber-position digit.
_NACA5_STANDARD_MEAN_LINES: dict[int, tuple[float, float]] = {
    1: (0.0580, 361.4),
    2: (0.1260, 51.64),
    3: (0.2025, 15.957),
    4: (0.2900, 6.643),
    5: (0.3910, 3.230),
}
# Reflexed mean-line constants (r, k1, k2/k1) keyed by the camber-position digit.
_NACA5_REFLEXED_MEAN_LINES: dict[int, tuple[float, float, float]] = {
    2: (0.1300, 51.99, 0.000764),
    3: (0.2170, 15.793, 0.00677),
    4: (0.3180, 6.520, 0.0303),
    5: (0.4410, 3.191, 0.1355),
}

# A mean line maps a chordwise station x to its camber ordinate and slope (yc, dyc/dx).
_MeanLine = Callable[[float], tuple[float, float]]


def naca4(code: str, samples: int = AIRFOIL_SAMPLES) -> tuple[tuple[float, float], ...]:
    """Generate normalized (x, z) coordinates for NACA 4-digit airfoil."""
    mean_line = _naca4_mean_line(code)
    return _naca_airfoil(mean_line, int(code[2:4]) / 100.0, samples)


def naca5(code: str, samples: int = AIRFOIL_SAMPLES) -> tuple[tuple[float, float], ...]:
    """Generate normalized coordinates for NACA 5-digit airfoil (e.g. 23012, 23112, 43012)."""
    mean_line = _naca5_mean_line(code)
    return _naca_airfoil(mean_line, int(code[3:5]) / 100.0, samples)


def _naca_airfoil(
    mean_line: _MeanLine, thickness: float, samples: int
) -> tuple[tuple[float, float], ...]:
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
        yc, slope = mean_line(x)
        angle = math.atan(slope)
        upper.append((x - yt * math.sin(angle), yc + yt * math.cos(angle)))
        if 0 < index < samples:
            lower.append((x + yt * math.sin(angle), yc - yt * math.cos(angle)))
    return tuple(upper + list(reversed(lower)))


def _naca4_mean_line(code: str) -> _MeanLine:
    if _NACA4_CODE.fullmatch(code) is None:
        raise ValueError(f"NACA 4-digit code must be exactly four digits, got {code!r}")
    camber = int(code[0]) / 100.0
    camber_position = int(code[1]) / 10.0
    if camber > 0.0 and camber_position == 0.0:
        raise ValueError(
            f"NACA 4-digit code {code!r} has {code[0]}% camber but camber-position digit 0; "
            "a cambered section needs a camber position of 1-9, a symmetric one uses '00'"
        )
    if camber == 0.0:
        return _naca_symmetric_camber
    return partial(_naca4_camber, camber=camber, position=camber_position)


def _naca_symmetric_camber(_x: float) -> tuple[float, float]:
    return 0.0, 0.0


def _naca4_camber(x: float, *, camber: float, position: float) -> tuple[float, float]:
    if x < position:
        return (
            camber / position**2 * (2 * position * x - x**2),
            2 * camber / position**2 * (position - x),
        )
    remaining = 1.0 - position
    return (
        camber / remaining**2 * (1 - 2 * position + 2 * position * x - x**2),
        2 * camber / remaining**2 * (position - x),
    )


def _naca5_mean_line(code: str) -> _MeanLine:
    if _NACA5_CODE.fullmatch(code) is None:
        raise ValueError(f"NACA 5-digit code must be exactly five digits, got {code!r}")
    design_cl = 0.15 * int(code[0])
    scale = design_cl / _NACA5_TABULATED_DESIGN_CL
    position_digit = int(code[1])
    reflex_digit = int(code[2])
    if reflex_digit == 0:
        standard = _NACA5_STANDARD_MEAN_LINES.get(position_digit)
        if standard is None:
            raise ValueError(
                f"NACA 5-digit code {code!r} has camber-position digit {code[1]}; expected 1-5"
            )
        r, k1 = standard
        return partial(_naca5_standard_camber, r=r, k1=k1 * scale)
    if reflex_digit == 1:
        reflexed = _NACA5_REFLEXED_MEAN_LINES.get(position_digit)
        if reflexed is None:
            raise ValueError(
                f"NACA 5-digit code {code!r} has camber-position digit {code[1]}; "
                "reflexed mean lines expect 2-5"
            )
        r, k1, k2_over_k1 = reflexed
        return partial(_naca5_reflexed_camber, r=r, k1=k1 * scale, k2_over_k1=k2_over_k1)
    raise ValueError(
        f"NACA 5-digit code {code!r} has reflex digit {code[2]}; "
        "expected 0 (standard) or 1 (reflexed)"
    )


def _naca5_standard_camber(x: float, *, r: float, k1: float) -> tuple[float, float]:
    if x < r:
        return (
            (k1 / 6.0) * (x**3 - 3 * r * x**2 + r**2 * (3 - r) * x),
            (k1 / 6.0) * (3 * x**2 - 6 * r * x + r**2 * (3 - r)),
        )
    return (k1 * r**3 / 6.0) * (1 - x), -(k1 * r**3 / 6.0)


def _naca5_reflexed_camber(
    x: float, *, r: float, k1: float, k2_over_k1: float
) -> tuple[float, float]:
    linear = k2_over_k1 * (1 - r) ** 3 + r**3
    cubic = 1.0 if x < r else k2_over_k1
    return (
        (k1 / 6.0) * (cubic * (x - r) ** 3 - linear * x + r**3),
        (k1 / 6.0) * (3 * cubic * (x - r) ** 2 - linear),
    )


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
        if len(loop) < _MIN_AIRFOIL_POINTS:
            raise ValueError(
                f"Airfoil {name!r} has fewer than {_MIN_AIRFOIL_POINTS} coordinate points"
            )
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


@dataclass(frozen=True)
class AirfoilMetrics:
    """Geometric properties of a normalized airfoil, as fractions of the chord."""

    max_thickness: float
    thickness_x: float
    max_camber: float
    camber_x: float | None
    """Chordwise station of the maximum camber; None for a symmetric airfoil."""
    te_gap: float


def compute_airfoil_metrics(
    points: tuple[tuple[float, float], ...] | list[tuple[float, float]],
) -> AirfoilMetrics:
    """Compute max thickness and camber with their stations, and the TE gap."""
    if len(points) < _MIN_AIRFOIL_POINTS:
        raise ValueError(
            f"Airfoil metrics need at least {_MIN_AIRFOIL_POINTS} coordinate points, "
            f"got {len(points)}"
        )

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

    stations = [s / 50.0 for s in range(1, 50)]
    thickness: list[float] = []
    camber: list[float] = []
    for x_target in stations:
        u_z = _interpolate_z_at_x(upper, x_target)
        l_z = _interpolate_z_at_x(lower, x_target)
        thickness.append(u_z - l_z)
        camber.append((u_z + l_z) / 2.0)

    thickest = max(range(len(stations)), key=lambda i: thickness[i])
    most_cambered = max(range(len(stations)), key=lambda i: abs(camber[i]))
    max_camber = camber[most_cambered]
    return AirfoilMetrics(
        max_thickness=thickness[thickest],
        thickness_x=stations[thickest],
        max_camber=max_camber,
        camber_x=stations[most_cambered] if abs(max_camber) > 1e-9 else None,
        te_gap=math.dist(points[0], points[-1]),
    )


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
    else:
        _naca4_mean_line(spec)
    return spec


def _coordinate_spec(spec: object) -> tuple[str, list[tuple[float, float]]]:
    if not isinstance(spec, dict) or spec.get("type") != "coordinates":
        raise _unsupported_spec(spec)
    name = spec.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("Coordinates airfoil spec requires a non-empty 'name'")
    raw_points = spec.get("points")
    if not isinstance(raw_points, list) or len(raw_points) < _MIN_AIRFOIL_POINTS:
        raise ValueError(
            f"Coordinates airfoil {name!r} requires at least {_MIN_AIRFOIL_POINTS} [x, z] points"
        )
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
