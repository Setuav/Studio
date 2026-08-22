"""Airfoil geometry generators, UIUC DAT parser, and authentic preset library."""

from __future__ import annotations

import logging
import math
from pathlib import Path
import re
from typing import Any

logger = logging.getLogger(__name__)


AIRFOIL_SAMPLES = 64
AIRFOILS_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "airfoils"


def naca4(code: str, samples: int = AIRFOIL_SAMPLES) -> tuple[tuple[float, float], ...]:
    """Generate normalized (x, z) coordinates for NACA 4-digit airfoil."""
    clean = re.sub(r"[^\d]", "", code)
    if len(clean) < 4:
        clean = "0012"
    camber = int(clean[0]) / 100.0
    camber_position = int(clean[1]) / 10.0
    thickness = int(clean[2:4]) / 100.0

    upper: list[tuple[float, float]] = []
    lower: list[tuple[float, float]] = []
    for index in range(samples + 1):
        x = 0.5 * (1.0 - math.cos(math.pi * index / samples))
        yt = 5.0 * thickness * (
            0.2969 * math.sqrt(max(x, 1e-9))
            - 0.1260 * x
            - 0.3516 * x**2
            + 0.2843 * x**3
            - 0.1015 * x**4
        )
        yc = 0.0
        slope = 0.0
        if camber_position > 0.0:
            if x < camber_position:
                yc = camber / camber_position**2 * (2 * camber_position * x - x**2)
                slope = 2 * camber / camber_position**2 * (camber_position - x)
            else:
                remaining = 1.0 - camber_position
                yc = camber / remaining**2 * (
                    1 - 2 * camber_position + 2 * camber_position * x - x**2
                )
                slope = 2 * camber / remaining**2 * (camber_position - x)
        angle = math.atan(slope)
        upper.append((x - yt * math.sin(angle), yc + yt * math.cos(angle)))
        if 0 < index < samples:
            lower.append((x + yt * math.sin(angle), yc - yt * math.cos(angle)))
    return tuple(upper + list(reversed(lower)))


