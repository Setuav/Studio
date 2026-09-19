"""Constants for 3D viewport display modes and camera view presets."""

from __future__ import annotations

WIRE_FEATURE = "feature"
WIRE_FULL = "full"
FACE_COLORED = "colored"
FACE_MONOCHROME = "monochrome"

VIEW_PRESETS: dict[str, tuple[float, float]] = {
    "top": (0.0, 90.0),
    "bottom": (0.0, -90.0),
    "front": (270.0, 0.0),
    "side": (180.0, 0.0),
    "iso": (210.0, 20.0),
}
