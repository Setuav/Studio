"""Fuselage cross-section profile property configuration and formatting utilities."""

from __future__ import annotations

from typing import Any

from ...engine.fuselage_geometry import FUSELAGE_PROFILE_TYPES, get_default_profile

PROFILE_FIELDS: dict[str, list[tuple[str, str]]] = {
    "circle": [("diameter", "Diameter")],
    "ellipse": [("width", "Width"), ("height", "Height")],
    "rectangle": [
        ("width", "Width"),
        ("height", "Height"),
        ("corner_radius", "Corner radius"),
    ],
    "trapezoid": [
        ("top_width", "Top width"),
        ("bottom_width", "Bottom width"),
        ("height", "Height"),
        ("corner_radius", "Corner radius"),
    ],
    "triangle": [
        ("base_width", "Base width"),
        ("height", "Height"),
        ("orientation", "Orientation"),
        ("corner_radius", "Corner radius"),
    ],
    "polygon": [("vertices", "Vertices")],
}


def format_profile_size(profile: dict[str, Any]) -> str:
    """Format human-readable profile dimensions with current unit system."""
    from setuav_studio.units import get_unit_manager

    um = get_unit_manager()
    profile_type = profile.get("type")
    length_sym = um.get_unit_symbol("length")

    def _fmt(val: Any) -> str:
        try:
            return um.format_number(float(val or 0.0), "length", 1)
        except (ValueError, TypeError):
            return str(val)

    if profile_type == "circle":
        return f"D {_fmt(profile.get('diameter', 0))} {length_sym}"
    if profile_type in {"ellipse", "rectangle"}:
        return f"{_fmt(profile.get('width', 0))} × {_fmt(profile.get('height', 0))} {length_sym}"
    if profile_type == "trapezoid":
        return f"{_fmt(profile.get('top_width', 0))} / {_fmt(profile.get('bottom_width', 0))} {length_sym}"
    if profile_type == "triangle":
        return (
            f"{_fmt(profile.get('base_width', 0))} × {_fmt(profile.get('height', 0))} {length_sym}"
        )
    if profile_type == "polygon":
        return f"{len(profile.get('vertices') or [])} vertices"
    return ""


__all__ = [
    "FUSELAGE_PROFILE_TYPES",
    "PROFILE_FIELDS",
    "format_profile_size",
    "get_default_profile",
]
