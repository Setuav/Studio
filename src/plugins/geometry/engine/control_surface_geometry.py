"""Analytical geometry calculations for control surfaces (sizing, shaping, metrics)."""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Any

SIZING_MODES = ("ratio", "dimension", "area_chord", "area_span")


def sizing_mode(geometry: dict[str, Any]) -> str:
    """The sizing mode chosen for the control surface in its editor."""
    mode = geometry["sizing_mode"]
    if mode not in SIZING_MODES:
        raise ValueError(f"Unknown control surface sizing mode {mode!r}")
    return mode


def span_follows_ratio(geometry: dict[str, Any]) -> bool:
    """Whether the span extent is kept as a fraction of the semi-span (eta) rather than in mm."""
    return sizing_mode(geometry) == "ratio"


def chord_follows_ratio(geometry: dict[str, Any]) -> bool:
    """Whether the chord is kept as a fraction of the surface chord rather than in mm."""
    return sizing_mode(geometry) != "dimension"


def surface_span_info(profiles: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    """Semi-span, root chord and tip chord (mm) and the planform area of one side (dm²)
    of the surface a control surface is cut from."""
    if len(profiles) < 2:
        raise ValueError("A lifting surface needs at least two profiles")
    semi_span = abs(float(profiles[-1]["position"]["y"]) - float(profiles[0]["position"]["y"]))
    root_chord = float(profiles[0]["chord"])
    tip_chord = float(profiles[-1]["chord"])
    panel_area_mm2 = sum(
        0.5
        * (float(inner["chord"]) + float(outer["chord"]))
        * abs(float(outer["position"]["y"]) - float(inner["position"]["y"]))
        for inner, outer in pairwise(profiles)
    )
    return semi_span, root_chord, tip_chord, panel_area_mm2 / 10000.0


def planform_station(profiles: list[dict[str, Any]], span: float) -> tuple[float, float]:
    """Leading-edge x and chord (mm) at ``span`` mm from the root, interpolated between
    the profiles as the 3D model does."""
    y_root = float(profiles[0]["position"]["y"])
    direction = 1.0 if float(profiles[-1]["position"]["y"]) >= y_root else -1.0
    y = y_root + direction * span
    ordered = sorted(profiles, key=lambda profile: float(profile["position"]["y"]))
    ys = [float(profile["position"]["y"]) for profile in ordered]
    if y <= ys[0]:
        return float(ordered[0]["position"]["x"]), float(ordered[0]["chord"])
    if y >= ys[-1]:
        return float(ordered[-1]["position"]["x"]), float(ordered[-1]["chord"])
    index = next(i for i in range(len(ys) - 1) if ys[i + 1] >= y)
    inner, outer = ordered[index], ordered[index + 1]
    t = (y - ys[index]) / max(ys[index + 1] - ys[index], 1e-9)
    leading_edge = float(inner["position"]["x"]) + t * (
        float(outer["position"]["x"]) - float(inner["position"]["x"])
    )
    chord = float(inner["chord"]) + t * (float(outer["chord"]) - float(inner["chord"]))
    return leading_edge, chord


def hinge_fraction_at(
    geometry: dict[str, Any], profiles: list[dict[str, Any]], span: float
) -> float:
    """Hinge position as a fraction of the local chord at ``span`` mm from the root.

    With a Hinge Sweep the hinge is a straight line that starts the control chord ahead
    of the trailing edge at Span Start; without one it keeps the chord fraction.
    """
    semi_span, root_chord, *_ = surface_span_info(profiles)
    leading_edge, chord = planform_station(profiles, span)
    chord = max(chord, 1.0)
    control_chord, fraction = resolve_chord_values(geometry, root_chord)
    sweep = geometry.get("hinge_sweep")
    if sweep is not None:
        span_start, *_ = resolve_span_values(geometry, semi_span)
        start_leading_edge, start_chord = planform_station(profiles, span_start)
        hinge_x = (
            start_leading_edge
            + start_chord
            - max(control_chord, 1.0)
            + (span - span_start) * math.tan(math.radians(float(sweep)))
        )
        return min(max((hinge_x - leading_edge) / chord, 0.05), 0.95)
    depth = fraction if chord_follows_ratio(geometry) else control_chord / chord
    return 1.0 - min(max(depth, 0.05), 0.95)


def control_area_mm2(geometry: dict[str, Any], profiles: list[dict[str, Any]]) -> float:
    """Planform area of one side of the control surface behind its hinge line (mm²)."""
    semi_span, *_ = surface_span_info(profiles)
    span_start, _eta_start, span_end, _eta_end = resolve_span_values(geometry, semi_span)
    low, high = sorted((span_start, span_end))
    y_root = float(profiles[0]["position"]["y"])
    breaks = sorted(
        {low, high}
        | {
            abs(float(profile["position"]["y"]) - y_root)
            for profile in profiles
            if low < abs(float(profile["position"]["y"]) - y_root) < high
        }
    )

    def control_chord(span: float) -> float:
        _leading_edge, chord = planform_station(profiles, span)
        return chord * (1.0 - hinge_fraction_at(geometry, profiles, span))

    area = 0.0
    for inner, outer in pairwise(breaks):
        # The clamped hinge makes the chord only piecewise linear, so sample each panel.
        stations = [inner + (outer - inner) * i / 8 for i in range(9)]
        chords = [control_chord(span) for span in stations]
        area += sum(
            0.5 * (chords[i] + chords[i + 1]) * (stations[i + 1] - stations[i]) for i in range(8)
        )
    return area


def resolve_span_values(
    geometry: dict[str, Any], semi_span: float
) -> tuple[float, float, float, float]:
    """Resolve start and end span/eta values from control surface geometry."""
    start, eta_start = _resolve_span_endpoint(geometry, "start", semi_span, 0.4)
    end, eta_end = _resolve_span_endpoint(geometry, "end", semi_span, 0.85)
    return start, eta_start, end, eta_end


def _resolve_span_endpoint(
    geometry: dict[str, Any], endpoint: str, semi_span: float, default_eta: float
) -> tuple[float, float]:
    span_key = f"span_{endpoint}"
    eta_key = f"eta_{endpoint}"
    if span_key in geometry:
        span = float(geometry.get(span_key, 0.0))
        eta = float(geometry.get(eta_key, round(span / semi_span, 4)))
    elif eta_key in geometry:
        eta = float(geometry.get(eta_key, 0.0))
        span = round(eta * semi_span, 1)
        geometry[span_key] = span
    else:
        eta = default_eta
        span = round(semi_span * eta, 1)
        geometry[span_key] = span
        geometry[eta_key] = eta
    return span, eta


def resolve_chord_values(geometry: dict[str, Any], root_chord: float) -> tuple[float, float]:
    """Resolve absolute chord length and chord fraction from geometry."""
    if "chord_fraction" in geometry and geometry.get("chord_fraction") is not None:
        fraction = float(geometry.get("chord_fraction", 0.25))
        chord = float(geometry.get("chord", round(fraction * root_chord, 1)))
    elif "chord" in geometry:
        chord = float(geometry.get("chord", 40.0))
        fraction = round(chord / root_chord, 3)
        geometry["chord_fraction"] = fraction
    else:
        fraction = 0.25
        chord = round(root_chord * fraction, 1)
        geometry["chord"] = chord
        geometry["chord_fraction"] = fraction
    return chord, fraction


def compute_control_surface_metrics(
    geometry: dict[str, Any], profiles: list[dict[str, Any]]
) -> dict[str, float]:
    """Sizing values, area and area ratio of a control surface on its lifting surface.

    The area is one side's, behind the hinge line the 3D model cuts; the area ratio is
    its share of that side of the lifting surface.
    """
    semi_span, root_chord, _tip_chord, panel_area_dm2 = surface_span_info(profiles)
    span_start, eta_start, span_end, eta_end = resolve_span_values(geometry, semi_span)
    chord, chord_fraction = resolve_chord_values(geometry, root_chord)
    area_mm2 = control_area_mm2(geometry, profiles)
    area_dm2 = area_mm2 / 10000.0
    return {
        "span_start": span_start,
        "span_end": span_end,
        "span_length": round(max(span_end - span_start, 0.0), 1),
        "eta_start": eta_start,
        "eta_end": eta_end,
        "eta_length": round(max(eta_end - eta_start, 0.0), 4),
        "chord": chord,
        "chord_fraction": chord_fraction,
        "area_mm2": round(area_mm2, 2),
        "area_dm2": round(area_dm2, 4),
        "area_ratio": round(area_dm2 / max(panel_area_dm2, 1e-9) * 100.0, 2),
    }


def solve_control_surface_from_area(
    geometry: dict[str, Any],
    target_area_dm2: float,
    profiles: list[dict[str, Any]],
    driver_mode: str = "area_chord",
) -> None:
    """Set the chord (area_span) or the span end (area_chord) that gives the target area."""
    semi_span, root_chord, *_ = surface_span_info(profiles)
    target_mm2 = max(target_area_dm2 * 10000.0, 1.0)
    _span_start, eta_start, _span_end, _eta_end = resolve_span_values(geometry, semi_span)

    def set_chord_fraction(fraction: float) -> None:
        geometry["chord_fraction"] = round(fraction, 3)
        geometry["chord"] = round(fraction * root_chord, 1)

    def set_eta_end(eta: float) -> None:
        geometry["eta_end"] = round(eta, 4)
        geometry["span_end"] = round(eta * semi_span, 1)

    if driver_mode == "area_span":
        low, high, apply = 0.02, 0.95, set_chord_fraction
    else:
        low, high, apply = min(eta_start + 0.01, 1.0), 1.0, set_eta_end
    # The area grows with both the chord and the span end, so bisect.
    for _ in range(40):
        middle = 0.5 * (low + high)
        apply(middle)
        if control_area_mm2(geometry, profiles) < target_mm2:
            low = middle
        else:
            high = middle
    apply(0.5 * (low + high))


def sync_sizing_values(geometry: dict[str, Any], semi_span: float, root_chord: float) -> None:
    """Synchronize span/chord units between ratio and absolute values."""
    if span_follows_ratio(geometry):
        _span_start, eta_start, _span_end, eta_end = resolve_span_values(geometry, semi_span)
        geometry["span_start"] = round(eta_start * semi_span, 1)
        geometry["span_end"] = round(eta_end * semi_span, 1)
    else:
        geometry["eta_start"] = round(float(geometry["span_start"]) / semi_span, 4)
        geometry["eta_end"] = round(float(geometry["span_end"]) / semi_span, 4)

    if chord_follows_ratio(geometry):
        _, fraction = resolve_chord_values(geometry, root_chord)
        geometry["chord"] = round(fraction * root_chord, 1)
    else:
        geometry["chord_fraction"] = round(float(geometry["chord"]) / root_chord, 3)


__all__ = [
    "SIZING_MODES",
    "chord_follows_ratio",
    "compute_control_surface_metrics",
    "control_area_mm2",
    "hinge_fraction_at",
    "planform_station",
    "resolve_chord_values",
    "resolve_span_values",
    "sizing_mode",
    "solve_control_surface_from_area",
    "span_follows_ratio",
    "surface_span_info",
    "sync_sizing_values",
]
