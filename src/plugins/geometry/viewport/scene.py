import math
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from ..engine.data import EnvelopeWireGeometry, GeometryData, LoftGeometry, Point3D, Section
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

    envelopes: list[EnvelopeWireGeometry] = []
    for item_id, item in items.items():
        source = _geometry_source(item, items) or item
        env_geom = _build_component_envelope_geometry(
            item_id, item, source, world_matrix, items
        )
        if env_geom is not None:
            envelopes.append(env_geom)

    return GeometryData(tuple(lofts), tuple(envelopes))


def _project_items(project: Any) -> dict[str, dict[str, Any]] | None:
    project_data = getattr(project, "data", project) if project is not None else {}
    components = project_data.get("components") if isinstance(project_data, dict) else None
    if not isinstance(components, list):
        return None
    from setuav_studio.model.configuration import ConfigurationManager

    cfg_mgr = ConfigurationManager(project_data)
    return {
        item["id"]: cfg_mgr.get_resolved_component(item)
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
    control.setdefault("tag", child.get("id") or child.get("name"))
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
        parameterization=loft.parameterization,
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
            wing = _wing_root_geometry(item, items, provider)
            if wing is None:
                continue
            source, root_section = wing
            matrices = [world_matrix_fn(item_id)]
            if _is_bilateral(source):
                matrices.append(_mirrored_root_matrix(item, fuselage_id, world_matrix_fn))
            for matrix in matrices:
                stub = _build_root_stub(fuselage, fuselage_id, root_section, matrix, color)
                if stub is not None:
                    stubs.append(stub)
    return stubs


def _wing_root_geometry(
    item: dict[str, Any], items: dict[str, Any], provider: GeometryProvider
) -> tuple[dict[str, Any], Section] | None:
    source = _geometry_source(item, items)
    if source is None or source.get("type") != "org.setuav.core:lifting-surface":
        return None
    lofts = provider(source)
    if not lofts or not lofts[0].sections:
        return None
    return source, lofts[0].sections[0]


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
    sections = _fuselage_cross_sections(fuse_comp)
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


def _fuselage_cross_sections(
    component: dict[str, Any],
) -> list[tuple[float, float, float, float, float, str]]:
    parameters = component.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    segments = geometry.get("segments")
    segments = segments if isinstance(segments, list) else []
    result: list[tuple[float, float, float, float, float, str]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        for section in segment.get("sections", []):
            if isinstance(section, dict):
                result.append(_fuselage_cross_section(section))
    return result


def _fuselage_cross_section(
    section: dict[str, Any],
) -> tuple[float, float, float, float, float, str]:
    position = section.get("position")
    position = position if isinstance(position, dict) else {}
    profile = section.get("profile")
    profile = profile if isinstance(profile, dict) else {}
    profile_type = str(profile.get("type", "circle"))
    if profile_type == "circle":
        width = height = float(profile.get("diameter", 0.0))
    elif profile_type in {"ellipse", "rectangle"}:
        width = float(profile.get("width", 0.0))
        height = float(profile.get("height", 0.0))
    else:
        width = float(profile.get("width", profile.get("diameter", 100.0)))
        height = float(profile.get("height", profile.get("diameter", 100.0)))
    return (
        float(position.get("x", 0.0)),
        float(position.get("y", 0.0)),
        float(position.get("z", 0.0)),
        max(width * 0.5, 1e-4),
        max(height * 0.5, 1e-4),
        profile_type,
    )


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


def _build_component_envelope_geometry(
    item_id: str,
    item: dict[str, Any],
    source: dict[str, Any],
    world_matrix: Callable[[str], Matrix4],
    items: dict[str, dict[str, Any]],
) -> EnvelopeWireGeometry | None:
    envelope = item.get("envelope") or source.get("envelope")
    component_type = source.get("type")

    parent_id = _frame_parent(item) or item.get("parent") or item.get("attach_to")
    parent_item = items.get(str(parent_id)) if parent_id else None
    parent_source = _geometry_source(parent_item, items) if parent_item else None

    if component_type in (
        "org.setuav.core:lifting-surface",
        "org.setuav.core:fuselage",
        "org.setuav.core:control-surface",
    ):
        secs = envelope.get("sections") if isinstance(envelope, dict) else None
        if (
            not secs
            or not all(isinstance(s, dict) and "corners_3d" in s for s in secs)
            or (component_type == "org.setuav.core:control-surface" and "hinge_axis" not in envelope)
        ):
            try:
                from plugins.geometry.engine.envelope import compute_geometry_envelope

                fresh = compute_geometry_envelope(source or item, parent_source)
                if isinstance(fresh, dict) and fresh:
                    envelope = fresh
                    if isinstance(source, dict):
                        source["envelope"] = fresh
            except Exception:
                pass
    elif not isinstance(envelope, dict):
        try:
            from plugins.geometry.engine.envelope import compute_geometry_envelope

            envelope = compute_geometry_envelope(source or item, parent_source)
        except Exception:
            envelope = None
    if not isinstance(envelope, dict) or not envelope:
        return None

    matrix = world_matrix(item_id)
    lines: list[tuple[Point3D, Point3D]] = []

    cs_deflection = 0.0
    cs_type = "aileron"
    if component_type == "org.setuav.core:control-surface":
        params = source.get("parameters") if isinstance(source, dict) else {}
        geom = params.get("geometry") if isinstance(params, dict) else {}
        if isinstance(geom, dict):
            cs_deflection = float(geom.get("deflection", 0.0))
            cs_type = str(geom.get("type", "aileron")).lower()

    env_to_draw = (
        _rotate_control_surface_envelope(envelope, cs_deflection)
        if component_type == "org.setuav.core:control-surface"
        else envelope
    )
    _append_envelope_lines(lines, env_to_draw, matrix)

    if component_type == "org.setuav.core:lifting-surface":
        _append_lifting_surface_tip_envelope_lines(lines, source, matrix)

    if component_type == "org.setuav.core:lifting-surface" and _is_bilateral(source):
        parent_id_frame = _frame_parent(item)
        parent_matrix = world_matrix(parent_id_frame) if isinstance(parent_id_frame, str) else identity_matrix()
        local_matrix = transform_matrix(item.get("transform"))
        mirror = derivation_matrix({"type": "mirror", "plane": "XZ"})
        mirrored_matrix = multiply_matrix(
            parent_matrix,
            multiply_matrix(mirror, local_matrix),
        )
        _append_envelope_lines(lines, envelope, mirrored_matrix)
        _append_lifting_surface_tip_envelope_lines(lines, source, mirrored_matrix)

    if (
        component_type == "org.setuav.core:control-surface"
        and parent_source
        and _is_bilateral(parent_source)
    ):
        parent_parent_id = _frame_parent(parent_item) if parent_item else None
        pp_matrix = world_matrix(parent_parent_id) if isinstance(parent_parent_id, str) else identity_matrix()
        parent_local_matrix = transform_matrix(parent_item.get("transform")) if parent_item else identity_matrix()
        cs_local_matrix = transform_matrix(item.get("transform"))
        mirror = derivation_matrix({"type": "mirror", "plane": "XZ"})
        mirrored_matrix = multiply_matrix(
            pp_matrix,
            multiply_matrix(mirror, multiply_matrix(parent_local_matrix, cs_local_matrix)),
        )
        mirrored_deflection = (
            -cs_deflection if cs_type in ("aileron", "elevon") else cs_deflection
        )
        mirrored_env = _rotate_control_surface_envelope(envelope, mirrored_deflection)
        _append_envelope_lines(lines, mirrored_env, mirrored_matrix)

    if not lines:
        return None
    return EnvelopeWireGeometry(component_id=item_id, lines=tuple(lines))


def _rotate_control_surface_envelope(
    envelope: dict[str, Any],
    angle_deg: float,
) -> dict[str, Any]:
    if abs(angle_deg) <= 1e-4:
        return envelope

    hinge_axis = envelope.get("hinge_axis")
    if isinstance(hinge_axis, (list, tuple)) and len(hinge_axis) >= 2:
        p0 = hinge_axis[0]
        p1 = hinge_axis[-1]
        ox = float(p0["x"])
        oy = float(p0["y"])
        oz = float(p0["z"])
        dx = float(p1["x"]) - ox
        dy = float(p1["y"]) - oy
        dz = float(p1["z"]) - oz
    else:
        secs = envelope.get("sections")
        if not isinstance(secs, list) or len(secs) < 2:
            return envelope
        c0 = secs[0].get("corners_3d") or []
        cN = secs[-1].get("corners_3d") or []
        if len(c0) < 4 or len(cN) < 4:
            return envelope
        ox = float(c0[0]["x"])
        oy = float(c0[0]["y"])
        oz = (float(c0[0]["z"]) + float(c0[3]["z"])) * 0.5
        end_x = float(cN[0]["x"])
        end_y = float(cN[0]["y"])
        end_z = (float(cN[0]["z"]) + float(cN[3]["z"])) * 0.5
        dx = end_x - ox
        dy = end_y - oy
        dz = end_z - oz

    length = math.sqrt(dx**2 + dy**2 + dz**2)
    if length < 1e-6:
        return envelope
    kx, ky, kz = dx / length, dy / length, dz / length

    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    one_minus_cos = 1.0 - cos_a

    def rot(pt: dict[str, Any]) -> dict[str, Any]:
        px = float(pt.get("x", 0.0))
        py = float(pt.get("y", 0.0))
        pz = float(pt.get("z", 0.0))
        vx, vy, vz = px - ox, py - oy, pz - oz
        dot = kx * vx + ky * vy + kz * vz
        cx = ky * vz - kz * vy
        cy = kz * vx - kx * vz
        cz = kx * vy - ky * vx
        rx = vx * cos_a + cx * sin_a + kx * dot * one_minus_cos + ox
        ry = vy * cos_a + cy * sin_a + ky * dot * one_minus_cos + oy
        rz = vz * cos_a + cz * sin_a + kz * dot * one_minus_cos + oz
        return {"x": round(rx, 2), "y": round(ry, 2), "z": round(rz, 2)}

    deflected_env = deepcopy(envelope)
    sections = deflected_env.get("sections")
    if isinstance(sections, list):
        for sec in sections:
            if isinstance(sec, dict) and "corners_3d" in sec:
                sec["corners_3d"] = [rot(c) for c in sec["corners_3d"] if isinstance(c, dict)]
    return deflected_env


def _append_envelope_lines(
    lines: list[tuple[Point3D, Point3D]],
    envelope: dict[str, Any],
    matrix: Matrix4,
) -> None:
    sections = envelope.get("sections")
    local_lines: list[tuple[Point3D, Point3D]] = []

    if isinstance(sections, list) and sections:
        section_loops: list[list[Point3D]] = []
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            corners_raw = sec.get("corners_3d")
            if isinstance(corners_raw, (list, tuple)) and len(corners_raw) >= 3:
                parsed_loop: list[Point3D] = []
                for pt in corners_raw:
                    if isinstance(pt, dict):
                        parsed_loop.append((
                            float(pt.get("x", 0.0)),
                            float(pt.get("y", 0.0)),
                            float(pt.get("z", 0.0)),
                        ))
                    elif isinstance(pt, (list, tuple)) and len(pt) >= 3:
                        parsed_loop.append((
                            float(pt[0]),
                            float(pt[1]),
                            float(pt[2]),
                        ))
                if len(parsed_loop) >= 3:
                    section_loops.append(parsed_loop)
            elif "x_bounds_mm" in sec and "z_bounds_mm" in sec:
                xb = sec["x_bounds_mm"]
                zb = sec["z_bounds_mm"]
                y = float(sec.get("span_y_mm", 0.0))
                if (
                    isinstance(xb, (list, tuple))
                    and len(xb) == 2
                    and isinstance(zb, (list, tuple))
                    and len(zb) == 2
                ):
                    loop = [
                        (float(xb[0]), y, float(zb[0])),
                        (float(xb[1]), y, float(zb[0])),
                        (float(xb[1]), y, float(zb[1])),
                        (float(xb[0]), y, float(zb[1])),
                    ]
                    section_loops.append(loop)
            elif "station_x_mm" in sec and "bounds" in sec:
                sx = float(sec.get("station_x_mm", 0.0))
                b = sec.get("bounds")
                if isinstance(b, dict):
                    ymin = float(b.get("ymin", 0.0))
                    ymax = float(b.get("ymax", 0.0))
                    zmin = float(b.get("zmin", 0.0))
                    zmax = float(b.get("zmax", 0.0))
                    loop = [
                        (sx, ymin, zmin),
                        (sx, ymax, zmin),
                        (sx, ymax, zmax),
                        (sx, ymin, zmax),
                    ]
                    section_loops.append(loop)

        # Section loops
        for loop in section_loops:
            n = len(loop)
            for i in range(n):
                local_lines.append((loop[i], loop[(i + 1) % n]))

        # Longitudinal connecting rails
        for i in range(len(section_loops) - 1):
            loop1 = section_loops[i]
            loop2 = section_loops[i + 1]
            m = min(len(loop1), len(loop2))
            for j in range(m):
                local_lines.append((loop1[j], loop2[j]))

    if not local_lines:
        size = envelope.get("size_mm")
        offset = envelope.get("offset_mm")
        if isinstance(size, dict):
            sx = float(size.get("x", 0.0))
            sy = float(size.get("y", 0.0))
            sz = float(size.get("z", 0.0))
            ox = float(offset.get("x", 0.0)) if isinstance(offset, dict) else 0.0
            oy = float(offset.get("y", 0.0)) if isinstance(offset, dict) else 0.0
            oz = float(offset.get("z", 0.0)) if isinstance(offset, dict) else 0.0

            shape = str(envelope.get("shape") or "box").lower()
            if sx > 0.0 and sy > 0.0 and sz > 0.0:
                hx, hy, hz = sx * 0.5, sy * 0.5, sz * 0.5
                if shape == "cylinder":
                    segments = 24
                    for x_pos in (ox - hx, ox + hx):
                        pts = [
                            (
                                x_pos,
                                oy + hy * math.cos(2.0 * math.pi * k / segments),
                                oz + hz * math.sin(2.0 * math.pi * k / segments),
                            )
                            for k in range(segments)
                        ]
                        for k in range(segments):
                            local_lines.append((pts[k], pts[(k + 1) % segments]))
                    for angle in (0.0, math.pi * 0.5, math.pi, math.pi * 1.5):
                        p_start = (ox - hx, oy + hy * math.cos(angle), oz + hz * math.sin(angle))
                        p_end = (ox + hx, oy + hy * math.cos(angle), oz + hz * math.sin(angle))
                        local_lines.append((p_start, p_end))
                elif shape == "sphere":
                    segments = 24
                    for k in range(segments):
                        a1 = 2.0 * math.pi * k / segments
                        a2 = 2.0 * math.pi * (k + 1) / segments
                        local_lines.append((
                            (ox + hx * math.cos(a1), oy + hy * math.sin(a1), oz),
                            (ox + hx * math.cos(a2), oy + hy * math.sin(a2), oz),
                        ))
                        local_lines.append((
                            (ox + hx * math.cos(a1), oy, oz + hz * math.sin(a1)),
                            (ox + hx * math.cos(a2), oy, oz + hz * math.sin(a2)),
                        ))
                        local_lines.append((
                            (ox, oy + hy * math.cos(a1), oz + hz * math.sin(a1)),
                            (ox, oy + hy * math.cos(a2), oz + hz * math.sin(a2)),
                        ))
                else:
                    p0 = (ox - hx, oy - hy, oz - hz)
                    p1 = (ox + hx, oy - hy, oz - hz)
                    p2 = (ox + hx, oy + hy, oz - hz)
                    p3 = (ox - hx, oy + hy, oz - hz)
                    p4 = (ox - hx, oy - hy, oz + hz)
                    p5 = (ox + hx, oy - hy, oz + hz)
                    p6 = (ox + hx, oy + hy, oz + hz)
                    p7 = (ox - hx, oy + hy, oz + hz)

                    local_lines.extend([(p0, p1), (p1, p2), (p2, p3), (p3, p0)])
                    local_lines.extend([(p4, p5), (p5, p6), (p6, p7), (p7, p4)])
                    local_lines.extend([(p0, p4), (p1, p5), (p2, p6), (p3, p7)])

    for start, end in local_lines:
        lines.append((
            transform_point(matrix, start),
            transform_point(matrix, end),
        ))


def _append_lifting_surface_tip_envelope_lines(
    lines: list[tuple[Point3D, Point3D]],
    source: dict[str, Any],
    matrix: Matrix4,
) -> None:
    try:
        from plugins.geometry.engine.lifting_surface_geometry import build_lifting_surface_geometry

        lofts = build_lifting_surface_geometry(source)
    except Exception:
        return

    comp_id = str(source.get("id") or "")
    tip_lofts = [
        loft
        for loft in lofts
        if loft.component_id != comp_id
        and (":winglet" in loft.component_id or ":tip-cap" in loft.component_id)
    ]

    for tip_loft in tip_lofts:
        if not tip_loft.sections:
            continue

        if ":winglet" in tip_loft.component_id:
            n_sec = len(tip_loft.sections)
            if n_sec <= 6:
                sampled_indices = list(range(n_sec))
            else:
                step = max(1, (n_sec - 1) // 5)
                sampled_indices = list(range(0, n_sec - 1, step))
                if (n_sec - 1) not in sampled_indices:
                    sampled_indices.append(n_sec - 1)

            quad_loops: list[list[Point3D]] = []
            for idx in sampled_indices:
                pts = tip_loft.sections[idx].points
                if not pts:
                    continue
                le = min(pts, key=lambda p: p[0])
                te = max(pts, key=lambda p: p[0])
                top_z = max(p[2] for p in pts)
                bot_z = min(p[2] for p in pts)

                p0 = (le[0], le[1], bot_z)
                p1 = (te[0], te[1], bot_z)
                p2 = (te[0], te[1], top_z)
                p3 = (le[0], le[1], top_z)
                quad_loops.append([p0, p1, p2, p3])

            local_lines: list[tuple[Point3D, Point3D]] = []
            for loop in quad_loops:
                for k in range(4):
                    local_lines.append((loop[k], loop[(k + 1) % 4]))
            for k in range(len(quad_loops) - 1):
                loop1 = quad_loops[k]
                loop2 = quad_loops[k + 1]
                for j in range(4):
                    local_lines.append((loop1[j], loop2[j]))

            for start, end in local_lines:
                lines.append((
                    transform_point(matrix, start),
                    transform_point(matrix, end),
                ))

        elif ":tip-cap" in tip_loft.component_id:
            all_pts = [p for sec in tip_loft.sections for p in sec.points]
            if not all_pts or not tip_loft.sections[0].points:
                continue

            y_junc = sum(p[1] for p in tip_loft.sections[0].points) / len(tip_loft.sections[0].points)
            y_outer = max((p[1] for p in all_pts), key=lambda y: abs(y - y_junc))
            tip_span = abs(y_outer - y_junc)
            if tip_span < 1e-3:
                continue

            span_dir = 1.0 if (y_outer - y_junc) >= 0 else -1.0
            n_stations = 3
            fractions = [i / (n_stations - 1) for i in range(n_stations)]

            quad_loops: list[list[Point3D]] = []
            for f in fractions:
                y_s = y_junc + span_dir * (f * tip_span)
                band_tol = max(tip_span * 0.15, 1.0)
                band = [p for p in all_pts if abs(p[1] - y_s) <= band_tol]
                if not band:
                    band = [min(all_pts, key=lambda p: abs(p[1] - y_s))]

                min_x = min(p[0] for p in band)
                max_x = max(p[0] for p in band)
                min_z = min(p[2] for p in band)
                max_z = max(p[2] for p in band)

                p0 = (min_x, y_s, min_z)
                p1 = (max_x, y_s, min_z)
                p2 = (max_x, y_s, max_z)
                p3 = (min_x, y_s, max_z)
                quad_loops.append([p0, p1, p2, p3])

            local_lines: list[tuple[Point3D, Point3D]] = []
            for loop in quad_loops:
                for k in range(4):
                    local_lines.append((loop[k], loop[(k + 1) % 4]))
            for k in range(len(quad_loops) - 1):
                loop1 = quad_loops[k]
                loop2 = quad_loops[k + 1]
                for j in range(4):
                    local_lines.append((loop1[j], loop2[j]))

            for start, end in local_lines:
                lines.append((
                    transform_point(matrix, start),
                    transform_point(matrix, end),
                ))
