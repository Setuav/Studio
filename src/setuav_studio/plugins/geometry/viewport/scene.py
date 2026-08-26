import math
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from ..engine.data import GeometryData, LoftGeometry, Section
from ..engine.transforms import (
    Matrix4,
    derivation_matrix,
    identity_matrix,
    multiply_matrix,
    transform_matrix,
    transform_point,
)
from .palettes import segment_colors

GeometryProvider = Callable[[dict[str, Any]], tuple[LoftGeometry, ...]]


def _frame_parent(item: dict[str, Any]) -> str | None:
    """Return the geometric coordinate-frame parent (attach_to, fallback parent)."""
    attach_to = item.get("attach_to")
    if isinstance(attach_to, str) and attach_to:
        return attach_to
    parent = item.get("parent")
    return parent if isinstance(parent, str) and parent else None


def build_project_geometry(
    project: Any,
    providers: dict[str, GeometryProvider],
) -> GeometryData:
    items = _project_items(project)
    if items is None:
        return GeometryData()

    world_matrix = _WorldMatrixResolver(items)
    lofts: list[LoftGeometry] = []
    for item_id, item in items.items():
        source = _geometry_source(item, items)
        if source is None:
            continue
        _attach_child_control_surfaces(source, item_id, items)
        _append_component_geometry(
            lofts,
            item_id,
            item,
            source,
            providers,
            world_matrix,
        )
    lofts.extend(_build_wing_root_stubs(items, providers, world_matrix))
    return GeometryData(tuple(lofts))


