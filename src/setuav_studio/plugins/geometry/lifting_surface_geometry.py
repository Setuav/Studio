import math
import re
from typing import Any

from setuav_studio.geometry_data import LoftGeometry, Section
from setuav_studio.geometry_scene import section_transform, transform_point


AIRFOIL_SAMPLES = 64
_WING_COLOR = (51 / 255, 127 / 255, 229 / 255)


def build_lifting_surface_geometry(
    component: dict[str, Any],
) -> tuple[LoftGeometry, ...]:
    parameters = component.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    profiles = geometry.get("profiles")
    if not isinstance(profiles, list):
        return ()

    sections = tuple(
        section
        for value in profiles
        if (section := _build_profile_section(value)) is not None
    )
    if len(sections) < 2:
        return ()
    blending = geometry.get("blending")
    blending = blending if isinstance(blending, dict) else {}
    return (
        LoftGeometry(
            component_id=str(component.get("id") or "lifting-surface"),
            sections=sections,
            color=_WING_COLOR,
            interpolation="linear" if blending.get("ruled") is True else "smooth",
            subdivisions=6,
        ),
    )


def _build_profile_section(value: object) -> Section | None:
    profile = value if isinstance(value, dict) else None
    if profile is None:
        return None
    chord = _number(profile.get("chord"))
    if chord <= 0:
        return None
    coordinates = sample_airfoil(profile.get("airfoil"))
    matrix = section_transform(profile)
    return Section(
        tuple(
            transform_point(matrix, (x * chord, 0.0, z * chord))
            for x, z in coordinates
        )
    )


def sample_airfoil(value: object) -> tuple[tuple[float, float], ...]:
    if isinstance(value, dict) and value.get("type") == "coordinates":
        points = value.get("points")
        if isinstance(points, list):
            parsed = [
                (_number(point[0]), _number(point[1]))
                for point in points
                if isinstance(point, list) and len(point) == 2
            ]
            if len(parsed) >= 3:
                return _resample_closed(parsed, AIRFOIL_SAMPLES * 2)

    code: str | None = None
    if isinstance(value, str):
        match = re.search(r"(?:naca\s*)?(\d{4})", value, re.IGNORECASE)
        code = match.group(1) if match else None
    elif isinstance(value, dict) and value.get("type") == "naca":
        raw_code = str(value.get("code") or "")
        code = raw_code if re.fullmatch(r"\d{4}", raw_code) else None
    return _naca4(code or "0012")


def _naca4(code: str) -> tuple[tuple[float, float], ...]:
    camber = int(code[0]) / 100.0
    camber_position = int(code[1]) / 10.0
    thickness = int(code[2:]) / 100.0
    upper: list[tuple[float, float]] = []
    lower: list[tuple[float, float]] = []
    for index in range(AIRFOIL_SAMPLES + 1):
        x = 0.5 * (1.0 - math.cos(math.pi * index / AIRFOIL_SAMPLES))
        yt = 5.0 * thickness * (
            0.2969 * math.sqrt(max(x, 1e-9))
            - 0.1260 * x
            - 0.3516 * x**2
            + 0.2843 * x**3
            - 0.1015 * x**4
        )
        yc = 0.0
        slope = 0.0
        if camber_position > 0.0:
            if x < camber_position:
                yc = camber / camber_position**2 * (2 * camber_position * x - x**2)
                slope = 2 * camber / camber_position**2 * (camber_position - x)
            else:
                remaining = 1.0 - camber_position
                yc = camber / remaining**2 * (
                    1 - 2 * camber_position + 2 * camber_position * x - x**2
                )
                slope = 2 * camber / remaining**2 * (camber_position - x)
        angle = math.atan(slope)
        upper.append((x - yt * math.sin(angle), yc + yt * math.cos(angle)))
        if 0 < index < AIRFOIL_SAMPLES:
            lower.append((x + yt * math.sin(angle), yc - yt * math.cos(angle)))
    return tuple(upper + list(reversed(lower)))


def _resample_closed(
    points: list[tuple[float, float]],
    count: int,
) -> tuple[tuple[float, float], ...]:
    if points[0] == points[-1]:
        points = points[:-1]
    lengths = [0.0]
    closed = points + [points[0]]
    for start, end in zip(closed, closed[1:]):
        lengths.append(lengths[-1] + math.dist(start, end))
    total = lengths[-1]
    if total < 1e-9:
        return ((0.0, 0.0),) * count
    result: list[tuple[float, float]] = []
    segment = 0
    for index in range(count):
        distance = total * index / count
        while segment + 1 < len(lengths) and lengths[segment + 1] < distance:
            segment += 1
        span = lengths[segment + 1] - lengths[segment]
        fraction = 0.0 if span < 1e-9 else (distance - lengths[segment]) / span
        start, end = closed[segment], closed[segment + 1]
        result.append(
            (
                start[0] * (1 - fraction) + end[0] * fraction,
                start[1] * (1 - fraction) + end[1] * fraction,
            )
        )
    return tuple(result)


def _number(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
