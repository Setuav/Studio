from __future__ import annotations

import bisect
import math
from collections.abc import Callable
from copy import deepcopy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from setuav_studio.project import ProjectDocument

from .data import EnvelopeWireGeometry, GeometryData, LoftGeometry, Point3D, Section
from .envelope import GEOMETRY_COMPONENT_TYPES
from .fuselage_geometry import sample_profile
from .lifting_surface_geometry import build_lifting_surface_geometry
from .transforms import (
    Matrix4,
    derivation_matrix,
    identity_matrix,
    multiply_matrix,
    number_field,
    transform_matrix,
    transform_point,
)

GeometryProvider = Callable[[dict[str, Any], list[dict[str, Any]]], tuple[LoftGeometry, ...]]


def _attach_target(item: dict[str, Any]) -> str | None:
    """Return the component this component's transform is relative to."""
    target = item.get("attach_to")
    if isinstance(target, str) and target:
        return target
    return None


def build_project_geometry(
    project: ProjectDocument,
    providers: dict[str, GeometryProvider],
) -> GeometryData:
    items = _project_items(project)
    if items is None:
        return GeometryData()

    world_matrix = _WorldMatrixResolver(items)
    lofts: list[LoftGeometry] = []
    for item_id, item in items.items():
        controls = _child_control_surfaces(item, item_id, items)
        _append_component_geometry(
            lofts,
            item_id,
            item,
            controls,
            providers,
            world_matrix,
        )
    lofts.extend(_build_lifting_surface_root_stubs(items, providers, world_matrix))

    envelopes: list[EnvelopeWireGeometry] = []
    for item_id, item in items.items():
        env_geom = _build_component_envelope_geometry(item_id, item, world_matrix, items)
        if env_geom is not None:
            envelopes.append(env_geom)

    return GeometryData(tuple(lofts), tuple(envelopes))


def _project_items(project: ProjectDocument) -> dict[str, dict[str, Any]] | None:
    components = project.data.get("components")
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
            raise ValueError(f"Component attachment cycle at {item_id!r}")
        item = self.items.get(item_id)
        if item is None:
            return identity_matrix()

        target_id = _attach_target(item)
        target = (
            self(target_id, resolving | {item_id})
            if isinstance(target_id, str)
            else identity_matrix()
        )
        local = transform_matrix(item.get("transform"))
        result = multiply_matrix(target, local)
        self.cache[item_id] = result
        return result


def _mirrored_deflection(control: dict[str, Any]) -> float | None:
    """Deflection of a control surface's mirrored copy; None when it has none.

    Follows the control's Symmetry Mode as the aerodynamic model does: Auto deflects
    ailerons and elevons opposite and everything else alike.
    """
    mode = str(control.get("symmetry_mode") or "auto").lower()
    deflection = float(control.get("deflection", 0.0))
    if mode == "none":
        return None
    if mode in ("antisymmetric", "anti-symmetric"):
        return -deflection
    if mode == "symmetric":
        return deflection
    differential = str(control.get("type", "aileron")).lower() in ("aileron", "elevon")
    return -deflection if differential else deflection


