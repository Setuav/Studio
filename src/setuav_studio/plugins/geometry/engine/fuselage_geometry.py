import math
from typing import Any

from ..viewport.palettes import segment_colors
from .data import LoftGeometry, Section
from .transforms import section_transform, transform_point

SECTION_SAMPLES = 128


def build_fuselage_geometry(component: dict[str, Any]) -> tuple[LoftGeometry, ...]:
    parameters = component.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    segments = geometry.get("segments")
    if not isinstance(segments, list):
        return ()

    component_id = str(component.get("id") or "fuselage")
    colors = segment_colors()
    lofts: list[LoftGeometry] = []
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        values = segment.get("sections")
        if not isinstance(values, list):
            continue
        sections = tuple(
            section for value in values if (section := _build_section(value)) is not None
        )
        if len(sections) < 2:
            continue
        loft = segment.get("loft")
        loft = loft if isinstance(loft, dict) else {}
        lofts.append(
            LoftGeometry(
                component_id=component_id,
                sections=sections,
                color=colors[index % len(colors)],
                interpolation="linear" if loft.get("method") == "ruled" else "smooth",
                station_spacing=10.0,
            )
        )
    return tuple(lofts)


def _build_section(value: object) -> Section | None:
    section = value if isinstance(value, dict) else None
    if section is None:
        return None
    profile = section.get("profile")
    if not isinstance(profile, dict):
        return None
    points_2d = sample_profile(profile)
    matrix = section_transform(section)
    return Section(tuple(transform_point(matrix, (0.0, y, z)) for y, z in points_2d))


def sample_profile(profile: dict[str, Any]) -> tuple[tuple[float, float], ...]:
    profile_type = profile.get("type")
    if profile_type == "circle":
        radius = _number(profile.get("diameter")) * 0.5
        return _ellipse(radius, radius)
    if profile_type == "ellipse":
        return _ellipse(
            _number(profile.get("width")) * 0.5,
            _number(profile.get("height")) * 0.5,
        )

    vertices: list[tuple[float, float, float]]
    if profile_type == "rectangle":
        half_width = _number(profile.get("width")) * 0.5
        half_height = _number(profile.get("height")) * 0.5
        radius = _number(profile.get("corner_radius"))
        vertices = [
            (half_width, -half_height, radius),
            (half_width, half_height, radius),
            (-half_width, half_height, radius),
            (-half_width, -half_height, radius),
        ]
    elif profile_type == "trapezoid":
        top = _number(profile.get("top_width")) * 0.5
        bottom = _number(profile.get("bottom_width")) * 0.5
        half_height = _number(profile.get("height")) * 0.5
        radius = _number(profile.get("corner_radius"))
        vertices = [
            (bottom, -half_height, radius),
            (top, half_height, radius),
            (-top, half_height, radius),
            (-bottom, -half_height, radius),
        ]
    elif profile_type == "triangle":
        half_width = _number(profile.get("base_width")) * 0.5
        half_height = _number(profile.get("height")) * 0.5
        radius = _number(profile.get("corner_radius"))
        if profile.get("orientation") == "down":
            vertices = [
                (half_width, half_height, radius),
                (-half_width, half_height, radius),
                (0.0, -half_height, radius),
            ]
        else:
            vertices = [
                (half_width, -half_height, radius),
                (0.0, half_height, radius),
                (-half_width, -half_height, radius),
            ]
    elif profile_type == "polygon":
        raw_vertices = profile.get("vertices")
        if not isinstance(raw_vertices, list):
            return _ellipse(0.0, 0.0)
        vertices = [
            (
                _number(vertex.get("y")),
                _number(vertex.get("z")),
                max(0.0, _number(vertex.get("radius"))),
            )
            for vertex in raw_vertices
            if isinstance(vertex, dict)
        ]
    else:
        return _ellipse(0.0, 0.0)

    if len(vertices) < 3:
        return _ellipse(0.0, 0.0)
    outline = _rounded_outline(vertices)
    return _radial_samples(outline)


def _ellipse(radius_y: float, radius_z: float) -> tuple[tuple[float, float], ...]:
    return tuple(
        (
            radius_y * math.cos(2.0 * math.pi * index / SECTION_SAMPLES),
            radius_z * math.sin(2.0 * math.pi * index / SECTION_SAMPLES),
        )
        for index in range(SECTION_SAMPLES)
    )


