"""Universal mass, center-of-gravity, and inertia tensor aggregation for aircraft components."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from setuav_studio.model.mass import (
    ComponentMassProperties,
    InertiaTensor,
    MassProperties,
    Vector3,
)
from setuav_studio.utilities.transform import (
    Matrix3,
    euler_to_matrix,
    resolve_world_transform,
    rotate_vector,
    transpose_matrix,
)

Matrix3x3 = tuple[
    tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]
]


def _matmul(left: Matrix3 | Matrix3x3, right: Matrix3 | Matrix3x3) -> Matrix3x3:
    return (
        (
            sum(left[0][k] * right[k][0] for k in range(3)),
            sum(left[0][k] * right[k][1] for k in range(3)),
            sum(left[0][k] * right[k][2] for k in range(3)),
        ),
        (
            sum(left[1][k] * right[k][0] for k in range(3)),
            sum(left[1][k] * right[k][1] for k in range(3)),
            sum(left[1][k] * right[k][2] for k in range(3)),
        ),
        (
            sum(left[2][k] * right[k][0] for k in range(3)),
            sum(left[2][k] * right[k][1] for k in range(3)),
            sum(left[2][k] * right[k][2] for k in range(3)),
        ),
    )


def _parallel_axis(mass_kg: float, offset_m: Vector3) -> Matrix3x3:
    dx, dy, dz = offset_m
    return (
        (mass_kg * (dy * dy + dz * dz), -mass_kg * dx * dy, -mass_kg * dx * dz),
        (-mass_kg * dx * dy, mass_kg * (dx * dx + dz * dz), -mass_kg * dy * dz),
        (-mass_kg * dx * dz, -mass_kg * dy * dz, mass_kg * (dx * dx + dy * dy)),
    )


def _add_matrix(left: Matrix3x3, right: Matrix3x3) -> Matrix3x3:
    return (
        (left[0][0] + right[0][0], left[0][1] + right[0][1], left[0][2] + right[0][2]),
        (left[1][0] + right[1][0], left[1][1] + right[1][1], left[1][2] + right[1][2]),
        (left[2][0] + right[2][0], left[2][1] + right[2][1], left[2][2] + right[2][2]),
    )


def _number(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def resolve_component_local_cg(component: dict[str, Any]) -> tuple[float, float, float]:
    """Resolve component local CG offset in mm relative to its coordinate origin.

    Derives automatically from physical envelope centroid unless an explicit override
    or local_cg_mm is declared.
    """
    # 1. Direct explicit local CG declaration
    declared_cg = component.get("local_cg_mm")
    if isinstance(declared_cg, dict):
        return (
            _number(declared_cg.get("x")),
            _number(declared_cg.get("y")),
            _number(declared_cg.get("z")),
        )

    # 2. Envelope centroid fallback (geometric centroid)
    envelope = component.get("envelope")
    if isinstance(envelope, dict):
        offset = envelope.get("offset_mm")
        if isinstance(offset, dict):
            return (
                _number(offset.get("x")),
                _number(offset.get("y")),
                _number(offset.get("z")),
            )

    return (0.0, 0.0, 0.0)


def resolve_component_local_inertia(
    component: dict[str, Any],
    mass_kg: float,
) -> InertiaTensor:
    """Resolve local inertia tensor in kg·m².

    Derives automatically from envelope unit_inertia * mass_kg unless explicitly declared.
    """
    # 1. Direct explicit inertia
    declared = component.get("inertia_kg_m2")
    if isinstance(declared, dict):
        return InertiaTensor.from_dict(declared)

    # 2. Envelope unit inertia scaled by mass
    envelope = component.get("envelope")
    if isinstance(envelope, dict) and mass_kg > 0.0:
        u_inertia = envelope.get("unit_inertia")
        if isinstance(u_inertia, dict):
            return InertiaTensor(
                ixx=mass_kg * _number(u_inertia.get("ixx")),
                iyy=mass_kg * _number(u_inertia.get("iyy")),
                izz=mass_kg * _number(u_inertia.get("izz")),
                ixy=mass_kg * _number(u_inertia.get("ixy")),
                ixz=mass_kg * _number(u_inertia.get("ixz")),
                iyz=mass_kg * _number(u_inertia.get("iyz")),
            )

    return InertiaTensor()


def _mat_vec_mul(matrix: Matrix3 | Matrix3x3, vec: Vector3) -> Vector3:
    return (
        matrix[0][0] * vec[0] + matrix[0][1] * vec[1] + matrix[0][2] * vec[2],
        matrix[1][0] * vec[0] + matrix[1][1] * vec[1] + matrix[1][2] * vec[2],
        matrix[2][0] * vec[0] + matrix[2][1] * vec[1] + matrix[2][2] * vec[2],
    )


def get_all_components(project_or_components: Any) -> list[dict[str, Any]]:
    from setuav_studio.project.document import ProjectDocument

    if isinstance(project_or_components, ProjectDocument):
        raw_components = project_or_components.data.get("components", [])
    elif isinstance(project_or_components, dict):
        raw_components = project_or_components.get("components", [])
        if not isinstance(raw_components, list):
            raw_components = list(project_or_components.values())
    elif isinstance(project_or_components, (list, tuple)):
        raw_components = list(project_or_components)
    else:
        raw_components = []
    return [c for c in raw_components if isinstance(c, dict) and c.get("id")]


def get_component_children(
    comp_id: str,
    project_or_components: Any,
    recursive: bool = True,
) -> list[dict[str, Any]]:
    """Return all direct or recursive child components belonging to comp_id in the hierarchy."""
    all_comps = get_all_components(project_or_components)
    direct_children = [c for c in all_comps if str(c.get("parent") or "") == comp_id]
    if not recursive:
        return direct_children

    result: list[dict[str, Any]] = []
    queue = list(direct_children)
    visited = {comp_id}
    while queue:
        child = queue.pop(0)
        c_id = str(child.get("id") or "")
        if c_id and c_id not in visited:
            visited.add(c_id)
            result.append(child)
            sub_children = [c for c in all_comps if str(c.get("parent") or "") == c_id]
            queue.extend(sub_children)
    return result


def get_component_intrinsic_mass_g(component: dict[str, Any]) -> float:
    """Return component intrinsic mass in grams, ignoring child components."""
    if component.get("has_mass") is False:
        return 0.0
    mass_g = _number(component.get("mass", 0.0))
    return max(0.0, mass_g)


def resolve_component_intrinsic_mass_properties(
    comp_or_id: str | dict[str, Any],
    project_or_components: Any,
) -> ComponentMassProperties:
    """Resolve intrinsic mass properties for a single component in local and body frames."""
    all_comps = get_all_components(project_or_components)
    by_id = {str(c["id"]): c for c in all_comps}
    comp = by_id.get(comp_or_id) if isinstance(comp_or_id, str) else comp_or_id
    comp_id = str(comp.get("id") or "") if isinstance(comp, dict) else ""
    if not comp or not comp_id:
        return ComponentMassProperties(
            component_id="",
            component_name="",
            mass_kg=0.0,
            cg_local_m=(0.0, 0.0, 0.0),
            cg_body_m=(0.0, 0.0, 0.0),
            inertia_local_kg_m2=InertiaTensor(),
            source="declared",
            quality="valid",
            component_type="",
        )

    effective = _effective_component(comp, by_id)
    comp_type = str(effective.get("type") or "").lower()
    mass_g = get_component_intrinsic_mass_g(effective)
    mass_kg = mass_g / 1000.0

    cg_local_mm = resolve_component_local_cg(effective)
    cg_local_m: Vector3 = (
        cg_local_mm[0] / 1000.0,
        cg_local_mm[1] / 1000.0,
        cg_local_mm[2] / 1000.0,
    )
    inertia_local = resolve_component_local_inertia(effective, mass_kg)

    world_pos_mm, world_rot_deg = resolve_world_transform(comp_id, by_id)
    rx, ry, rz = rotate_vector(cg_local_mm, world_rot_deg)
    cg_body_mm = (world_pos_mm[0] + rx, world_pos_mm[1] + ry, world_pos_mm[2] + rz)

    if is_mirrored_component(effective, by_id):
        cg_body_mm = (cg_body_mm[0], 0.0, cg_body_mm[2])

    cg_body_m: Vector3 = (
        cg_body_mm[0] / 1000.0,
        cg_body_mm[1] / 1000.0,
        cg_body_mm[2] / 1000.0,
    )

    return ComponentMassProperties(
        component_id=comp_id,
        component_name=str(effective.get("name") or comp_id),
        mass_kg=mass_kg,
        cg_local_m=cg_local_m,
        cg_body_m=cg_body_m,
        inertia_local_kg_m2=inertia_local,
        source="declared",
        quality="valid",
        component_type=comp_type,
    )


def resolve_component_aggregate_mass_properties(
    comp_id: str,
    project_or_components: Any,
) -> ComponentMassProperties:
    """Aggregate mass, center of gravity, and inertia tensor for comp_id and all its child components."""
    all_comps = get_all_components(project_or_components)
    by_id = {str(c["id"]): c for c in all_comps}
    root_comp = by_id.get(comp_id)
    if root_comp is None:
        return ComponentMassProperties(
            component_id=comp_id,
            component_name=comp_id,
            mass_kg=0.0,
            cg_local_m=(0.0, 0.0, 0.0),
            cg_body_m=(0.0, 0.0, 0.0),
            inertia_local_kg_m2=InertiaTensor(),
            source="aggregated",
            quality="valid",
            component_type="",
        )

    descendants = get_component_children(comp_id, all_comps, recursive=True)
    if not descendants:
        intrinsic = resolve_component_intrinsic_mass_properties(root_comp, all_comps)
        return ComponentMassProperties(
            component_id=comp_id,
            component_name=intrinsic.component_name,
            mass_kg=round(intrinsic.mass_kg, 6),
            cg_local_m=intrinsic.cg_local_m,
            cg_body_m=intrinsic.cg_body_m,
            inertia_local_kg_m2=intrinsic.inertia_local_kg_m2,
            source="declared",
            quality=intrinsic.quality,
            component_type=intrinsic.component_type,
        )

    # Subtree includes root component itself plus all descendants
    subtree = [root_comp, *descendants]
    items: list[ComponentMassProperties] = []
    for c in subtree:
        c_item = resolve_component_intrinsic_mass_properties(c, all_comps)
        if c_item.mass_kg > 0.0:
            items.append(c_item)

    comp_name = str(root_comp.get("name") or comp_id)
    comp_type = str(root_comp.get("type") or "").lower()

    world_pos_mm, world_rot_deg = resolve_world_transform(comp_id, by_id)
    world_pos_m: Vector3 = (
        world_pos_mm[0] / 1000.0,
        world_pos_mm[1] / 1000.0,
        world_pos_mm[2] / 1000.0,
    )
    r_root = euler_to_matrix(*world_rot_deg)
    r_root_inv = transpose_matrix(r_root)

    total_mass_kg = sum(it.mass_kg for it in items)
    if total_mass_kg <= 0.0:
        cg_local_mm = resolve_component_local_cg(root_comp)
        cg_local_m: Vector3 = (
            cg_local_mm[0] / 1000.0,
            cg_local_mm[1] / 1000.0,
            cg_local_mm[2] / 1000.0,
        )
        rx, ry, rz = rotate_vector(cg_local_mm, world_rot_deg)
        cg_body_m: Vector3 = (
            world_pos_m[0] + rx / 1000.0,
            world_pos_m[1] + ry / 1000.0,
            world_pos_m[2] + rz / 1000.0,
        )
        return ComponentMassProperties(
            component_id=comp_id,
            component_name=comp_name,
            mass_kg=0.0,
            cg_local_m=cg_local_m,
            cg_body_m=cg_body_m,
            inertia_local_kg_m2=InertiaTensor(),
            source="aggregated",
            quality="valid",
            component_type=comp_type,
        )

    # 1. Body CG
    total_cg_body_m = cast(
        Vector3,
        tuple(
            sum(it.mass_kg * it.cg_body_m[axis] for it in items) / total_mass_kg
            for axis in range(3)
        ),
    )

    # 2. Local CG in root component's coordinate frame
    delta_world_m = cast(
        Vector3,
        tuple(total_cg_body_m[i] - world_pos_m[i] for i in range(3)),
    )
    total_cg_local_m = _mat_vec_mul(r_root_inv, delta_world_m)

    # 3. Total inertia tensor about total_cg_body_m in world frame
    zero_mat: Matrix3x3 = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    total_inertia_world = zero_mat

    for it in items:
        _, item_world_rot_deg = resolve_world_transform(it.component_id, by_id)
        r_item = euler_to_matrix(*item_world_rot_deg)
        r_item_t = transpose_matrix(r_item)

        local_mat = cast(Matrix3x3, it.inertia_local_kg_m2.as_matrix())
        body_mat = _matmul(_matmul(r_item, local_mat), r_item_t)

        offset_m = cast(
            Vector3,
            tuple(it.cg_body_m[i] - total_cg_body_m[i] for i in range(3)),
        )
        parallel_mat = _parallel_axis(it.mass_kg, offset_m)
        total_inertia_world = _add_matrix(total_inertia_world, _add_matrix(body_mat, parallel_mat))

    # Transform total inertia from world frame into root component's local frame
    total_inertia_local = _matmul(_matmul(r_root_inv, total_inertia_world), r_root)

    return ComponentMassProperties(
        component_id=comp_id,
        component_name=comp_name,
        mass_kg=round(total_mass_kg, 6),
        cg_local_m=cast(
            Vector3,
            (
                round(total_cg_local_m[0], 6),
                round(total_cg_local_m[1], 6),
                round(total_cg_local_m[2], 6),
            ),
        ),
        cg_body_m=cast(
            Vector3,
            (
                round(total_cg_body_m[0], 6),
                round(total_cg_body_m[1], 6),
                round(total_cg_body_m[2], 6),
            ),
        ),
        inertia_local_kg_m2=InertiaTensor.from_matrix(total_inertia_local),
        source="aggregated",
        quality="valid",
        component_type=comp_type,
    )


def resolve_aircraft_mass_properties(
    project_or_components: Any,
) -> MassProperties:
    """Aggregate total aircraft mass, center of gravity, and 3D inertia tensor in body frame.

    All components with intrinsic mass are aggregated directly in aircraft body frame without
    requiring hardcoded component type or ID exceptions. Result masses are in kg, CG in meters,
    and inertia in kg·m².
    """
    components = get_all_components(project_or_components)
    by_id: dict[str, dict[str, Any]] = {str(c["id"]): c for c in components}

    result_items: list[ComponentMassProperties] = []

    for comp in components:
        if comp.get("has_mass") is False:
            continue

        item = resolve_component_intrinsic_mass_properties(comp, components)
        if item.mass_kg > 0.0:
            result_items.append(item)

    if not result_items:
        return MassProperties(
            mass_kg=0.0,
            cg_body_m=(0.0, 0.0, 0.0),
            inertia_cg_kg_m2=InertiaTensor(),
        )

    total_mass_kg = sum(item.mass_kg for item in result_items)
    if total_mass_kg <= 0.0:
        return MassProperties(
            mass_kg=0.0,
            cg_body_m=(0.0, 0.0, 0.0),
            inertia_cg_kg_m2=InertiaTensor(),
        )

    total_cg_m = cast(
        Vector3,
        tuple(
            sum(item.mass_kg * item.cg_body_m[axis] for item in result_items) / total_mass_kg
            for axis in range(3)
        ),
    )

    zero_mat: Matrix3x3 = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    total_inertia = zero_mat

    for item in result_items:
        _, world_rot_deg = resolve_world_transform(item.component_id, by_id)
        r_mat = euler_to_matrix(*world_rot_deg)
        r_mat_t = transpose_matrix(r_mat)

        local_mat = cast(Matrix3x3, item.inertia_local_kg_m2.as_matrix())
        body_mat = _matmul(_matmul(r_mat, local_mat), r_mat_t)

        offset_m = cast(
            Vector3,
            tuple(item.cg_body_m[i] - total_cg_m[i] for i in range(3)),
        )
        parallel_mat = _parallel_axis(item.mass_kg, offset_m)
        total_inertia = _add_matrix(total_inertia, _add_matrix(body_mat, parallel_mat))

    return MassProperties(
        mass_kg=round(total_mass_kg, 6),
        cg_body_m=cast(
            Vector3,
            (round(total_cg_m[0], 6), round(total_cg_m[1], 6), round(total_cg_m[2], 6)),
        ),
        inertia_cg_kg_m2=InertiaTensor.from_matrix(total_inertia),
    )


def is_mirrored_component(
    component: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
) -> bool:
    """Return whether the component is mirrored across the body XZ plane.

    A component is mirrored by its own geometry; a control surface follows the
    lifting surface it is parented to.
    """
    if _geometry_mirror(component):
        return True
    if component.get("type") != "org.setuav.core:control-surface":
        return False
    parent = by_id.get(str(component.get("parent") or ""))
    return parent is not None and _geometry_mirror(_effective_component(parent, by_id))


def _geometry_mirror(component: dict[str, Any]) -> bool:
    parameters = component.get("parameters")
    geometry = parameters.get("geometry") if isinstance(parameters, dict) else None
    return isinstance(geometry, dict) and bool(geometry.get("mirror"))


def _effective_component(
    component: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if component.get("kind") != "instance":
        return deepcopy(component)
    source_id = str(component.get("source") or "")
    source = by_id.get(source_id)
    if source is None:
        return deepcopy(component)
    effective = deepcopy(source)
    for key in ("id", "name", "kind", "source", "parent", "derivation"):
        if key in component:
            effective[key] = deepcopy(component[key])
    if "mass" in component:
        effective["mass"] = component["mass"]
    overrides = component.get("parameter_overrides")
    if isinstance(overrides, dict):
        parameters = effective.setdefault("parameters", {})
        if isinstance(parameters, dict):
            parameters.update(overrides)
    return effective