def _mirrored_controls(controls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The control surfaces of a surface's mirrored copy, with their mirrored deflection."""
    mirrored: list[dict[str, Any]] = []
    for control in controls:
        deflection = _mirrored_deflection(control)
        if deflection is not None:
            mirrored.append({**deepcopy(control), "deflection": deflection})
    return mirrored


def _child_control_surfaces(
    item: dict[str, Any],
    item_id: str,
    items: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if item.get("type") != "org.setuav.core:lifting-surface" or not item_id:
        return []
    return [
        control
        for child in items.values()
        if (control := _child_control_surface(child, item_id)) is not None
    ]


def _child_control_surface(
    child: dict[str, Any],
    surface_id: str,
) -> dict[str, Any] | None:
    if (
        child.get("type") != "org.setuav.core:control-surface"
        or (_attach_target(child) or "") != surface_id
    ):
        return None
    parameters = child.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    control = deepcopy(geometry) if isinstance(geometry, dict) else {}
    if "id" in child:
        control["id"] = child["id"]
    if "name" in child:
        control["name"] = child["name"]
    return control


def _append_component_geometry(
    lofts: list[LoftGeometry],
    item_id: str,
    item: dict[str, Any],
    controls: list[dict[str, Any]],
    providers: dict[str, GeometryProvider],
    world_matrix: Callable[[str], Matrix4],
) -> None:
    component_type = item.get("type")
    provider = providers.get(component_type) if isinstance(component_type, str) else None
    if provider is None:
        return
    matrix = world_matrix(item_id)
    source_lofts = provider(item, controls)
    lofts.extend(_transform_loft(loft, matrix, item_id, item_id, item_id) for loft in source_lofts)
    if component_type == "org.setuav.core:lifting-surface" and _is_bilateral(item):
        _append_mirrored_geometry(
            lofts,
            item_id,
            item,
            controls,
            provider,
            world_matrix,
        )


def _is_bilateral(source: dict[str, Any]) -> bool:
    parameters = source.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    return geometry.get("mirror") is True


def _append_mirrored_geometry(
    lofts: list[LoftGeometry],
    item_id: str,
    item: dict[str, Any],
    controls: list[dict[str, Any]],
    provider: GeometryProvider,
    world_matrix: Callable[[str], Matrix4],
) -> None:
    target_id = _attach_target(item)
    target_matrix = world_matrix(target_id) if isinstance(target_id, str) else identity_matrix()
    local_matrix = transform_matrix(item.get("transform"))
    mirror = derivation_matrix({"type": "mirror", "plane": "XZ"})
    mirrored_matrix = multiply_matrix(
        target_matrix,
        multiply_matrix(mirror, local_matrix),
    )
    mirrored_lofts = provider(item, _mirrored_controls(controls))
    lofts.extend(
        _transform_loft(loft, mirrored_matrix, f"{item_id}:mirror", item_id, item_id)
        for loft in mirrored_lofts
    )


def _transform_loft(
    loft: LoftGeometry, matrix: Matrix4, component_id: str, source_id: str, item_id: str
) -> LoftGeometry:
    # The source's own lofts draw the placed item; a control surface's loft keeps
    # its own component.
    owner_id = item_id if loft.owner_id == source_id else loft.owner_id
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
        interpolation=loft.interpolation,
        station_spacing=loft.station_spacing,
        closed_ends=loft.closed_ends,
        owner_id=owner_id,
        feature_wire=loft.feature_wire,
    )


def _build_lifting_surface_root_stubs(
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
        sections = _fuselage_cross_sections(fuselage)
        if not sections:
            continue
        for item_id, item in items.items():
            if item.get("attach_to") != fuselage_id:
                continue
            wing = _lifting_surface_root_geometry(item, provider)
            if wing is None:
                continue
            root_section = wing
            matrices = [world_matrix_fn(item_id)]
            if _is_bilateral(item):
                matrices.append(_mirrored_root_matrix(item, world_matrix_fn))
            for matrix in matrices:
                stub = _build_root_stub(sections, fuselage_id, root_section, matrix)
                if stub is not None:
                    stubs.append(stub)
    return stubs


def _lifting_surface_root_geometry(
    item: dict[str, Any], provider: GeometryProvider
) -> Section | None:
    if item.get("type") != "org.setuav.core:lifting-surface":
        return None
    lofts = provider(item, [])
    if not lofts or not lofts[0].sections:
        return None
    return lofts[0].sections[0]


def _fuselage_items(items: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in items.values()
        if isinstance(item, dict) and item.get("type") == "org.setuav.core:fuselage"
    ]


def _mirrored_root_matrix(
    item: dict[str, Any],
    world_matrix_fn: Callable[[str], Matrix4],
) -> Matrix4:
    target_id = _attach_target(item)
    target_matrix = world_matrix_fn(target_id) if target_id else identity_matrix()
    local_matrix = transform_matrix(item.get("transform"))
    mirror = derivation_matrix({"type": "mirror", "plane": "XZ"})
    return multiply_matrix(target_matrix, multiply_matrix(mirror, local_matrix))


def _build_root_stub(
    sections: list[FuselageCrossSection],
    fuselage_id: str,
    root_section: Section,
    matrix: Matrix4,
) -> LoftGeometry | None:
    outer_points = tuple(transform_point(matrix, point) for point in root_section.points)
    inward = _inward_span_direction(matrix)
    inner_points, has_gap = _project_root_points(sections, outer_points, inward)
    if not has_gap:
        return None
    return LoftGeometry(
        component_id=fuselage_id,
        owner_id=fuselage_id,
        feature_wire="ends",
        sections=(Section(inner_points), Section(outer_points)),
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
    sections: list[FuselageCrossSection],
    outer_points: tuple[tuple[float, float, float], ...],
    inward: tuple[float, float, float],
) -> tuple[tuple[tuple[float, float, float], ...], bool]:
    inner_points: list[tuple[float, float, float]] = []
    has_gap = False
    for outer_point in outer_points:
        inner_point, point_has_gap = _project_point_to_fuselage(
            sections,
            outer_point,
            inward,
        )
        inner_points.append(inner_point)
        if point_has_gap:
            has_gap = True
    return tuple(inner_points), has_gap


FuselageCrossSection = tuple[float, float, float, float, float]
"""Section x, the outline's bounding-box centre y and z, and its half width and height."""


def _get_fuselage_cross_section_at_x(
    sections: list[FuselageCrossSection],
    x_target: float,
) -> tuple[float, float, float, float]:
    """Interpolate the centre and half sizes of x-sorted ``sections`` at ``x_target``."""
    if x_target <= sections[0][0]:
        return sections[0][1:]
    if x_target >= sections[-1][0]:
        return sections[-1][1:]
    upper_index = bisect.bisect_right([section[0] for section in sections], x_target)
    lower, upper = sections[upper_index - 1], sections[upper_index]
    t = (x_target - lower[0]) / max(upper[0] - lower[0], 1e-6)
    y, z, half_width, half_height = (
        low + t * (high - low) for low, high in zip(lower[1:], upper[1:], strict=True)
    )
    return y, z, half_width, half_height


def _fuselage_cross_sections(component: dict[str, Any]) -> list[FuselageCrossSection]:
    """Return the fuselage's section extents sorted by x."""
    parameters = component.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    geometry = parameters.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    segments = geometry.get("segments")
    segments = segments if isinstance(segments, list) else []
    result: list[FuselageCrossSection] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        for section in segment.get("sections", []):
            if isinstance(section, dict):
                result.append(_fuselage_cross_section(section))
    return sorted(result, key=lambda section: section[0])


def _fuselage_cross_section(section: dict[str, Any]) -> FuselageCrossSection:
    position = section.get("position")
    position = position if isinstance(position, dict) else {}
    profile = section.get("profile")
    profile = profile if isinstance(profile, dict) else {}
    outline = sample_profile(profile)
    ys = [point[0] for point in outline]
    zs = [point[1] for point in outline]
    return (
        number_field(position, "x", 0.0),
        number_field(position, "y", 0.0) + (max(ys) + min(ys)) * 0.5,
        number_field(position, "z", 0.0) + (max(zs) + min(zs)) * 0.5,
        max((max(ys) - min(ys)) * 0.5, 1e-4),
        max((max(zs) - min(zs)) * 0.5, 1e-4),
    )


def _project_point_to_fuselage(
    sections: list[FuselageCrossSection],
    pt: tuple[float, float, float],
    d_in: tuple[float, float, float],
) -> tuple[tuple[float, float, float], bool]:
    gx, gy, gz = pt
    dx, dy, dz = d_in
    y_c, z_c, r_y, r_z = _get_fuselage_cross_section_at_x(sections, gx)

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
    world_matrix: Callable[[str], Matrix4],
    items: dict[str, dict[str, Any]],
) -> EnvelopeWireGeometry | None:
    """Build the wireframe of the envelope stored on the component.

    Geometry envelopes are kept on the component by ``sync_component_envelope``;
    the wireframe draws exactly the envelope that mass properties are derived from.
    """
    component_type = item.get("type")
    if component_type not in GEOMETRY_COMPONENT_TYPES:
        return None
    envelope = item.get("envelope")
    if not isinstance(envelope, dict) or not envelope:
        return None

    target_id = _attach_target(item)
    target_source = items.get(str(target_id)) if target_id else None

    matrix = world_matrix(item_id)
    lines: list[tuple[Point3D, Point3D]] = []

    cs_deflection = 0.0
    cs_geometry: dict[str, Any] = {}
    if component_type == "org.setuav.core:control-surface":
        params = item.get("parameters")
        geom = params.get("geometry") if isinstance(params, dict) else {}
        if isinstance(geom, dict):
            cs_geometry = geom
            cs_deflection = float(geom.get("deflection", 0.0))

    env_to_draw = (
        _rotate_control_surface_envelope(envelope, cs_deflection)
        if component_type == "org.setuav.core:control-surface"
        else envelope
    )
    _append_envelope_lines(lines, env_to_draw, matrix)

    if component_type == "org.setuav.core:lifting-surface":
        _append_lifting_surface_tip_envelope_lines(lines, item, matrix)

    if component_type == "org.setuav.core:lifting-surface" and _is_bilateral(item):
        target_frame_id = _attach_target(item)
        target_matrix = (
            world_matrix(target_frame_id) if isinstance(target_frame_id, str) else identity_matrix()
        )
        local_matrix = transform_matrix(item.get("transform"))
        mirror = derivation_matrix({"type": "mirror", "plane": "XZ"})
        mirrored_matrix = multiply_matrix(
            target_matrix,
            multiply_matrix(mirror, local_matrix),
        )
        _append_envelope_lines(lines, envelope, mirrored_matrix)
        _append_lifting_surface_tip_envelope_lines(lines, item, mirrored_matrix)

    mirrored_deflection = _mirrored_deflection(cs_geometry)
    if (
        component_type == "org.setuav.core:control-surface"
        and target_source
        and _is_bilateral(target_source)
        and mirrored_deflection is not None
    ):
        outer_target_id = _attach_target(target_source)
        pp_matrix = (
            world_matrix(outer_target_id) if isinstance(outer_target_id, str) else identity_matrix()
        )
        target_local_matrix = transform_matrix(target_source.get("transform"))
        cs_local_matrix = transform_matrix(item.get("transform"))
        mirror = derivation_matrix({"type": "mirror", "plane": "XZ"})
        mirrored_matrix = multiply_matrix(
            pp_matrix,
            multiply_matrix(mirror, multiply_matrix(target_local_matrix, cs_local_matrix)),
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


def _append_envelope_lines(  # noqa: C901
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
                        parsed_loop.append(
                            (
                                float(pt.get("x", 0.0)),
                                float(pt.get("y", 0.0)),
                                float(pt.get("z", 0.0)),
                            )
                        )
                    elif isinstance(pt, (list, tuple)) and len(pt) >= 3:
                        parsed_loop.append(
                            (
                                float(pt[0]),
                                float(pt[1]),
                                float(pt[2]),
                            )
                        )
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
                    local_lines.extend(
                        _cylinder_wire_lines(
                            (ox, oy, oz), (hx, hy, hz), "xyz".index(str(envelope["axis"]))
                        )
                    )
                elif shape == "sphere":
                    segments = 24
                    for k in range(segments):
                        a1 = 2.0 * math.pi * k / segments
                        a2 = 2.0 * math.pi * (k + 1) / segments
                        local_lines.append(
                            (
                                (ox + hx * math.cos(a1), oy + hy * math.sin(a1), oz),
                                (ox + hx * math.cos(a2), oy + hy * math.sin(a2), oz),
                            )
                        )
                        local_lines.append(
                            (
                                (ox + hx * math.cos(a1), oy, oz + hz * math.sin(a1)),
                                (ox + hx * math.cos(a2), oy, oz + hz * math.sin(a2)),
                            )
                        )
                        local_lines.append(
                            (
                                (ox, oy + hy * math.cos(a1), oz + hz * math.sin(a1)),
                                (ox, oy + hy * math.cos(a2), oz + hz * math.sin(a2)),
                            )
                        )
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
        lines.append(
            (
                transform_point(matrix, start),
                transform_point(matrix, end),
            )
        )


def _append_lifting_surface_tip_envelope_lines(  # noqa: C901
    lines: list[tuple[Point3D, Point3D]],
    source: dict[str, Any],
    matrix: Matrix4,
) -> None:
    lofts = build_lifting_surface_geometry(source)
    comp_id = str(source["id"])
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
                lines.append(
                    (
                        transform_point(matrix, start),
                        transform_point(matrix, end),
                    )
                )

        elif ":tip-cap" in tip_loft.component_id:
            all_pts = [p for sec in tip_loft.sections for p in sec.points]
            if not all_pts or not tip_loft.sections[0].points:
                continue

            y_junc = sum(p[1] for p in tip_loft.sections[0].points) / len(
                tip_loft.sections[0].points
            )
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
                lines.append(
                    (
                        transform_point(matrix, start),
                        transform_point(matrix, end),
                    )
                )


def _cylinder_wire_lines(
    center: tuple[float, float, float],
    half_size: tuple[float, float, float],
    axis: int,
    segments: int = 24,
) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
    """Return the end rings and four rails of a cylinder along ``axis`` (0, 1 or 2)."""
    first, second = (i for i in range(3) if i != axis)

    def point(along: float, angle: float) -> tuple[float, float, float]:
        coords = list(center)
        coords[axis] += along
        coords[first] += half_size[first] * math.cos(angle)
        coords[second] += half_size[second] * math.sin(angle)
        return (coords[0], coords[1], coords[2])

    lines = []
    for along in (-half_size[axis], half_size[axis]):
        ring = [point(along, 2.0 * math.pi * k / segments) for k in range(segments)]
        lines.extend((ring[k], ring[(k + 1) % segments]) for k in range(segments))
    for angle in (0.0, math.pi * 0.5, math.pi, math.pi * 1.5):
        lines.append((point(-half_size[axis], angle), point(half_size[axis], angle)))
    return lines