def _rounded_outline(
    vertices: list[tuple[float, float, float]],
) -> list[tuple[float, float]]:
    if _signed_area(vertices) < 0:
        vertices = list(reversed(vertices))
    outline: list[tuple[float, float]] = []
    count = len(vertices)
    for index, (y, z, requested_radius) in enumerate(vertices):
        previous = vertices[index - 1]
        following = vertices[(index + 1) % count]
        incoming = _unit(previous[0] - y, previous[1] - z)
        outgoing = _unit(following[0] - y, following[1] - z)
        edge_in = math.hypot(previous[0] - y, previous[1] - z)
        edge_out = math.hypot(following[0] - y, following[1] - z)
        dot = max(-1.0, min(1.0, incoming[0] * outgoing[0] + incoming[1] * outgoing[1]))
        angle = math.acos(dot)
        cross = incoming[0] * outgoing[1] - incoming[1] * outgoing[0]
        if requested_radius <= 0 or angle < 1e-6 or cross >= 0:
            outline.append((y, z))
            continue
        tangent = min(
            requested_radius / max(math.tan(angle * 0.5), 1e-9),
            edge_in * 0.49,
            edge_out * 0.49,
        )
        radius = tangent * math.tan(angle * 0.5)
        bisector = _unit(incoming[0] + outgoing[0], incoming[1] + outgoing[1])
        centre_distance = radius / max(math.sin(angle * 0.5), 1e-9)
        centre = (y + bisector[0] * centre_distance, z + bisector[1] * centre_distance)
        tangent_in = (y + incoming[0] * tangent, z + incoming[1] * tangent)
        tangent_out = (y + outgoing[0] * tangent, z + outgoing[1] * tangent)
        start = math.atan2(tangent_in[1] - centre[1], tangent_in[0] - centre[0])
        end = math.atan2(tangent_out[1] - centre[1], tangent_out[0] - centre[0])
        while end <= start:
            end += 2.0 * math.pi
        for step in range(9):
            angle_at_step = start + (end - start) * step / 8
            outline.append(
                (
                    centre[0] + radius * math.cos(angle_at_step),
                    centre[1] + radius * math.sin(angle_at_step),
                )
            )
    return outline