def naca5(code: str, samples: int = AIRFOIL_SAMPLES) -> tuple[tuple[float, float], ...]:
    """Generate normalized coordinates for NACA 5-digit airfoil (e.g. 23012, 24012)."""
    clean = re.sub(r"[^\d]", "", code)
    if len(clean) < 5:
        return naca4("0012", samples)
    L = int(clean[0])
    P = int(clean[1])
    thickness = int(clean[3:5]) / 100.0
    p = P * 0.05

    table = {
        0.05: (0.0580, 361.4),
        0.10: (0.1260, 51.64),
        0.15: (0.2025, 15.793),
        0.20: (0.2900, 6.520),
        0.25: (0.3910, 3.191),
    }
    m, k1 = table.get(round(p, 2), (0.2025, 15.793))

    upper: list[tuple[float, float]] = []
    lower: list[tuple[float, float]] = []
    for i in range(samples + 1):
        x = 0.5 * (1.0 - math.cos(math.pi * i / samples))
        yt = 5.0 * thickness * (
            0.2969 * math.sqrt(max(x, 1e-9))
            - 0.1260 * x
            - 0.3516 * x**2
            + 0.2843 * x**3
            - 0.1015 * x**4
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


def biconvex(thickness: float = 0.10, samples: int = AIRFOIL_SAMPLES) -> tuple[tuple[float, float], ...]:
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


def parse_airfoil_dat(content: str, samples: int = AIRFOIL_SAMPLES * 2) -> tuple[str, tuple[tuple[float, float], ...]]:
    """Parse standard Selig/UIUC or Lednicer .dat coordinate format and normalize to [0, 1]."""
    raw_lines = [l.strip() for l in content.splitlines()]
    non_empty = [l for l in raw_lines if l]
    if not non_empty:
        return "Custom", naca4("0012", samples // 2)

    name = non_empty[0].strip()

    # Check for Lednicer format in line 2 (e.g. "61.0  61.0" or "49.0  49.0")
    is_lednicer = False
    n_upper = 0
    n_lower = 0
    if len(non_empty) > 1:
        second_line = non_empty[1].replace(",", " ").split()
        if len(second_line) == 2:
            try:
                val1 = float(second_line[0])
                val2 = float(second_line[1])
                if (val1 > 5 or val2 > 5) and (val1.is_integer() or val2.is_integer()):
                    is_lednicer = True
                    n_upper = int(val1)
                    n_lower = int(val2)
            except ValueError:
                pass

    if is_lednicer:
        # Lednicer format: upper surface (LE -> TE), then lower surface (LE -> TE)
        data_points: list[tuple[float, float]] = []
        for line in non_empty[2:]:
            parts = line.replace(",", " ").split()
            if len(parts) >= 2:
                try:
                    data_points.append((float(parts[0]), float(parts[1])))
                except ValueError:
                    continue

        upper = data_points[:n_upper]  # LE -> TE
        lower = data_points[n_upper : n_upper + n_lower]  # LE -> TE
    else:
        # Selig format: single continuous loop TE -> LE -> TE
        loop = []
        for line in non_empty[1:]:
            parts = line.replace(",", " ").split()
            if len(parts) >= 2:
                try:
                    loop.append((float(parts[0]), float(parts[1])))
                except ValueError:
                    continue
        if len(loop) < 3:
            return name, naca4("0012", samples // 2)
        le_idx = min(range(len(loop)), key=lambda i: loop[i][0])
        upper = list(reversed(loop[:le_idx + 1]))  # LE -> TE
        lower = loop[le_idx:]  # LE -> TE

    if not upper or not lower:
        return name, naca4("0012", samples // 2)

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


def compute_airfoil_metrics(points: tuple[tuple[float, float], ...] | list[tuple[float, float]]) -> dict[str, float]:
    """Compute geometric properties: max thickness, max camber, TE gap."""
    if len(points) < 4:
        return {"max_thickness": 0.12, "max_camber": 0.0, "te_gap": 0.0, "thickness_x": 0.3, "camber_x": 0.4}

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
    if abs(te_thickness) < 1e-6 and abs(thickness_scale - 1.0) < 1e-6 and abs(camber_scale - 1.0) < 1e-6:
        return coords

    # Split into upper / lower branches from LE to TE
    le_idx = min(range(len(coords)), key=lambda i: coords[i][0])
    n = len(coords)
    # Build upper (LE->TE going up) and lower (LE->TE going down)
    ordered = [coords[(le_idx + i) % n] for i in range(n)]
    te_idx = max(range(len(ordered)), key=lambda i: ordered[i][0])
    upper = ordered[:te_idx + 1]          # LE -> TE (upper side)
    lower = [ordered[0]] + list(reversed(ordered[te_idx:]))  # LE -> TE (lower side)

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


def _interpolate_z_at_x(points: tuple[tuple[float, float], ...] | list[tuple[float, float]], x_target: float) -> float:
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
    path = AIRFOILS_DATA_DIR / filename
    if path.is_file():
        _, pts = parse_airfoil_dat(path.read_text(encoding="utf-8"))
        return pts
    return naca4("0012")


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


def sample_airfoil_points(value: object) -> tuple[tuple[float, float], ...]:
    """Sample coordinates for any airfoil representation (string, code, dict, file)."""
    if isinstance(value, dict):
        val_type = value.get("type")
        if val_type == "coordinates":
            points = value.get("points")
            if isinstance(points, list):
                parsed = [
                    (float(p[0]), float(p[1]))
                    for p in points
                    if isinstance(p, (list, tuple)) and len(p) >= 2
                ]
                if len(parsed) >= 3:
                    min_x = min(p[0] for p in parsed)
                    max_x = max(p[0] for p in parsed)
                    chord = max(max_x - min_x, 1e-6)
                    norm = [((p[0] - min_x) / chord, p[1] / chord) for p in parsed]
                    le_idx = min(range(len(norm)), key=lambda i: norm[i][0])
                    norm[le_idx] = (0.0, norm[le_idx][1])
                    return tuple(norm)
        elif val_type == "naca":
            code = str(value.get("code") or "0012")
            clean_digits = re.sub(r"[^\d]", "", code)
            if len(clean_digits) == 5:
                return naca5(clean_digits)
            return naca4(clean_digits or "0012")
        elif val_type == "file":
            path_str = str(value.get("path") or value.get("file") or "")
            path = Path(path_str)
            if not path.is_file():
                path = AIRFOILS_DATA_DIR / path_str
            if path.is_file():
                try:
                    _, pts = parse_airfoil_dat(path.read_text(encoding="utf-8"))
                    return pts
                except (ValueError, OSError, IndexError) as exc:
                    logger.warning("Failed to parse airfoil file %s: %s", path, exc)

    # String matching
    if isinstance(value, str):
        val_str = value.strip()
        # 1. Preset dictionary
        for name, preset in PRESET_AIRFOILS.items():
            if name.lower() == val_str.lower() or name.replace(" ", "").lower() == val_str.replace(" ", "").lower():
                return preset["generator"]()
        # 2. NACA digits
        match5 = re.search(r"(?:naca\s*)?(\d{5})", val_str, re.IGNORECASE)
        if match5:
            return naca5(match5.group(1))
        match4 = re.search(r"(?:naca\s*)?(\d{4})", val_str, re.IGNORECASE)
        if match4:
            return naca4(match4.group(1))
        # 3. File path
        path = Path(val_str)
        if not path.is_file():
            path = AIRFOILS_DATA_DIR / val_str
        if path.is_file():
            try:
                _, pts = parse_airfoil_dat(path.read_text(encoding="utf-8"))
                return pts
            except (ValueError, OSError, IndexError) as exc:
                logger.warning("Failed to parse airfoil file %s: %s", path, exc)

    return naca4("0012")
