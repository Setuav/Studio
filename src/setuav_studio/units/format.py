"""Number formatting for values shown in display units."""

from __future__ import annotations

from typing import Any


def format_engineering_value(val: Any, decimals: int | None = 2) -> str:
    """Cleanly formats numbers removing floating-point noise and keeping engineering precision."""
    if val is None or val == "":
        return ""
    try:
        f_val = float(val)
    except (ValueError, TypeError):
        return str(val)

    effective_decimals = 2 if decimals is None else decimals
    rounded = round(f_val, effective_decimals)
    if abs(rounded) < 1e-12:
        return "0" if effective_decimals == 0 else "0.0"
    if effective_decimals == 0:
        return str(int(rounded))
    if abs(rounded - int(rounded)) < 1e-9:
        return f"{rounded:.1f}"
    formatted = f"{rounded:.{effective_decimals}f}".rstrip("0")
    if formatted.endswith("."):
        formatted += "0"
    return formatted


__all__ = ["format_engineering_value"]
