import math
from itertools import pairwise

from ..engine.data import GeometryData, LoftGeometry, Point3D, Section

SELECTED_WIRE = (0.95, 0.58, 0.28)
HOVERED_WIRE = (1.0, 1.0, 1.0)
SECTION_RING = (1.0, 0.85, 0.20)
_DIM_FACTOR = 0.5
_LONGITUDINAL_LINES = 12
FACE_COLORED = "colored"
FACE_MONOCHROME = "monochrome"
FACE_TRANSPARENT = "transparent"
_WIRE_GREY = (0.82, 0.82, 0.82)
_SOLID_GREY = (0.44, 0.44, 0.44)
_SOLID_TINT = 0.88
_WIRE_TINT = 0.30
_MIN_STATIONS = 1
_MAX_STATIONS = 32


def _wire_tint(color: Point3D) -> Point3D:
    base = 0.82
    return tuple(channel + (base - channel) * _WIRE_TINT for channel in color)


def _is_matching_component(loft_component_id: str, target_component_id: str | None) -> bool:
    if target_component_id is None:
        return False
    if loft_component_id == target_component_id:
        return True

    loft_lower = loft_component_id.lower()
    target_lower = target_component_id.lower()
    if loft_lower == target_lower:
        return True

    parts = loft_component_id.split(":")
    parts_lower = [p.lower() for p in parts]

    # 1. If target matches a subpart (e.g. "aileron" matches "main-wing:Aileron" or "main-wing:mirror:Aileron")
    if target_lower in parts_lower:
        return True

    # 2. If target is the main component (e.g. "main-wing"), matches base wing body and its mirror, but not control surface lofts
    if parts_lower[0] == target_lower:
        subparts = [
            p
            for p in parts_lower
            if p not in (target_lower, "mirror", "stations", "tip-cap", "winglet")
        ]
        if not subparts:
            return True

    return False


def build_loft_wire_vertices(
    data: GeometryData,
    selected_component_id: str | None = None,
    hovered_component_id: str | None = None,
    face_style: str = FACE_COLORED,
) -> list[float]:
    vertices: list[float] = []
    for loft in data.lofts:
        if ":stations" in loft.component_id:
            continue
        if _is_matching_component(
            loft.component_id, selected_component_id
        ) or _is_matching_component(loft.component_id, hovered_component_id):
            continue
        loops = _tessellated_loops(loft)
        if not loops:
            continue
        color = (
            _wire_tint(loft.color) if face_style in (FACE_COLORED, FACE_TRANSPARENT) else _WIRE_GREY
        )
        _append_loft_wire(vertices, loops, color)
    return vertices


def build_component_wire_vertices(
    data: GeometryData,
    component_id: str | None,
    color: Point3D = SELECTED_WIRE,
) -> list[float]:
    vertices: list[float] = []
    if component_id is None:
        return vertices
    for loft in data.lofts:
        if ":stations" in loft.component_id:
            continue
        if not _is_matching_component(loft.component_id, component_id):
            continue
        loops = _tessellated_loops(loft)
        if not loops:
            continue
        _append_loft_wire(vertices, loops, color)
    return vertices


def _append_loft_wire(vertices: list[float], loops, color: Point3D) -> None:
    for loop in loops:
        for index, point in enumerate(loop):
            _add_line(vertices, point, loop[(index + 1) % len(loop)], color)
    point_count = len(loops[0])
    for i in range(_LONGITUDINAL_LINES):
        point_index = int(i * point_count / _LONGITUDINAL_LINES)
        for current, following in pairwise(loops):
            _add_line(vertices, current[point_index], following[point_index], color)


CS_HIGHLIGHT = SELECTED_WIRE
AIRFOIL_HIGHLIGHT = SELECTED_WIRE
AIRFOIL_CHORD_HIGHLIGHT = SELECTED_WIRE


def build_section_ring_vertices(
    data: GeometryData,
    component_id: str | None,
    segment_index: int | None,
    section_index: int | None,
    color: Point3D = SECTION_RING,
) -> list[float]:
    if component_id is None or section_index is None:
        return []
    if segment_index == 1:
        return _build_control_surface_highlight(data, component_id, section_index)
    if segment_index == 2:
        return _build_station_highlight(data, component_id, section_index)
    return _build_panel_highlight(data, component_id, section_index, color)


def _build_control_surface_highlight(
    data: GeometryData,
    component_id: str,
    section_index: int,
) -> list[float]:
    control_lofts, distinct_tags = _control_surface_lofts(data, component_id)
    if 0 <= section_index < len(distinct_tags):
        target_tag = distinct_tags[section_index]
        selected_lofts = [loft for loft in control_lofts if target_tag in loft.component_id]
    else:
        selected_lofts = control_lofts

    vertices: list[float] = []
    for loft in selected_lofts:
        loops = _tessellated_loops(loft)
        if loops:
            _append_loft_wire(vertices, loops, CS_HIGHLIGHT)
    return vertices


