"""Visual 3D primitives generator for Center of Gravity (CG) markers in Viewport.

Implements clean, minimalist CAD-style CG markers (Option A):
- Crisp RGB coordinate axis crosshairs (X: Red, Y: Green, Z: Blue)
- Compact central marker point in bright aviation gold
- Aircraft-level CG highlighted by a subtle horizontal target ring
- Mirrored components (e.g. wings) centered on the Y=0 symmetry plane with a faint tie-line
"""

from __future__ import annotations

from typing import Any

from setuav_studio.ui.viewport.primitives import (
    BoxPrimitive,
    LineSegmentsPrimitive,
    Point3D,
    RingPrimitive,
    VisualPrimitive,
)
from setuav_studio.utilities.mass_balance import (
    resolve_component_aggregate_mass_properties,
    resolve_component_local_cg,
)
from setuav_studio.utilities.transform import resolve_world_transform, rotate_vector

# Visual styles for clean CAD CG markers
_X_AXIS_COLOR = (0.95, 0.25, 0.25, 1.0)  # Red - Longitudinal / Roll axis
_Y_AXIS_COLOR = (0.25, 0.85, 0.35, 1.0)  # Green - Lateral / Pitch axis
_Z_AXIS_COLOR = (0.25, 0.55, 0.95, 1.0)  # Blue - Vertical / Yaw axis
_GOLD_COLOR = (1.0, 0.82, 0.08, 1.0)  # Aviation Gold / Amber
_FAINT_GOLD_COLOR = (1.0, 0.82, 0.08, 0.30)  # Semi-transparent for mirror tie-lines


def build_component_cg_primitives(
    component_id: str,
    project_or_components: Any,
) -> list[VisualPrimitive]:
    """Generate minimalist 3D visual primitives representing the Center of Gravity for a component.

    Option A style:
    - RGB coordinate crosshair (15-30 mm proportional)
    - Small 3.5 mm gold center point
    - No heavy gimbal rings or obscuring boxes
    - Mirrored components centered at Y=0 with a faint connecting line to half-wings
    """
    if project_or_components is None or not component_id:
        return []

    from setuav_studio.project.document import ProjectDocument

    # 1. Resolve component dictionary
    comp: dict[str, Any] | None = None
    if isinstance(project_or_components, ProjectDocument):
        comp = project_or_components.get_component(component_id)
    elif isinstance(project_or_components, dict):
        components = project_or_components.get("components", [])
        if isinstance(components, list):
            comp = next(
                (c for c in components if isinstance(c, dict) and c.get("id") == component_id), None
            )
        else:
            comp = project_or_components.get(component_id)
    elif isinstance(project_or_components, (list, tuple)):
        comp = next(
            (
                c
                for c in project_or_components
                if isinstance(c, dict) and c.get("id") == component_id
            ),
            None,
        )

    if comp is None:
        return []

    # 2. Local CG and world transform (aggregating children if this is an assembly)
    agg = resolve_component_aggregate_mass_properties(component_id, project_or_components)
    if agg.mass_kg > 0.0:
        cg_world: Point3D = (
            agg.cg_body_m[0] * 1000.0,
            agg.cg_body_m[1] * 1000.0,
            agg.cg_body_m[2] * 1000.0,
        )
    else:
        local_cg_mm = resolve_component_local_cg(comp)
        world_pos_mm, world_rot_deg = resolve_world_transform(comp, project_or_components)
        rx, ry, rz = rotate_vector(local_cg_mm, world_rot_deg)
        cg_world = (world_pos_mm[0] + rx, world_pos_mm[1] + ry, world_pos_mm[2] + rz)

    # 3. Determine clean crosshair length proportional to component scale
    char_len = 0.0
    envelope = comp.get("envelope")
    if isinstance(envelope, dict):
        size = envelope.get("size_mm")
        if isinstance(size, dict):
            char_len = max(
                float(size.get("x", 0.0) or 0.0),
                float(size.get("y", 0.0) or 0.0),
                float(size.get("z", 0.0) or 0.0),
            )
    cross_len = max(18.0, min(40.0, char_len * 0.05)) if char_len > 0.0 else 24.0

    # 4. Handle mirror symmetry
    is_mirror = bool(comp.get("parameters", {}).get("geometry", {}).get("mirror"))

    primitives: list[VisualPrimitive] = []

    if is_mirror:
        # Effective combined CG sits strictly on the aircraft symmetry plane (Y=0)
        center_cg: Point3D = (cg_world[0], 0.0, cg_world[2])

        # If semi-wing has a non-zero Y offset, draw a faint tie line and subtle wing dots
        y_offset = abs(cg_world[1])
        if y_offset > 1.0:
            left_semi: Point3D = (cg_world[0], -y_offset, cg_world[2])
            right_semi: Point3D = (cg_world[0], y_offset, cg_world[2])
            primitives.append(
                LineSegmentsPrimitive(lines=((left_semi, right_semi),), color=_FAINT_GOLD_COLOR)
            )
            # Subtle semi-wing markers
            for semi in (left_semi, right_semi):
                primitives.append(
                    BoxPrimitive(
                        center=semi,
                        size=(2.5, 2.5, 2.5),
                        color=_FAINT_GOLD_COLOR,
                        solid=True,
                        wireframe=False,
                    )
                )

        main_center = center_cg
    else:
        main_center = cg_world

    cx, cy, cz = main_center

    # 5. Crisp RGB 3D crosshairs
    axis_x = (((cx - cross_len, cy, cz), (cx + cross_len, cy, cz)),)
    axis_y = (((cx, cy - cross_len, cz), (cx, cy + cross_len, cz)),)
    axis_z = (((cx, cy, cz - cross_len), (cx, cy, cz + cross_len)),)

    primitives.append(LineSegmentsPrimitive(lines=axis_x, color=_X_AXIS_COLOR))
    primitives.append(LineSegmentsPrimitive(lines=axis_y, color=_Y_AXIS_COLOR))
    primitives.append(LineSegmentsPrimitive(lines=axis_z, color=_Z_AXIS_COLOR))

    # 6. Central point dot
    primitives.append(
        BoxPrimitive(
            center=main_center,
            size=(3.5, 3.5, 3.5),
            color=_GOLD_COLOR,
            solid=True,
            wireframe=False,
        )
    )

    return primitives


