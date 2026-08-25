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
    project_data = getattr(project, "data", project) if project is not None else {}
    components = project_data.get("components") if isinstance(project_data, dict) else None
    if not isinstance(components, list):
        return GeometryData()

    items = {
        item["id"]: item
        for item in components
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    world_cache: dict[str, Matrix4] = {}

    def world_matrix(item_id: str, resolving: frozenset[str] = frozenset()) -> Matrix4:
        if item_id in world_cache:
            return world_cache[item_id]
        if item_id in resolving:
            raise ValueError(f"Component parent cycle at {item_id!r}")
        item = items.get(item_id)
        if item is None:
            return identity_matrix()

        parent_id = _frame_parent(item)
        parent = (
            world_matrix(parent_id, resolving | {item_id})
            if isinstance(parent_id, str)
            else identity_matrix()
        )
        local = transform_matrix(item.get("transform"))
        if item.get("kind") == "instance":
            source = items.get(item.get("source"))
            source_transform = (
                transform_matrix(source.get("transform"))
                if isinstance(source, dict)
                else identity_matrix()
            )
            derivation = derivation_matrix(item.get("derivation"))
            local = multiply_matrix(local, multiply_matrix(derivation, source_transform))
        result = multiply_matrix(parent, local)
        world_cache[item_id] = result
        return result

    lofts: list[LoftGeometry] = []
    for item_id, item in items.items():
        if not isinstance(item, dict):
            continue
        source = deepcopy(item)
        if item.get("kind") == "instance":
            candidate = items.get(item.get("source"))
            if not isinstance(candidate, dict):
                continue
            source = deepcopy(candidate)
            overrides = item.get("parameter_overrides")
            if isinstance(overrides, dict):
                parameters = source.get("parameters")
                if not isinstance(parameters, dict):
                    parameters = {}
                    source["parameters"] = parameters
                _merge(parameters, overrides)

            # Invert deflection on mirrored instances for anti-symmetric surfaces (aileron, elevon)
            derivation = item.get("derivation")
            if isinstance(derivation, dict) and derivation.get("type") == "mirror":
                plane = derivation.get("plane", "XZ")
                if plane in ("XZ", "1", None):
                    params = (
                        source.get("parameters")
                        if isinstance(source.get("parameters"), dict)
                        else {}
                    )
                    geom = (
                        params.get("geometry") if isinstance(params.get("geometry"), dict) else {}
                    )
                    cs_list = geom.get("control_surfaces")
                    if isinstance(cs_list, list):
                        for cs in cs_list:
                            if isinstance(cs, dict) and str(cs.get("type", "aileron")).lower() in (
                                "aileron",
                                "elevon",
                            ):
                                cs["deflection"] = -float(cs.get("deflection", 0.0))

        component_type = source.get("type")
        if component_type == "org.setuav.core:lifting-surface":
            # Collect child control surfaces attached to this lifting surface
            child_cs: list[dict[str, Any]] = []
            for child in items.values():
                if (
                    isinstance(child, dict)
                    and child.get("type") == "org.setuav.core:control-surface"
                    and (_frame_parent(child) or "") == item_id
                ):
                    child_params = (
                        child.get("parameters") if isinstance(child.get("parameters"), dict) else {}
                    )
                    child_geom = (
                        deepcopy(child_params.get("geometry", {}))
                        if isinstance(child_params.get("geometry"), dict)
                        else {}
                    )
                    child_geom.setdefault("tag", child.get("name") or child.get("id"))
                    child_cs.append(child_geom)
            if child_cs:
                params = source.setdefault("parameters", {})
                geom = params.setdefault("geometry", {})
                geom["control_surfaces"] = child_cs

        provider = providers.get(component_type) if isinstance(component_type, str) else None
        if provider is None:
            continue
        matrix = world_matrix(item_id)
        parent_id = _frame_parent(item)
        params = source.get("parameters") if isinstance(source.get("parameters"), dict) else {}
        geom = params.get("geometry") if isinstance(params.get("geometry"), dict) else {}

        for loft in provider(source):
            lofts.append(_transform_loft(loft, matrix, item_id))

        # Check if bilateral mirror is enabled on lifting surface
        if component_type == "org.setuav.core:lifting-surface" and (
            geom.get("mirror") is True or source.get("mirror") is True
        ):
            parent_mat = (
                world_matrix(parent_id) if isinstance(parent_id, str) else identity_matrix()
            )
            local_mat = transform_matrix(item.get("transform"))
            mirror_deriv = derivation_matrix({"type": "mirror", "plane": "XZ"})
            mirrored_world_mat = multiply_matrix(
                parent_mat, multiply_matrix(mirror_deriv, local_mat)
            )

            source_mirror = deepcopy(source)
            mirror_params = (
                source_mirror.get("parameters")
                if isinstance(source_mirror.get("parameters"), dict)
                else {}
            )
            mirror_geom = (
                mirror_params.get("geometry")
                if isinstance(mirror_params.get("geometry"), dict)
                else {}
            )
            cs_list = mirror_geom.get("control_surfaces")
            if isinstance(cs_list, list):
                for cs in cs_list:
                    if isinstance(cs, dict) and str(cs.get("type", "aileron")).lower() in (
                        "aileron",
                        "elevon",
                    ):
                        cs["deflection"] = -float(cs.get("deflection", 0.0))

            for loft in provider(source_mirror):
                lofts.append(_transform_loft(loft, mirrored_world_mat, f"{item_id}:mirror"))

    # Automatic wing-fuselage root stubs connecting wing root to fuselage skin
    lofts.extend(_build_wing_root_stubs(items, providers, world_matrix))
    return GeometryData(tuple(lofts))


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
    stubs: list[LoftGeometry] = []
    fuselage_items = [
        item
        for item in items.values()
        if isinstance(item, dict) and item.get("type") == "org.setuav.core:fuselage"
    ]
    if not fuselage_items:
        return stubs

    for fuse in fuselage_items:
        fuse_id = fuse.get("id")
        if not isinstance(fuse_id, str):
            continue
        fuse_colors = segment_colors()
        fuse_color = fuse_colors[0] if fuse_colors else (0.8, 0.8, 0.8, 1.0)

        for item_id, item in items.items():
            if not isinstance(item, dict):
                continue
            parent_id = _frame_parent(item)
            if parent_id != fuse_id:
                continue

            source = item
            if item.get("kind") == "instance":
                candidate = items.get(item.get("source"))
                if not isinstance(candidate, dict):
                    continue
                source = deepcopy(candidate)
                overrides = item.get("parameter_overrides")
                if isinstance(overrides, dict):
                    params = source.get("parameters")
                    if not isinstance(params, dict):
                        params = {}
                        source["parameters"] = params
                    _merge(params, overrides)

            if source.get("type") != "org.setuav.core:lifting-surface":
                continue

            ls_provider = providers.get("org.setuav.core:lifting-surface")
            if ls_provider is None:
                continue

            wing_lofts = ls_provider(source)
            if not wing_lofts or not wing_lofts[0].sections:
                continue

            # Root section in local coordinates of this lifting surface
            root_sec_local = wing_lofts[0].sections[0]
            mat = world_matrix_fn(item_id)
            outer_points = tuple(transform_point(mat, pt) for pt in root_sec_local.points)

            # Compute inward ray direction along span root normal
            p0 = transform_point(mat, (0.0, 0.0, 0.0))
            p1 = transform_point(mat, (0.0, -1.0, 0.0))
            d_vec = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
            l_len = math.sqrt(d_vec[0] ** 2 + d_vec[1] ** 2 + d_vec[2] ** 2)
            d_in = (
                d_vec[0] / max(l_len, 1e-6),
                d_vec[1] / max(l_len, 1e-6),
                d_vec[2] / max(l_len, 1e-6),
            )

            # Build matching inner points at the fuselage outer skin
            inner_points: list[tuple[float, float, float]] = []
            has_gap = False
            for p_out in outer_points:
                p_in, g_flag = _project_point_to_fuselage(fuse, p_out, d_in)
                inner_points.append(p_in)
                if g_flag:
                    has_gap = True

            if has_gap:
                stubs.append(
                    LoftGeometry(
                        component_id=fuse_id,
                        sections=(Section(tuple(inner_points)), Section(outer_points)),
                        color=fuse_color,
                        interpolation="linear",
                        station_spacing=10.0,
                        closed_ends=False,
                    )
                )

            # If bilateral mirror is enabled on lifting surface, also build mirrored root stub
            params = source.get("parameters") if isinstance(source.get("parameters"), dict) else {}
            geom = params.get("geometry") if isinstance(params.get("geometry"), dict) else {}
            if geom.get("mirror") is True or source.get("mirror") is True:
                parent_mat = world_matrix_fn(fuse_id)
                local_mat = transform_matrix(item.get("transform"))
                mirror_deriv = derivation_matrix({"type": "mirror", "plane": "XZ"})
                mirrored_world_mat = multiply_matrix(
                    parent_mat, multiply_matrix(mirror_deriv, local_mat)
                )
                mirror_outer_points = tuple(
                    transform_point(mirrored_world_mat, pt) for pt in root_sec_local.points
                )

                p0_m = transform_point(mirrored_world_mat, (0.0, 0.0, 0.0))
                p1_m = transform_point(mirrored_world_mat, (0.0, -1.0, 0.0))
                d_vec_m = (p1_m[0] - p0_m[0], p1_m[1] - p0_m[1], p1_m[2] - p0_m[2])
                l_len_m = math.sqrt(d_vec_m[0] ** 2 + d_vec_m[1] ** 2 + d_vec_m[2] ** 2)
                d_in_m = (
                    d_vec_m[0] / max(l_len_m, 1e-6),
                    d_vec_m[1] / max(l_len_m, 1e-6),
                    d_vec_m[2] / max(l_len_m, 1e-6),
                )

                mirror_inner_points: list[tuple[float, float, float]] = []
                mirror_has_gap = False
                for p_out in mirror_outer_points:
                    p_in, g_flag = _project_point_to_fuselage(fuse, p_out, d_in_m)
                    mirror_inner_points.append(p_in)
                    if g_flag:
                        mirror_has_gap = True

                if mirror_has_gap:
                    stubs.append(
                        LoftGeometry(
                            component_id=fuse_id,
                            sections=(
                                Section(tuple(mirror_inner_points)),
                                Section(mirror_outer_points),
                            ),
                            color=fuse_color,
                            interpolation="linear",
                            station_spacing=10.0,
                            closed_ends=False,
                        )
                    )

    return stubs


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
