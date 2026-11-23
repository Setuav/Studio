"""The display color of project components.

A component may carry ``"color": "#RRGGBB"``; without one it is drawn in
:data:`DEFAULT_COMPONENT_COLOR`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

DEFAULT_COMPONENT_COLOR = "#B4B9C0"

_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")


def is_hex_color(value: object) -> bool:
    """Whether ``value`` is a ``#RRGGBB`` color string."""
    return isinstance(value, str) and _HEX_COLOR.fullmatch(value) is not None


def hex_to_rgb(color: str) -> tuple[float, float, float]:
    """``#RRGGBB`` as red, green and blue from 0 to 1."""
    if not is_hex_color(color):
        raise ValueError(f"Expected a #RRGGBB color, got {color!r}")
    return (int(color[1:3], 16) / 255.0, int(color[3:5], 16) / 255.0, int(color[5:7], 16) / 255.0)


def component_color(
    component: Mapping[str, Any],
    _components: Mapping[str, Any] | None = None,
) -> str:
    """The ``#RRGGBB`` color ``component`` is drawn in."""
    color = component.get("color")
    if color is None:
        return DEFAULT_COMPONENT_COLOR
    if not is_hex_color(color):
        raise ValueError(f"Component {component.get('id')!r} has an invalid color {color!r}")
    return str(color).upper()


__all__ = [
    "DEFAULT_COMPONENT_COLOR",
    "component_color",
    "hex_to_rgb",
    "is_hex_color",
]