def build_aircraft_cg_primitives(
    project_or_components: Any,
    cross_len: float = 32.0,
    ring_radius: float = 16.0,
) -> list[VisualPrimitive]:
    """Generate minimalist 3D visual primitives representing the aggregate aircraft Center of Gravity.

    Option A style:
    - RGB crosshairs (32 mm)
    - Single horizontal reticle ring (16 mm) in aviation gold
    - Central gold point dot (5 mm)
    """
    from setuav_studio.utilities.mass_balance import resolve_aircraft_mass_properties

    mass_props = resolve_aircraft_mass_properties(project_or_components)
    if mass_props.mass_kg <= 0.0:
        return []

    # Convert from meters to mm
    cg_x_mm = mass_props.cg_body_m[0] * 1000.0
    cg_y_mm = mass_props.cg_body_m[1] * 1000.0
    cg_z_mm = mass_props.cg_body_m[2] * 1000.0
    center: Point3D = (cg_x_mm, cg_y_mm, cg_z_mm)
    cx, cy, cz = center

    primitives: list[VisualPrimitive] = []

    # 1. Horizontal target ring in the XY plane
    primitives.append(
        RingPrimitive(
            center=center,
            normal=(0.0, 0.0, 1.0),
            radius=ring_radius,
            color=_GOLD_COLOR,
            segments=36,
        )
    )

    # 2. RGB 3D crosshairs
    axis_x = (((cx - cross_len, cy, cz), (cx + cross_len, cy, cz)),)
    axis_y = (((cx, cy - cross_len, cz), (cx, cy + cross_len, cz)),)
    axis_z = (((cx, cy, cz - cross_len), (cx, cy, cz + cross_len)),)

    primitives.append(LineSegmentsPrimitive(lines=axis_x, color=_X_AXIS_COLOR))
    primitives.append(LineSegmentsPrimitive(lines=axis_y, color=_Y_AXIS_COLOR))
    primitives.append(LineSegmentsPrimitive(lines=axis_z, color=_Z_AXIS_COLOR))

    # 3. Central gold point marker
    primitives.append(
        BoxPrimitive(
            center=center,
            size=(5.0, 5.0, 5.0),
            color=_GOLD_COLOR,
            solid=True,
            wireframe=False,
        )
    )

    return primitives
