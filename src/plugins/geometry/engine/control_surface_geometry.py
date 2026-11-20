"""Analytical geometry calculations for control surfaces (sizing, shaping, metrics)."""

from __future__ import annotations

import math
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
    """Semi-span, root chord and tip chord (mm) and area (dm²) of the surface a control
    surface is cut from."""
    if len(profiles) < 2:
        raise ValueError("A lifting surface needs at least two profiles")
    semi_span = abs(float(profiles[-1]["position"]["y"]) - float(profiles[0]["position"]["y"]))
    root_chord = float(profiles[0]["chord"])
    tip_chord = float(profiles[-1]["chord"])
    return semi_span, root_chord, tip_chord, semi_span * (root_chord + tip_chord) / 10000.0


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
    geometry: dict[str, Any],
    semi_span: float,
    root_chord: float,
    tip_chord: float | None = None,
    parent_surface_area: float | None = None,
) -> dict[str, float]:
    """Compute all geometric metrics including area, area ratio, span length, and chords."""
    span_start, eta_start, span_end, eta_end = resolve_span_values(geometry, semi_span)
    chord, chord_fraction = resolve_chord_values(geometry, root_chord)

    span_length = max(span_end - span_start, 0.0)
    eta_length = max(eta_end - eta_start, 0.0)

    tc = tip_chord if tip_chord is not None else root_chord
    eta_mid = (eta_start + eta_end) / 2.0
    c_local_mid = max(root_chord + (tc - root_chord) * eta_mid, 1.0)

    area_mm2 = span_length * c_local_mid * chord_fraction
    area_dm2 = area_mm2 / 10000.0

    if parent_surface_area and parent_surface_area > 0:
        area_ratio = (area_dm2 / parent_surface_area) * 100.0
    else:
        semi_surface_area_dm2 = max((semi_span * (root_chord + tc) / 2.0) / 10000.0, 1e-4)
        area_ratio = (area_dm2 / semi_surface_area_dm2) * 100.0

    return {
        "span_start": span_start,
        "span_end": span_end,
        "span_length": round(span_length, 1),
        "eta_start": eta_start,
        "eta_end": eta_end,
        "eta_length": round(eta_length, 4),
        "chord": chord,
        "chord_fraction": chord_fraction,
        "area_mm2": round(area_mm2, 2),
        "area_dm2": round(area_dm2, 4),
        "area_ratio": round(area_ratio, 2),
    }


def solve_control_surface_from_area(
    geometry: dict[str, Any],
    target_area_dm2: float,
    semi_span: float,
    root_chord: float,
    tip_chord: float | None = None,
    driver_mode: str = "area_chord",
) -> None:
    """Solve for span_end or chord_fraction from target planform area."""
    target_area_mm2 = max(target_area_dm2 * 10000.0, 1.0)
    tc = tip_chord if tip_chord is not None else root_chord
    _, eta_start, _, eta_end = resolve_span_values(geometry, semi_span)
    _chord, chord_fraction = resolve_chord_values(geometry, root_chord)

    if driver_mode == "area_span":
        # Span extent is fixed, solve for required chord_fraction
        eta_mid = (eta_start + eta_end) / 2.0
        c_local_mid = max(root_chord + (tc - root_chord) * eta_mid, 1.0)
        span_length = max((eta_end - eta_start) * semi_span, 1.0)
        new_cf = min(max(target_area_mm2 / (span_length * c_local_mid), 0.02), 0.95)
        geometry["chord_fraction"] = round(new_cf, 3)
        geometry["chord"] = round(new_cf * root_chord, 1)
    else:
        # Chord fraction is fixed, solve for required span_length / eta_end
        cf = max(chord_fraction, 0.02)
        K = target_area_mm2 / (max(semi_span, 1.0) * cf)
        c0 = root_chord
        dc = tc - root_chord
        if abs(dc) < 1e-4:
            d_eta = K / max(c0, 1.0)
            new_eta2 = min(max(eta_start + d_eta, eta_start + 0.01), 1.0)
        else:
            A = 0.5 * dc
            B = c0
            C = -(0.5 * dc * (eta_start**2) + c0 * eta_start + K)
            disc = B * B - 4 * A * C
            new_eta2 = (-B + math.sqrt(disc)) / (2 * A) if disc >= 0 else eta_start + 0.3
            new_eta2 = min(max(new_eta2, eta_start + 0.01), 1.0)

        geometry["eta_end"] = round(new_eta2, 4)
        geometry["span_end"] = round(new_eta2 * semi_span, 1)


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
    "resolve_chord_values",
    "resolve_span_values",
    "sizing_mode",
    "solve_control_surface_from_area",
    "span_follows_ratio",
    "surface_span_info",
    "sync_sizing_values",
]
