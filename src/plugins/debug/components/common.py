"""Shared utilities, transforms, color parsing, and base editor for debug components."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from setuav_studio.ui.editor.component import BaseComponentEditor
from setuav_studio.ui.viewport import ViewportProtocol

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

DEBUG_LAYER = "debug"


def _parse_sequence_rgba(nums: list[float]) -> tuple[float, float, float, float]:
    if any(v > 1.0 for v in nums[:3]):
        r = min(1.0, max(0.0, nums[0] / 255.0))
        g = min(1.0, max(0.0, nums[1] / 255.0))
        b = min(1.0, max(0.0, nums[2] / 255.0))
        a = min(1.0, max(0.0, nums[3] / 255.0)) if len(nums) >= 4 else 1.0
    else:
        r = min(1.0, max(0.0, nums[0]))
        g = min(1.0, max(0.0, nums[1]))
        b = min(1.0, max(0.0, nums[2]))
        a = min(1.0, max(0.0, nums[3])) if len(nums) >= 4 else 1.0
    return (r, g, b, a)


def _parse_hex_rgba(text: str) -> tuple[float, float, float, float] | None:
    try:
        if len(text) == 7:
            return (
                int(text[1:3], 16) / 255.0,
                int(text[3:5], 16) / 255.0,
                int(text[5:7], 16) / 255.0,
                1.0,
            )
        if len(text) == 4:
            return (
                int(text[1] * 2, 16) / 255.0,
                int(text[2] * 2, 16) / 255.0,
                int(text[3] * 2, 16) / 255.0,
                1.0,
            )
        if len(text) == 9:
            return (
                int(text[1:3], 16) / 255.0,
                int(text[3:5], 16) / 255.0,
                int(text[5:7], 16) / 255.0,
                int(text[7:9], 16) / 255.0,
            )
    except ValueError:
        pass
    return None


def parse_color_rgba(
    val: Any, default: tuple[float, float, float, float] = (0.3, 0.6, 0.9, 1.0)
) -> tuple[float, float, float, float]:
    """Parse color value into an (r, g, b, a) tuple in 0.0 - 1.0 range."""
    if isinstance(val, (tuple, list)) and len(val) >= 3:
        try:
            return _parse_sequence_rgba([float(v) for v in val[:4]])
        except (ValueError, TypeError):
            return default

    if isinstance(val, str):
        text = val.strip()
        if not text:
            return default

        if text.startswith("#"):
            parsed_hex = _parse_hex_rgba(text)
            if parsed_hex is not None:
                return parsed_hex

        if text.lower().startswith("rgb"):
            left_paren = text.find("(")
            right_paren = text.rfind(")")
            if left_paren != -1 and right_paren != -1:
                text = text[left_paren + 1 : right_paren]

        clean = text.strip("()[]")
        parts = [p.strip() for p in clean.replace(";", ",").split(",") if p.strip()]
        if len(parts) < 3:
            parts = [p.strip() for p in clean.split() if p.strip()]
        if len(parts) >= 3:
            try:
                return _parse_sequence_rgba([float(p) for p in parts[:4]])
            except ValueError:
                pass

    return default


def rotate_vector(
    vec: tuple[float, float, float],
    rotation: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Rotate a 3D vector by (roll, pitch, yaw) Euler angles in degrees."""
    roll, pitch, yaw = rotation
    if abs(roll) < 1e-6 and abs(pitch) < 1e-6 and abs(yaw) < 1e-6:
        return vec
    r = math.radians(roll)
    p = math.radians(pitch)
    y_rad = math.radians(yaw)
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y_rad), math.sin(y_rad)
    x, y, z = vec
    rx = (cp * cy) * x + (cy * sp * sr - sy * cr) * y + (cy * sp * cr + sy * sr) * z
    ry = (cp * sy) * x + (sy * sp * sr + cy * cr) * y + (sy * sp * cr - cy * sr) * z
    rz = (-sp) * x + (cp * sr) * y + (cp * cr) * z
    return (rx, ry, rz)