def _control_surface_lofts(
    data: GeometryData,
    component_id: str,
) -> tuple[list[LoftGeometry], list[str]]:
    lofts: list[LoftGeometry] = []
    distinct_tags: list[str] = []
    ignored_parts = (component_id, "mirror", "stations", "tip-cap", "winglet")
    for loft in data.lofts:
        if not _is_matching_component(loft.component_id, component_id):
            continue
        subtags = [part for part in loft.component_id.split(":") if part not in ignored_parts]
        if not subtags:
            continue
        lofts.append(loft)
        for tag in subtags:
            if tag not in distinct_tags:
                distinct_tags.append(tag)
    return lofts, distinct_tags


def _build_station_highlight(
    data: GeometryData,
    component_id: str,
    section_index: int,
) -> list[float]:
    vertices: list[float] = []
    for is_mirror in (False, True):
        sections = _station_sections(_matching_station_lofts(data, component_id, is_mirror))
        if not 0 <= section_index < len(sections):
            continue
        loop = sections[section_index].points
        _append_ring(vertices, loop, AIRFOIL_HIGHLIGHT)
        if loop:
            _add_line(
                vertices,
                min(loop, key=lambda point: point[0]),
                max(loop, key=lambda point: point[0]),
                AIRFOIL_CHORD_HIGHLIGHT,
            )
    return vertices


def _build_panel_highlight(
    data: GeometryData,
    component_id: str,
    section_index: int,
    color: Point3D,
) -> list[float]:
    vertices: list[float] = []
    for is_mirror in (False, True):
        sections = _station_sections(_matching_station_lofts(data, component_id, is_mirror))
        if not 0 <= section_index < len(sections):
            continue
        root_loop = sections[section_index].points
        _append_ring(vertices, root_loop, color)

        tip_index = section_index + 1
        if tip_index >= len(sections):
            continue
        tip_loop = sections[tip_index].points
        _append_ring(vertices, tip_loop, color)
        _append_panel_rails(vertices, root_loop, tip_loop, color)
    return vertices


def _matching_station_lofts(
    data: GeometryData,
    component_id: str,
    is_mirror: bool,
) -> list[LoftGeometry]:
    excluded_parts = (":cs-", ":hinge-", ":tip-cap")
    return [
        loft
        for loft in data.lofts
        if _is_matching_component(loft.component_id, component_id)
        and ((":mirror" in loft.component_id) == is_mirror)
        and not any(part in loft.component_id for part in excluded_parts)
    ]


def _station_sections(lofts: list[LoftGeometry]) -> list[Section]:
    seen_y: list[float] = []
    sections: list[Section] = []
    for loft in lofts:
        for section in loft.sections:
            if not getattr(section, "is_station", True):
                continue
            y_coord = section.points[0][1] if section.points else 0.0
            if any(abs(y_coord - seen) < 1e-2 for seen in seen_y):
                continue
            seen_y.append(y_coord)
            sections.append(section)
    sections.sort(key=lambda section: abs(section.points[0][1]))
    return sections


def _append_ring(
    vertices: list[float],
    loop: tuple[Point3D, ...],
    color: Point3D,
) -> None:
    for index, point in enumerate(loop):
        _add_line(vertices, point, loop[(index + 1) % len(loop)], color)


def _append_panel_rails(
    vertices: list[float],
    root_loop: tuple[Point3D, ...],
    tip_loop: tuple[Point3D, ...],
    color: Point3D,
) -> None:
    point_count = min(len(root_loop), len(tip_loop))
    for fraction in (0.0, 0.25, 0.5, 0.75):
        point_index = int(fraction * point_count) % point_count
        _add_line(vertices, root_loop[point_index], tip_loop[point_index], color)


def build_loft_solid_vertices(
    data: GeometryData,
    selected_component_id: str | None = None,
    hovered_component_id: str | None = None,
    face_style: str = FACE_COLORED,
) -> list[float]:
    vertices: list[float] = []

    # Only dim if there is an active 3D selection that matches at least one loft in the scene
    has_3d_selection = False
    if selected_component_id is not None:
        has_3d_selection = any(
            _is_matching_component(loft.component_id, selected_component_id)
            for loft in data.lofts
            if ":stations" not in loft.component_id
        )

    for loft in data.lofts:
        if ":stations" in loft.component_id:
            continue
        loops = _tessellated_loops(loft)
        if not loops:
            continue
        if face_style in (FACE_COLORED, FACE_TRANSPARENT):
            color = tuple(channel * _SOLID_TINT for channel in loft.color)
        else:
            color = _SOLID_GREY

        if has_3d_selection:
            is_sel = _is_matching_component(loft.component_id, selected_component_id)
            is_hov = _is_matching_component(loft.component_id, hovered_component_id)
            if not is_sel and not is_hov:
                color = tuple(channel * _DIM_FACTOR for channel in color)

        for current, following in pairwise(loops):
            _add_quad_strip(vertices, current, following, color)
        if loft.closed_ends:
            _cap_loop(vertices, loops[0], color, flip=True)
            _cap_loop(vertices, loops[-1], color, flip=False)
    return vertices


