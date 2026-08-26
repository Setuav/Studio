"""Shared control-surface sizing normalization helpers."""

from __future__ import annotations

from typing import Any


def resolve_span_values(
    geometry: dict[str, Any], semi_span: float
) -> tuple[float, float, float, float]:
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


def sync_sizing_values(geometry: dict[str, Any], semi_span: float, root_chord: float) -> None:
    span_mode = str(geometry.get("span_mode", "ratio")).lower()
    if span_mode == "ratio":
        _span_start, eta_start, _span_end, eta_end = resolve_span_values(geometry, semi_span)
        geometry["span_start"] = round(eta_start * semi_span, 1)
        geometry["span_end"] = round(eta_end * semi_span, 1)
    else:
        geometry["eta_start"] = round(float(geometry.get("span_start", 0.0)) / semi_span, 4)
        geometry["eta_end"] = round(float(geometry.get("span_end", 0.0)) / semi_span, 4)

    if str(geometry.get("chord_mode", "ratio")).lower() == "ratio":
        _, fraction = resolve_chord_values(geometry, root_chord)
        geometry["chord"] = round(fraction * root_chord, 1)
    else:
        geometry["chord_fraction"] = round(float(geometry.get("chord", 40.0)) / root_chord, 3)