def resolve_world_transform(
    comp_id: str,
    comps_by_id: dict[str, dict[str, Any]],
    resolving: frozenset[str] = frozenset(),
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Compute (world_position, world_rotation) traversing parent chain."""
    if comp_id in resolving:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    comp = comps_by_id.get(comp_id)
    if comp is None:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    raw_transform = comp.get("transform")
    transform_dict: dict[str, Any] = raw_transform if isinstance(raw_transform, dict) else {}
    raw_pos = transform_dict.get("position")
    pos_dict: dict[str, Any] = raw_pos if isinstance(raw_pos, dict) else {}
    raw_rot = transform_dict.get("rotation")
    rot_dict: dict[str, Any] = raw_rot if isinstance(raw_rot, dict) else {}

    lx = float(pos_dict.get("x", 0.0) or 0.0)
    ly = float(pos_dict.get("y", 0.0) or 0.0)
    lz = float(pos_dict.get("z", 0.0) or 0.0)

    l_roll = float(rot_dict.get("roll", rot_dict.get("x", 0.0)) or 0.0)
    l_pitch = float(rot_dict.get("pitch", rot_dict.get("y", 0.0)) or 0.0)
    l_yaw = float(rot_dict.get("yaw", rot_dict.get("z", 0.0)) or 0.0)

    parent_id = comp.get("parent") or comp.get("attach_to")
    if not parent_id or str(parent_id) not in comps_by_id:
        return (lx, ly, lz), (l_roll, l_pitch, l_yaw)

    p_pos, p_rot = resolve_world_transform(str(parent_id), comps_by_id, resolving | {comp_id})

    rx, ry, rz = rotate_vector((lx, ly, lz), p_rot)
    world_pos = (p_pos[0] + rx, p_pos[1] + ry, p_pos[2] + rz)
    world_rot = (p_rot[0] + l_roll, p_rot[1] + l_pitch, p_rot[2] + l_yaw)

    return world_pos, world_rot


_RENDERERS: dict[
    str,
    Callable[
        [
            ViewportProtocol,
            str,
            str,
            dict[str, Any],
            float,
            float,
            float,
            tuple[float, float, float],
            dict[str, Any] | None,
        ],
        None,
    ],
] = {}


def register_renderer(
    component_type: str,
    fn: Callable[
        [
            ViewportProtocol,
            str,
            str,
            dict[str, Any],
            float,
            float,
            float,
            tuple[float, float, float],
            dict[str, Any] | None,
        ],
        None,
    ],
) -> None:
    """Register a renderer function for a specific debug component type."""
    _RENDERERS[component_type] = fn


def update_component_in_viewport(
    viewport: ViewportProtocol,
    component: dict[str, Any],
    project: Any = None,
) -> None:
    """Update or add a single debug component in the 3D viewport."""
    if viewport is None:
        return
    comp_id = str(component.get("id") or "")
    if not comp_id:
        return
    name = str(component.get("name") or comp_id)
    raw_params = component.get("parameters")
    params: dict[str, Any] = dict(raw_params) if isinstance(raw_params, dict) else {}

    comps_by_id: dict[str, dict[str, Any]] = {}
    if project is not None and hasattr(project, "data") and isinstance(project.data, dict):
        comps = project.data.get("components", [])
        if isinstance(comps, list):
            comps_by_id = {
                str(c.get("id")): c for c in comps if isinstance(c, dict) and c.get("id")
            }
    if comp_id not in comps_by_id:
        comps_by_id[comp_id] = component

    world_pos, world_rot = resolve_world_transform(comp_id, comps_by_id)
    px, py, pz = world_pos
    envelope = component.get("envelope")
    ctype = str(component.get("type", ""))

    renderer = _RENDERERS.get(ctype)
    if renderer is not None:
        renderer(viewport, comp_id, name, params, px, py, pz, world_rot, envelope)


def sync_debug_components_to_viewport(viewport: ViewportProtocol, project: Any) -> None:
    """Synchronize all debug components in the project with the viewport."""
    if viewport is None:
        return
    if project is None or not hasattr(project, "data") or not isinstance(project.data, dict):
        viewport.clear(layer=DEBUG_LAYER)
        return

    comps = project.data.get("components", [])
    if not isinstance(comps, list):
        viewport.clear(layer=DEBUG_LAYER)
        return

    debug_components = [
        c
        for c in comps
        if isinstance(c, dict) and str(c.get("type", "")).startswith("org.setuav.debug:")
    ]

    active_ids = {str(c.get("id")) for c in debug_components}
    existing_ids = set(viewport.object_ids(layer=DEBUG_LAYER))

    for oid in existing_ids - active_ids:
        viewport.remove(oid)

    for comp in debug_components:
        update_component_in_viewport(viewport, comp, project)


class BaseDebugComponentEditor(BaseComponentEditor):
    """Base property editor for debug components with direct viewport updating."""

    def __init__(
        self,
        api: StudioAPI,
        component: Any,
        parameter_fields: Any = (),
        parent: Any = None,
    ) -> None:
        raw_comp: dict[str, Any] = (
            component.raw_data
            if hasattr(component, "raw_data") and isinstance(component.raw_data, dict)
            else component
        )
        super().__init__(api, raw_comp, parameter_fields=parameter_fields, parent=parent)

    def update_viewport(self) -> None:
        """Update this component's 3D representation directly in the viewport."""
        vp = getattr(self._api, "viewport", None)
        if vp is not None:
            update_component_in_viewport(vp, self._component, self._api.current_project)

    def _on_param_changed(self, key: str, value: Any) -> None:
        super()._on_param_changed(key, value)
        if (
            key in ("axis", "radius", "length", "width", "outer_radius", "height")
            and "envelope" in self._component
        ):
            vp = getattr(self._api, "viewport", None)
            if vp is not None:
                comp_id = str(self._component.get("id") or "")
                obj = vp.get_object(comp_id)
                if obj is not None and hasattr(obj, "compute_envelope"):
                    computed = obj.compute_envelope()
                    if computed is not None:
                        self._component["envelope"] = computed
                        self.update_viewport()


def generate_unique_identity(api: StudioAPI, base_id: str, base_name: str) -> tuple[str, str]:
    """Generate a collision-free ID and human-friendly display name."""
    project = api.current_project
    if project is None or not isinstance(project.data.get("components"), list):
        return f"{base_id}-1", f"{base_name} 1"
    existing_ids = {str(c.get("id")) for c in project.data["components"] if isinstance(c, dict)}
    existing_names = {str(c.get("name")) for c in project.data["components"] if isinstance(c, dict)}
    idx = 1
    while f"{base_id}-{idx}" in existing_ids or f"{base_name} {idx}" in existing_names:
        idx += 1
    return f"{base_id}-{idx}", f"{base_name} {idx}"


def add_debug_component(
    api: StudioAPI,
    factory_fn: Callable[[str, str], Any],
    base_id: str,
    base_name: str,
) -> Any | None:
    """Create and append a debug component into the active project with undo support."""
    project = api.current_project
    if project is None:
        window = getattr(api, "_window", None) or getattr(api, "main_window", None)
        if window is not None and hasattr(window, "new_untitled_project"):
            window.new_untitled_project()
            project = api.current_project
    if project is None or project.read_only:
        api.show_status("Cannot add component to read-only project", "warning")
        return None

    comp_id, name = generate_unique_identity(api, base_id, base_name)
    comp = factory_fn(comp_id, name)
    raw = comp.raw_data if hasattr(comp, "raw_data") and isinstance(comp.raw_data, dict) else comp

    def change() -> None:
        comps = project.data.setdefault("components", [])
        if isinstance(comps, list):
            comps.append(raw)

    api.edit_project(f"Add {name}", change)
    created = next(
        (
            item
            for item in project.data.get("components", [])
            if isinstance(item, dict) and item.get("id") == comp_id
        ),
        raw,
    )
    # Render component directly into viewport
    vp = getattr(api, "viewport", None)
    if vp is not None:
        update_component_in_viewport(vp, created, project)

    api.set_selection(created)
    api.show_status(f"Added {name}", "success", 3000)
    return created


def clear_debug_components(api: StudioAPI) -> None:
    """Remove all debug primitive components from the active project."""
    project = api.current_project
    if project is None or project.read_only:
        return
    comps = project.data.get("components", [])
    if not isinstance(comps, list):
        return
    debug_ids = {
        c.get("id")
        for c in comps
        if isinstance(c, dict) and str(c.get("type", "")).startswith("org.setuav.debug:")
    }
    if not debug_ids:
        api.show_status("No debug components to clear", "info", 2000)
        return

    def change() -> None:
        project.data["components"] = [
            c
            for c in comps
            if isinstance(c, dict) and not str(c.get("type", "")).startswith("org.setuav.debug:")
        ]

    count = len(debug_ids)
    api.edit_project("Clear Debug Primitives", change)
    # Clear viewport layer directly
    vp = getattr(api, "viewport", None)
    if vp is not None:
        vp.clear(layer=DEBUG_LAYER)

    api.set_selection(None)
    api.show_status(f"Removed {count} debug component(s)", "info", 3000)