def _radial_samples(outline: list[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    if not outline or max(math.hypot(y, z) for y, z in outline) < 1e-9:
        return ((0.0, 0.0),) * SECTION_SAMPLES
    result: list[tuple[float, float]] = []
    for index in range(SECTION_SAMPLES):
        angle = 2.0 * math.pi * index / SECTION_SAMPLES
        direction = (math.cos(angle), math.sin(angle))
        nearest: float | None = None
        for start, end in zip(outline, outline[1:] + outline[:1], strict=True):
            segment = (end[0] - start[0], end[1] - start[1])
            denominator = _cross2(direction, segment)
            if abs(denominator) < 1e-10:
                continue
            distance = _cross2(start, segment) / denominator
            fraction = _cross2(start, direction) / denominator
            if (
                distance >= -1e-8
                and -1e-8 <= fraction <= 1.0 + 1e-8
                and (nearest is None or distance < nearest)
            ):
                nearest = max(0.0, distance)
        result.append((direction[0] * (nearest or 0.0), direction[1] * (nearest or 0.0)))
    return tuple(result)


def _signed_area(vertices: list[tuple[float, float, float]]) -> float:
    return 0.5 * sum(
        start[0] * end[1] - end[0] * start[1]
        for start, end in zip(vertices, vertices[1:] + vertices[:1], strict=True)
    )


def _unit(y: float, z: float) -> tuple[float, float]:
    length = math.hypot(y, z)
    return (y / length, z / length) if length > 1e-9 else (0.0, 0.0)


def _cross2(left: tuple[float, float], right: tuple[float, float]) -> float:
    return left[0] * right[1] - left[1] * right[0]


def _number(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


FUSELAGE_PROFILE_TYPES: tuple[str, ...] = (
    "circle",
    "ellipse",
    "rectangle",
    "trapezoid",
    "triangle",
    "polygon",
)

DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "circle": {"type": "circle", "diameter": 100.0},
    "ellipse": {"type": "ellipse", "width": 100.0, "height": 100.0},
    "rectangle": {
        "type": "rectangle",
        "width": 100.0,
        "height": 100.0,
        "corner_radius": 0.0,
    },
    "trapezoid": {
        "type": "trapezoid",
        "top_width": 80.0,
        "bottom_width": 100.0,
        "height": 100.0,
        "corner_radius": 0.0,
    },
    "triangle": {
        "type": "triangle",
        "base_width": 100.0,
        "height": 100.0,
        "orientation": "up",
        "corner_radius": 0.0,
    },
    "polygon": {
        "type": "polygon",
        "vertices": [
            {"y": -50.0, "z": -50.0, "radius": 0.0},
            {"y": 50.0, "z": -50.0, "radius": 0.0},
            {"y": 0.0, "z": 50.0, "radius": 0.0},
        ],
    },
}


def get_default_profile(profile_type: str) -> dict[str, Any]:
    """Return a deepcopy of the default profile configuration dictionary."""
    template = DEFAULT_PROFILES.get(profile_type, DEFAULT_PROFILES["circle"])
    return {
        key: [v.copy() if isinstance(v, dict) else v for v in val] if isinstance(val, list) else val
        for key, val in template.items()
    }


def create_default_section(x: float = 0.0, profile_type: str = "circle") -> dict[str, Any]:
    """Create a standard default fuselage cross-section data structure."""
    return {
        "position": {"x": x, "y": 0.0, "z": 0.0},
        "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
        "profile": get_default_profile(profile_type),
    }


def create_default_segment(
    tag: str = "main",
    x_start: float = 0.0,
    x_end: float = 500.0,
) -> dict[str, Any]:
    """Create a standard fuselage segment with start and end sections."""
    return {
        "tag": tag,
        "loft": {"method": "smooth", "parameterization": "uniform"},
        "sections": [
            create_default_section(x_start),
            create_default_section(x_end),
        ],
    }


def format_profile_size(profile: dict[str, Any]) -> str:
    """Format human-readable profile dimensions."""
    profile_type = profile.get("type")
    if profile_type == "circle":
        return f"D {profile.get('diameter', 0)}"
    if profile_type in {"ellipse", "rectangle"}:
        return f"{profile.get('width', 0)} × {profile.get('height', 0)}"
    if profile_type == "trapezoid":
        return f"{profile.get('top_width', 0)} / {profile.get('bottom_width', 0)}"
    if profile_type == "triangle":
        return f"{profile.get('base_width', 0)} × {profile.get('height', 0)}"
    if profile_type == "polygon":
        return f"{len(profile.get('vertices') or [])} vertices"
    return ""


def compute_section_metrics(points: tuple[tuple[float, float], ...]) -> dict[str, float]:
    """Compute geometric and engineering metrics from a 2D closed polygon outline."""
    if len(points) < 3:
        return {
            "area": 0.0,
            "perimeter": 0.0,
            "width": 0.0,
            "height": 0.0,
            "y_cg": 0.0,
            "z_cg": 0.0,
            "aspect_ratio": 0.0,
            "hydraulic_diam": 0.0,
        }

    n = len(points)
    area2 = 0.0
    perimeter = 0.0
    y_sum = 0.0
    z_sum = 0.0

    ys = [p[0] for p in points]
    zs = [p[1] for p in points]

    for i in range(n):
        y0, z0 = points[i]
        y1, z1 = points[(i + 1) % n]
        cross = y0 * z1 - y1 * z0
        area2 += cross
        perimeter += math.hypot(y1 - y0, z1 - z0)
        y_sum += (y0 + y1) * cross
        z_sum += (z0 + z1) * cross

    area = abs(area2) * 0.5
    if abs(area2) > 1e-9:
        y_cg = y_sum / (3.0 * area2)
        z_cg = z_sum / (3.0 * area2)
    else:
        y_cg = sum(ys) / n
        z_cg = sum(zs) / n

    width = max(ys) - min(ys)
    height = max(zs) - min(zs)
    aspect_ratio = width / max(height, 1e-6)
    dh = (4.0 * area / perimeter) if perimeter > 1e-9 else 0.0

    return {
        "area": area,
        "perimeter": perimeter,
        "width": width,
        "height": height,
        "y_cg": y_cg,
        "z_cg": z_cg,
        "aspect_ratio": aspect_ratio,
        "hydraulic_diam": dh,
    }