def _project_items(project: Any) -> dict[str, dict[str, Any]] | None:
    project_data = getattr(project, "data", project) if project is not None else {}
    components = project_data.get("components") if isinstance(project_data, dict) else None
    if not isinstance(components, list):
        return None
    return {
        item["id"]: item
        for item in components
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


class _WorldMatrixResolver:
    def __init__(self, items: dict[str, dict[str, Any]]) -> None:
        self.items = items
        self.cache: dict[str, Matrix4] = {}

    def __call__(
        self,
        item_id: str,
        resolving: frozenset[str] = frozenset(),
    ) -> Matrix4:
        if item_id in self.cache:
            return self.cache[item_id]
        if item_id in resolving:
            raise ValueError(f"Component parent cycle at {item_id!r}")
        item = self.items.get(item_id)
        if item is None:
            return identity_matrix()

        parent_id = _frame_parent(item)
        parent = (
            self(parent_id, resolving | {item_id})
            if isinstance(parent_id, str)
            else identity_matrix()
        )
        local = self._local_matrix(item)
        result = multiply_matrix(parent, local)
        self.cache[item_id] = result
        return result

    def _local_matrix(self, item: dict[str, Any]) -> Matrix4:
        local = transform_matrix(item.get("transform"))
        if item.get("kind") != "instance":
            return local
        source = self.items.get(item.get("source"))
        source_transform = (
            transform_matrix(source.get("transform"))
            if isinstance(source, dict)
            else identity_matrix()
        )
        derivation = derivation_matrix(item.get("derivation"))
        return multiply_matrix(local, multiply_matrix(derivation, source_transform))


def _geometry_source(
    item: dict[str, Any],
    items: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    source = deepcopy(item)
    if item.get("kind") != "instance":
        return source
    candidate = items.get(item.get("source"))
    if not isinstance(candidate, dict):
        return None
    source = deepcopy(candidate)
    overrides = item.get("parameter_overrides")
    if isinstance(overrides, dict):
        parameters = source.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}
            source["parameters"] = parameters
        _merge(parameters, overrides)
    if _is_xz_mirror(item.get("derivation")):
        _invert_differential_controls(source)
    return source


def _is_xz_mirror(derivation: Any) -> bool:
    if not isinstance(derivation, dict) or derivation.get("type") != "mirror":
        return False
    return derivation.get("plane", "XZ") in ("XZ", "1", None)


def _invert_differential_controls(source: dict[str, Any]) -> None:
    parameters = source.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    controls = geometry.get("control_surfaces")
    if not isinstance(controls, list):
        return
    for control in controls:
        if isinstance(control, dict) and str(control.get("type", "aileron")).lower() in (
            "aileron",
            "elevon",
        ):
            control["deflection"] = -float(control.get("deflection", 0.0))


def _attach_child_control_surfaces(
    source: dict[str, Any],
    item_id: str,
    items: dict[str, dict[str, Any]],
) -> None:
    if source.get("type") != "org.setuav.core:lifting-surface":
        return
    controls = [
        control
        for child in items.values()
        if (control := _child_control_surface(child, item_id)) is not None
    ]
    if controls:
        parameters = source.setdefault("parameters", {})
        geometry = parameters.setdefault("geometry", {})
        geometry["control_surfaces"] = controls


def _child_control_surface(
    child: dict[str, Any],
    parent_id: str,
) -> dict[str, Any] | None:
    if (
        child.get("type") != "org.setuav.core:control-surface"
        or (_frame_parent(child) or "") != parent_id
    ):
        return None
    parameters = child.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    control = deepcopy(geometry) if isinstance(geometry, dict) else {}
    control.setdefault("tag", child.get("name") or child.get("id"))
    return control


def _append_component_geometry(
    lofts: list[LoftGeometry],
    item_id: str,
    item: dict[str, Any],
    source: dict[str, Any],
    providers: dict[str, GeometryProvider],
    world_matrix: Callable[[str], Matrix4],
) -> None:
    component_type = source.get("type")
    provider = providers.get(component_type) if isinstance(component_type, str) else None
    if provider is None:
        return
    matrix = world_matrix(item_id)
    lofts.extend(_transform_loft(loft, matrix, item_id) for loft in provider(source))
    if component_type == "org.setuav.core:lifting-surface" and _is_bilateral(source):
        _append_mirrored_geometry(
            lofts,
            item_id,
            item,
            source,
            provider,
            world_matrix,
        )


def _is_bilateral(source: dict[str, Any]) -> bool:
    parameters = source.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    return geometry.get("mirror") is True or source.get("mirror") is True


def _append_mirrored_geometry(
    lofts: list[LoftGeometry],
    item_id: str,
    item: dict[str, Any],
    source: dict[str, Any],
    provider: GeometryProvider,
    world_matrix: Callable[[str], Matrix4],
) -> None:
    parent_id = _frame_parent(item)
    parent_matrix = world_matrix(parent_id) if isinstance(parent_id, str) else identity_matrix()
    local_matrix = transform_matrix(item.get("transform"))
    mirror = derivation_matrix({"type": "mirror", "plane": "XZ"})
    mirrored_matrix = multiply_matrix(
        parent_matrix,
        multiply_matrix(mirror, local_matrix),
    )
    mirrored_source = deepcopy(source)
    _invert_differential_controls(mirrored_source)
    lofts.extend(
        _transform_loft(loft, mirrored_matrix, f"{item_id}:mirror")
        for loft in provider(mirrored_source)
    )


def _transform_loft(loft: LoftGeometry, matrix: Matrix4, component_id: str) -> LoftGeometry:
    target_id = component_id
    if ":" in loft.component_id:
        sub_tag = loft.component_id.split(":", 1)[1]
        target_id = f"{component_id}:{sub_tag}"
    return LoftGeometry(
        component_id=target_id,
        sections=tuple(
            Section(
                tuple(transform_point(matrix, point) for point in section.points),
                is_station=section.is_station,
            )
            for section in loft.sections
        ),
        color=loft.color,
        interpolation=loft.interpolation,
        station_spacing=loft.station_spacing,
        closed_ends=loft.closed_ends,
    )


def _merge(target: dict[str, Any], overrides: dict[str, Any]) -> None:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = deepcopy(value)


def _build_wing_root_stubs(
    items: dict[str, Any],
    providers: dict[str, GeometryProvider],
    world_matrix_fn: Callable[[str], Matrix4],
) -> list[LoftGeometry]:
    provider = providers.get("org.setuav.core:lifting-surface")
    if provider is None:
        return []

    stubs: list[LoftGeometry] = []
    for fuselage in _fuselage_items(items):
        fuselage_id = fuselage.get("id")
        if not isinstance(fuselage_id, str):
            continue
        color = _fuselage_stub_color()
        for item_id, item in items.items():
            if _frame_parent(item) != fuselage_id:
                continue
            source = _geometry_source(item, items)
            if source is None or source.get("type") != "org.setuav.core:lifting-surface":
                continue
            wing_lofts = provider(source)
            if not wing_lofts or not wing_lofts[0].sections:
                continue
            root_section = wing_lofts[0].sections[0]
            matrices = [world_matrix_fn(item_id)]
            if _is_bilateral(source):
                matrices.append(_mirrored_root_matrix(item, fuselage_id, world_matrix_fn))
            for matrix in matrices:
                stub = _build_root_stub(fuselage, fuselage_id, root_section, matrix, color)
                if stub is not None:
                    stubs.append(stub)
    return stubs


def _fuselage_items(items: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in items.values()
        if isinstance(item, dict) and item.get("type") == "org.setuav.core:fuselage"
    ]


def _fuselage_stub_color() -> tuple[float, float, float, float]:
    colors = segment_colors()
    return colors[0] if colors else (0.8, 0.8, 0.8, 1.0)


def _mirrored_root_matrix(
    item: dict[str, Any],
    fuselage_id: str,
    world_matrix_fn: Callable[[str], Matrix4],
) -> Matrix4:
    parent_matrix = world_matrix_fn(fuselage_id)
    local_matrix = transform_matrix(item.get("transform"))
    mirror = derivation_matrix({"type": "mirror", "plane": "XZ"})
    return multiply_matrix(parent_matrix, multiply_matrix(mirror, local_matrix))


def _build_root_stub(
    fuselage: dict[str, Any],
    fuselage_id: str,
    root_section: Section,
    matrix: Matrix4,
    color: tuple[float, float, float, float],
) -> LoftGeometry | None:
    outer_points = tuple(transform_point(matrix, point) for point in root_section.points)
    inward = _inward_span_direction(matrix)
    inner_points, has_gap = _project_root_points(fuselage, outer_points, inward)
    if not has_gap:
        return None
    return LoftGeometry(
        component_id=fuselage_id,
        sections=(Section(inner_points), Section(outer_points)),
        color=color,
        interpolation="linear",
        station_spacing=10.0,
        closed_ends=False,
    )


def _inward_span_direction(matrix: Matrix4) -> tuple[float, float, float]:
    origin = transform_point(matrix, (0.0, 0.0, 0.0))
    inward_point = transform_point(matrix, (0.0, -1.0, 0.0))
    vector = tuple(inward_point[axis] - origin[axis] for axis in range(3))
    length = math.sqrt(sum(value**2 for value in vector))
    return (
        vector[0] / max(length, 1e-6),
        vector[1] / max(length, 1e-6),
        vector[2] / max(length, 1e-6),
    )


def _project_root_points(
    fuselage: dict[str, Any],
    outer_points: tuple[tuple[float, float, float], ...],
    inward: tuple[float, float, float],
) -> tuple[tuple[tuple[float, float, float], ...], bool]:
    inner_points: list[tuple[float, float, float]] = []
    has_gap = False
    for outer_point in outer_points:
        inner_point, point_has_gap = _project_point_to_fuselage(
            fuselage,
            outer_point,
            inward,
        )
        inner_points.append(inner_point)
        if point_has_gap:
            has_gap = True
    return tuple(inner_points), has_gap


def _get_fuselage_cross_section_at_x(
    fuse_comp: dict[str, Any],
    x_target: float,
) -> tuple[float, float, float, float, str]:
    params = fuse_comp.get("parameters") if isinstance(fuse_comp.get("parameters"), dict) else {}
    geom = params.get("geometry") if isinstance(params.get("geometry"), dict) else {}
    segments = geom.get("segments") if isinstance(geom.get("segments"), list) else []

    sections: list[tuple[float, float, float, float, float, str]] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        for sec in seg.get("sections", []):
            if not isinstance(sec, dict):
                continue
            pos = sec.get("position") if isinstance(sec.get("position"), dict) else {}
            sec_x = float(pos.get("x", 0.0))
            sec_y = float(pos.get("y", 0.0))
            sec_z = float(pos.get("z", 0.0))
            prof = sec.get("profile") if isinstance(sec.get("profile"), dict) else {}
            p_type = str(prof.get("type", "circle"))
            if p_type == "circle":
                w = float(prof.get("diameter", 0.0))
                h = w
            elif p_type in ("ellipse", "rectangle"):
                w = float(prof.get("width", 0.0))
                h = float(prof.get("height", 0.0))
            else:
                w = float(prof.get("width", prof.get("diameter", 100.0)))
                h = float(prof.get("height", prof.get("diameter", 100.0)))
            sections.append((sec_x, sec_y, sec_z, max(w * 0.5, 1e-4), max(h * 0.5, 1e-4), p_type))

    sections.sort(key=lambda s: s[0])
    if not sections:
        return 0.0, 0.0, 50.0, 50.0, "circle"

    if x_target <= sections[0][0]:
        sec = sections[0]
        return sec[1], sec[2], sec[3], sec[4], sec[5]
    elif x_target >= sections[-1][0]:
        sec = sections[-1]
        return sec[1], sec[2], sec[3], sec[4], sec[5]
    else:
        for i in range(len(sections) - 1):
            if sections[i][0] <= x_target <= sections[i + 1][0]:
                x0, y0, z0, a0, b0, p0 = sections[i]
                x1, y1, z1, a1, b1, _p1 = sections[i + 1]
                t = (x_target - x0) / max(x1 - x0, 1e-6)
                return (
                    y0 + t * (y1 - y0),
                    z0 + t * (z1 - z0),
                    a0 + t * (a1 - a0),
                    b0 + t * (b1 - b0),
                    p0,
                )

    return 0.0, 0.0, 50.0, 50.0, "circle"


def _project_point_to_fuselage(
    fuse_comp: dict[str, Any],
    pt: tuple[float, float, float],
    d_in: tuple[float, float, float],
) -> tuple[tuple[float, float, float], bool]:
    gx, gy, gz = pt
    dx, dy, dz = d_in
    y_c, z_c, r_y, r_z, _ = _get_fuselage_cross_section_at_x(fuse_comp, gx)

    u_0 = (gy - y_c) / r_y
    v_0 = (gz - z_c) / r_z
    u_d = dy / r_y
    v_d = dz / r_z

    if u_0**2 + v_0**2 <= 1.0 + 1e-4:
        return pt, False

    a = u_d**2 + v_d**2
    if a < 1e-9:
        return pt, False

    b = 2.0 * (u_0 * u_d + v_0 * v_d)
    c = u_0**2 + v_0**2 - 1.0
    disc = b**2 - 4.0 * a * c

    if disc < 0.0:
        angle = math.atan2(v_0, u_0)
        target_y = y_c + r_y * math.cos(angle)
        target_z = z_c + r_z * math.sin(angle)
        return (gx, target_y, target_z), True

    t1 = (-b - math.sqrt(disc)) / (2.0 * a)
    t2 = (-b + math.sqrt(disc)) / (2.0 * a)
    t = t1 if t1 > 0.0 else t2
    if t <= 1e-3:
        return pt, False

    p_in = (gx + t * dx, gy + t * dy, gz + t * dz)
    return p_in, True
