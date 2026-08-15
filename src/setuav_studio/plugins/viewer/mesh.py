import math

from setuav_studio.geometry_data import GeometryData, LoftGeometry, Point3D


_SELECTED_COLOR = (0.50, 0.77, 0.82)
_LONGITUDINAL_LINES = 12
FACE_COLORED = "colored"
FACE_MONOCHROME = "monochrome"
FACE_TRANSPARENT = "transparent"
_WIRE_GREY = (0.90, 0.90, 0.90)
_SOLID_GREY = (0.62, 0.62, 0.62)


def build_loft_wire_vertices(
    data: GeometryData,
    selected_component_id: str | None = None,
    face_style: str = FACE_COLORED,
) -> list[float]:
    vertices: list[float] = []
    for loft in data.lofts:
        loops = _tessellated_loops(loft)
        if not loops:
            continue
        color = (
            _SELECTED_COLOR
            if loft.component_id == selected_component_id
            else loft.color if face_style == FACE_COLORED else _WIRE_GREY
        )
        for loop in loops:
            for index, point in enumerate(loop):
                _add_line(vertices, point, loop[(index + 1) % len(loop)], color)
        step = max(1, len(loops[0]) // _LONGITUDINAL_LINES)
        for point_index in range(0, len(loops[0]), step):
            for current, following in zip(loops, loops[1:]):
                _add_line(vertices, current[point_index], following[point_index], color)
    return vertices


def build_loft_solid_vertices(
    data: GeometryData,
    selected_component_id: str | None = None,
    face_style: str = FACE_COLORED,
) -> list[float]:
    vertices: list[float] = []
    for loft in data.lofts:
        loops = _tessellated_loops(loft)
        if not loops:
            continue
        if loft.component_id == selected_component_id:
            color = tuple(channel * 0.65 for channel in _SELECTED_COLOR)
        elif face_style == FACE_COLORED:
            color = tuple(channel * 0.65 for channel in loft.color)
        else:
            color = _SOLID_GREY
        for current, following in zip(loops, loops[1:]):
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

    inserted = max(0, loft.subdivisions)
    if inserted == 0:
        return sections
    parameters = _section_parameters(sections)
    use_spline = loft.interpolation == "smooth" and len(sections) > 2
    splines = _build_splines(sections, parameters) if use_spline else None
    result: list[tuple[Point3D, ...]] = []
    for gap in range(len(sections) - 1):
        result.append(sections[gap])
        for step in range(1, inserted + 1):
            fraction = step / (inserted + 1)
            if splines is None:
                result.append(
                    tuple(
                        _lerp(start, end, fraction)
                        for start, end in zip(sections[gap], sections[gap + 1])
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


def _section_parameters(sections: list[tuple[Point3D, ...]]) -> list[float]:
    centres = [
        tuple(sum(point[axis] for point in section) / len(section) for axis in range(3))
        for section in sections
    ]
    distances = [math.dist(start, end) for start, end in zip(centres, centres[1:])]
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
        x, y, z,
        [_spline_sigma(parameters, values) for values in x],
        [_spline_sigma(parameters, values) for values in y],
        [_spline_sigma(parameters, values) for values in z],
    )


def _spline_sigma(parameters: list[float], values: list[float]) -> list[float]:
    count = len(parameters)
    intervals = [parameters[index + 1] - parameters[index] for index in range(count - 1)]
    slopes = [
        (values[index + 1] - values[index]) / intervals[index]
        for index in range(count - 1)
    ]
    diagonal = [0.0] * count
    right = [0.0] * count
    sigma = [0.0] * count
    if count > 2:
        diagonal[1] = 2.0 * (intervals[0] + intervals[1])
        right[1] = 6.0 * (slopes[1] - slopes[0])
        for index in range(2, count - 1):
            diagonal[index] = 2.0 * (intervals[index - 1] + intervals[index]) - intervals[index - 1] ** 2 / diagonal[index - 1]
            right[index] = 6.0 * (slopes[index] - slopes[index - 1]) - intervals[index - 1] * right[index - 1] / diagonal[index - 1]
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
    return start * values[low] + end * values[low + 1] + (
        (start**3 - start) * sigma[low] + (end**3 - end) * sigma[low + 1]
    ) * interval**2 / 6.0


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
