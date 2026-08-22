"""Color palettes for component, fuselage, and wing geometry."""

_COLORS: dict[str, tuple[tuple[float, float, float], ...]] = {
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
    "studio": (
        (0.65, 0.68, 0.72),  # neutral studio clay
        (0.58, 0.64, 0.72),  # slate blue
        (0.62, 0.66, 0.64),  # muted sage
        (0.70, 0.68, 0.65),  # warm clay
        (0.75, 0.76, 0.78),  # light stone
    ),
}

_WING_COLORS: dict[str, tuple[float, float, float]] = {
    "titanium": (0.86, 0.89, 0.93),  # composite aero white-grey
    "carbon": (0.82, 0.85, 0.88),    # matte aero grey
    "studio": (0.88, 0.88, 0.90),    # pearl white / studio off-white
}

_CS_COLORS: dict[str, tuple[float, float, float]] = {
    "titanium": (0.95, 0.52, 0.12),  # aerospace amber / signal orange
    "carbon": (0.15, 0.65, 0.92),    # electric cyan / neon blue
    "studio": (0.92, 0.28, 0.25),    # safety crimson / coral red
}

DEFAULT_PALETTE = "titanium"
_active_palette = DEFAULT_PALETTE


def palette_names() -> tuple[str, ...]:
    return tuple(_COLORS.keys())


def set_active_palette(name: str) -> None:
    if name not in _COLORS:
        raise ValueError(f"Unknown palette: {name}")
    global _active_palette
    _active_palette = name


def active_palette() -> str:
    return _active_palette


def segment_colors() -> tuple[tuple[float, float, float], ...]:
    return _COLORS[_active_palette]


def wing_color() -> tuple[float, float, float]:
    return _WING_COLORS[_active_palette]


def control_surface_color() -> tuple[float, float, float]:
    return _CS_COLORS.get(_active_palette, (0.95, 0.52, 0.12))