def _tessellated_loops(loft: LoftGeometry) -> list[tuple[Point3D, ...]]:
    sections = [section.points for section in loft.sections]
    if len(sections) < 2:
        return []
    point_count = len(sections[0])
    if point_count < 3:
        raise ValueError(f"Loft {loft.component_id!r} sections require at least 3 points")
    if any(len(section) != point_count for section in sections):
        raise ValueError(f"Loft {loft.component_id!r} sections must have equal point counts")

    spacing = loft.station_spacing
    if spacing <= 0.0:
        return sections
    parameters = _section_parameters(sections)
    use_spline = loft.interpolation == "smooth" and len(sections) > 2
    splines = _build_splines(sections, parameters) if use_spline else None
    result: list[tuple[Point3D, ...]] = []
    for gap in range(len(sections) - 1):
        result.append(sections[gap])
        gap_length = parameters[gap + 1] - parameters[gap]
        inserted = _station_count(gap_length, spacing)
        for step in range(1, inserted + 1):
            fraction = step / (inserted + 1)
            if splines is None:
                result.append(
                    tuple(
                        _lerp(start, end, fraction)
                        for start, end in zip(sections[gap], sections[gap + 1], strict=True)
                    )
                )
            else:
                value = parameters[gap] + fraction * (parameters[gap + 1] - parameters[gap])
                result.append(
                    tuple(
                        (
                            _spline_eval(parameters, splines[0][index], splines[3][index], value),
                            _spline_eval(parameters, splines[1][index], splines[4][index], value),
                            _spline_eval(parameters, splines[2][index], splines[5][index], value),
                        )
                        for index in range(point_count)
                    )
                )
    result.append(sections[-1])
    return result


def _station_count(gap_length: float, spacing: float) -> int:
    count = round(gap_length / spacing)
    return min(max(count, _MIN_STATIONS), _MAX_STATIONS)


def _section_parameters(sections: list[tuple[Point3D, ...]]) -> list[float]:
    centres = [
        tuple(sum(point[axis] for point in section) / len(section) for axis in range(3))
        for section in sections
    ]
    distances = [math.dist(start, end) for start, end in pairwise(centres)]
    if any(distance < 1e-6 for distance in distances):
        return [float(index) for index in range(len(sections))]
    values = [0.0]
    for distance in distances:
        values.append(values[-1] + distance)
    return values


def _build_splines(sections, parameters):
    point_count = len(sections[0])
    x = [[section[index][0] for section in sections] for index in range(point_count)]
    y = [[section[index][1] for section in sections] for index in range(point_count)]
    z = [[section[index][2] for section in sections] for index in range(point_count)]
    return (
        x,
        y,
        z,
        [_spline_sigma(parameters, values) for values in x],
        [_spline_sigma(parameters, values) for values in y],
        [_spline_sigma(parameters, values) for values in z],
    )


def _spline_sigma(parameters: list[float], values: list[float]) -> list[float]:
    count = len(parameters)
    intervals = [parameters[index + 1] - parameters[index] for index in range(count - 1)]
    slopes = [(values[index + 1] - values[index]) / intervals[index] for index in range(count - 1)]
    diagonal = [0.0] * count
    right = [0.0] * count
    sigma = [0.0] * count
    if count > 2:
        diagonal[1] = 2.0 * (intervals[0] + intervals[1])
        right[1] = 6.0 * (slopes[1] - slopes[0])
        for index in range(2, count - 1):
            diagonal[index] = (
                2.0 * (intervals[index - 1] + intervals[index])
                - intervals[index - 1] ** 2 / diagonal[index - 1]
            )
            right[index] = (
                6.0 * (slopes[index] - slopes[index - 1])
                - intervals[index - 1] * right[index - 1] / diagonal[index - 1]
            )
        for index in range(count - 2, 0, -1):
            sigma[index] = (right[index] - intervals[index] * sigma[index + 1]) / diagonal[index]
    return sigma


