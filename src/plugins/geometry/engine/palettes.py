"""Color palettes for component, fuselage, and wing geometry."""

from __future__ import annotations

_COLORS: dict[str, tuple[tuple[float, float, float], ...]] = {
    "studio": (
        (0.65, 0.68, 0.72),  # neutral studio clay
        (0.58, 0.64, 0.72),  # slate blue
        (0.62, 0.66, 0.64),  # muted sage
        (0.70, 0.68, 0.65),  # warm clay
        (0.75, 0.76, 0.78),  # light stone
    ),
    "titanium": (
        (0.72, 0.76, 0.82),  # titanium slate
        (0.55, 0.65, 0.78),  # steel blue
        (0.62, 0.66, 0.72),  # graphite aluminum
        (0.48, 0.58, 0.70),  # midnight steel
        (0.78, 0.82, 0.88),  # light titanium
    ),
    "carbon": (
        (0.32, 0.35, 0.40),  # dark carbon anthracite
        (0.25, 0.42, 0.55),  # cobalt navy
        (0.28, 0.42, 0.38),  # emerald anthracite
        (0.38, 0.40, 0.45),  # gunmetal grey
        (0.45, 0.48, 0.52),  # carbon titanium
    ),
}

_LIFTING_SURFACE_COLORS: dict[str, tuple[float, float, float]] = {
    "studio": (0.88, 0.88, 0.90),  # pearl white / studio off-white
    "titanium": (0.86, 0.89, 0.93),  # composite aero white-grey
    "carbon": (0.82, 0.85, 0.88),  # matte aero grey
}

_CS_COLORS: dict[str, tuple[float, float, float]] = {
    "studio": (0.92, 0.28, 0.25),  # safety crimson / coral red
    "titanium": (0.95, 0.52, 0.12),  # aerospace amber / signal orange
    "carbon": (0.15, 0.65, 0.92),  # electric cyan / neon blue
}

# Studio colors are the default for aircraft geometry
DEFAULT_PALETTE = "studio"
_VIEWPORT_PALETTE_KEY = "geometry/viewport/palette"


def palette_names() -> tuple[str, ...]:
    return tuple(_COLORS.keys())


def set_active_palette(name: str) -> None:
    if name not in _COLORS:
        raise ValueError(f"Unknown palette: {name}")
    from PySide6.QtCore import QSettings

    QSettings().setValue(_VIEWPORT_PALETTE_KEY, name)


def active_palette() -> str:
    from PySide6.QtCore import QSettings

    val = str(QSettings().value(_VIEWPORT_PALETTE_KEY, DEFAULT_PALETTE))
    return val if val in _COLORS else DEFAULT_PALETTE


def segment_colors(palette: str | None = None) -> tuple[tuple[float, float, float], ...]:
    pal = palette if (palette and palette in _COLORS) else active_palette()
    return _COLORS[pal]


def lifting_surface_color(palette: str | None = None) -> tuple[float, float, float]:
    pal = palette if (palette and palette in _LIFTING_SURFACE_COLORS) else active_palette()
    return _LIFTING_SURFACE_COLORS[pal]


def control_surface_color(palette: str | None = None) -> tuple[float, float, float]:
    pal = palette if (palette and palette in _CS_COLORS) else active_palette()
    return _CS_COLORS.get(pal, (0.92, 0.28, 0.25))


__all__ = [
    "DEFAULT_PALETTE",
    "active_palette",
    "control_surface_color",
    "lifting_surface_color",
    "palette_names",
    "segment_colors",
    "set_active_palette",
]
