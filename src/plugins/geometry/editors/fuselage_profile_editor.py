"""Fuselage cross-section profile property configuration and formatting utilities."""

from __future__ import annotations

import contextlib
from typing import Any

from setuav_studio_sdk import StudioAPI

from ..engine.fuselage_geometry import FUSELAGE_PROFILE_TYPES, get_default_profile

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
            num = float(val or 0.0)
            disp = um.to_display(num, "length")
            return f"{disp:.1f}" if abs(disp - round(disp)) > 1e-4 else f"{disp:.0f}"
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


def evaluate_expression_or_number(
    val_str: str,
    api: StudioAPI | None,
) -> tuple[float | None, bool]:
    """Evaluate expression string or parse numeric float.

    Returns:
        tuple[num_val, is_expression]
    """
    val_clean = val_str.strip()
    if val_clean.startswith("=") or not val_clean.replace(".", "", 1).replace("-", "", 1).isdigit():
        if api is not None and getattr(api, "current_project", None) is not None:
            try:
                from setuav_studio.model.expression import ExpressionEvaluator

                evaluator = ExpressionEvaluator()
                scope = api.current_project.get_scope(api=api)
                expr = val_clean.lstrip("=").strip()
                res = evaluator.evaluate(expr, scope)
                if isinstance(res, (int, float)):
                    return float(res), True
            except Exception:
                pass
        return None, True
    with contextlib.suppress(ValueError):
        return float(val_clean), False
    return None, False


__all__ = [
    "FUSELAGE_PROFILE_TYPES",
    "PROFILE_FIELDS",
    "evaluate_expression_or_number",
    "format_profile_size",
    "get_default_profile",
]
