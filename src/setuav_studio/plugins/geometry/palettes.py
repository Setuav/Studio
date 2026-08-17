"""Color palettes for component and wing geometry."""

_COLORS: dict[str, tuple[tuple[float, float, float], ...]] = {
    "warm": (
        (0.90, 0.60, 0.45),  # light terracotta
        (0.65, 0.76, 0.50),  # light olive
        (0.95, 0.78, 0.50),  # light gold
        (0.76, 0.69, 0.60),  # light taupe
        (0.86, 0.60, 0.62),  # light rose
    ),
    "sunset": (
        (0.95, 0.55, 0.30),  # orange
        (0.90, 0.72, 0.40),  # amber
        (0.85, 0.45, 0.60),  # pink
        (0.68, 0.50, 0.75),  # violet
        (0.95, 0.85, 0.60),  # cream
    ),
    "forest": (
        (0.55, 0.72, 0.45),  # green
        (0.65, 0.60, 0.40),  # olive
        (0.75, 0.65, 0.45),  # khaki
        (0.60, 0.70, 0.55),  # sage
        (0.80, 0.72, 0.50),  # sand
    ),
    "desert": (
        (0.95, 0.80, 0.55),  # sand
        (0.85, 0.68, 0.45),  # taupe
        (0.90, 0.75, 0.50),  # beige
        (0.80, 0.62, 0.42),  # brown
        (0.92, 0.84, 0.65),  # cream
    ),
    "pastel": (
        (0.95, 0.75, 0.70),  # peach
        (0.75, 0.85, 0.65),  # light green
        (0.95, 0.85, 0.65),  # light yellow
        (0.85, 0.80, 0.75),  # light grey
        (0.92, 0.70, 0.72),  # light pink
    ),
    "ocean": (
        (0.55, 0.72, 0.85),  # blue
        (0.60, 0.80, 0.75),  # turquoise
        (0.75, 0.70, 0.85),  # lavender
        (0.55, 0.60, 0.75),  # steel
        (0.80, 0.85, 0.90),  # ice
    ),
}

_WING_COLORS: dict[str, tuple[float, float, float]] = {
    "warm": (0.92, 0.70, 0.50),
    "sunset": (0.95, 0.65, 0.35),
    "forest": (0.70, 0.78, 0.50),
    "desert": (0.90, 0.72, 0.48),
    "pastel": (0.90, 0.78, 0.65),
    "ocean": (0.60, 0.75, 0.85),
}

DEFAULT_PALETTE = "warm"
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