def _spline_eval(parameters, values, sigma, position) -> float:
    low, high = 0, len(parameters) - 2
    while low < high:
        middle = (low + high) // 2
        if parameters[middle + 1] < position:
            low = middle + 1
        else:
            high = middle
    interval = parameters[low + 1] - parameters[low]
    start = (parameters[low + 1] - position) / interval
    end = (position - parameters[low]) / interval
    return (
        start * values[low]
        + end * values[low + 1]
        + ((start**3 - start) * sigma[low] + (end**3 - end) * sigma[low + 1]) * interval**2 / 6.0
    )


def _add_quad_strip(vertices, first, second, color) -> None:
    for index in range(len(first)):
        following = (index + 1) % len(first)
        p0, p1 = first[index], first[following]
        p2, p3 = second[index], second[following]
        _add_triangle(vertices, p0, p1, p2, color)
        _add_triangle(vertices, p1, p3, p2, color)


def _cap_loop(vertices, loop, color, flip: bool) -> None:
    centre = tuple(sum(point[axis] for point in loop) / len(loop) for axis in range(3))
    for index, point in enumerate(loop):
        following = loop[(index + 1) % len(loop)]
        if flip:
            _add_triangle(vertices, centre, following, point, color)
        else:
            _add_triangle(vertices, centre, point, following, color)


def _add_triangle(vertices, first, second, third, color) -> None:
    normal = _normal(first, second, third)
    for point in (first, second, third):
        vertices.extend((*point, *normal, *color))


def _normal(first: Point3D, second: Point3D, third: Point3D) -> Point3D:
    left = tuple(second[index] - first[index] for index in range(3))
    right = tuple(third[index] - first[index] for index in range(3))
    value = (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )
    length = math.sqrt(sum(component * component for component in value))
    return tuple(component / length for component in value) if length > 1e-9 else (0.0, 0.0, 1.0)


def _lerp(start: Point3D, end: Point3D, fraction: float) -> Point3D:
    return tuple(start[index] * (1.0 - fraction) + end[index] * fraction for index in range(3))


def _add_line(vertices, start, end, color) -> None:
    vertices.extend((*start, *color, *end, *color))


def hit_test_loft(
    data: GeometryData,
    origin: Point3D,
    direction: Point3D,
) -> str | None:
    best_distance: float | None = None
    best_id: str | None = None
    for loft in data.lofts:
        loops = _tessellated_loops(loft)
        if not loops:
            continue
        for current, following in pairwise(loops):
            for index in range(len(current)):
                next_index = (index + 1) % len(current)
                first, second = current[index], current[next_index]
                third, fourth = following[index], following[next_index]
                for triangle in ((first, second, third), (second, fourth, third)):
                    distance = _ray_triangle_intersection(origin, direction, triangle)
                    if distance is None or (
                        best_distance is not None and distance >= best_distance
                    ):
                        continue
                    best_distance = distance
                    best_id = loft.component_id
        cap_distance = _loft_cap_hit_distance(loft, loops, origin, direction, best_distance)
        if cap_distance is not None:
            best_distance = cap_distance
            best_id = loft.component_id
    return best_id


def _loft_cap_hit_distance(
    loft: LoftGeometry,
    loops: list[tuple[Point3D, ...]],
    origin: Point3D,
    direction: Point3D,
    current_best: float | None,
) -> float | None:
    if not loft.closed_ends:
        return None
    best = current_best
    found = False
    for loop, flip in ((loops[0], True), (loops[-1], False)):
        centre = tuple(sum(point[axis] for point in loop) / len(loop) for axis in range(3))
        for index, point in enumerate(loop):
            following = loop[(index + 1) % len(loop)]
            triangle = (centre, following, point) if flip else (centre, point, following)
            distance = _ray_triangle_intersection(origin, direction, triangle)
            if distance is not None and (best is None or distance < best):
                best = distance
                found = True
    return best if found else None


def _ray_triangle_intersection(
    origin: Point3D,
    direction: Point3D,
    triangle: tuple[Point3D, Point3D, Point3D],
) -> float | None:
    first, second, third = triangle
    edge1 = _subtract(second, first)
    edge2 = _subtract(third, first)
    cross = _cross(direction, edge2)
    determinant = _dot(edge1, cross)
    if abs(determinant) < 1e-9:
        return None
    inverse = 1.0 / determinant
    offset = _subtract(origin, first)
    u = _dot(offset, cross) * inverse
    if u < 0.0 or u > 1.0:
        return None
    perpendicular = _cross(offset, edge1)
    v = _dot(direction, perpendicular) * inverse
    if v < 0.0 or u + v > 1.0:
        return None
    distance = _dot(edge2, perpendicular) * inverse
    return distance if distance >= 0.0 else None


def _dot(left: Point3D, right: Point3D) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _cross(left: Point3D, right: Point3D) -> Point3D:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _subtract(left: Point3D, right: Point3D) -> Point3D:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])
