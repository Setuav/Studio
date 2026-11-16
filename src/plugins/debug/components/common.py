"""Shared utilities, transforms, color parsing, and base editor for debug components."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from setuav_studio.ui.editor.component import BaseComponentEditor
from setuav_studio.ui.viewport import ViewportProtocol
from setuav_studio.utilities.transform import (
    resolve_world_transform,
    rotate_vector,
)

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

__all__ = [
    "DEBUG_LAYER",
    "BaseDebugComponentEditor",
    "add_debug_component",
    "clear_debug_components",
    "compute_debug_envelope",
    "generate_unique_identity",
    "no_envelope",
    "parse_color_rgba",
    "register_envelope",
    "register_renderer",
    "resolve_world_transform",
    "rotate_vector",
    "sync_debug_components_to_viewport",
    "sync_debug_envelope",
    "sync_debug_envelopes",
    "update_component_in_viewport",
]

DEBUG_LAYER = "debug"


def parse_color_rgba(text: str) -> tuple[float, float, float, float]:
    """Parse a ``#RRGGBB`` color into an opaque (r, g, b, a) tuple in the 0-1 range."""
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", text):
        raise ValueError(f"Color {text!r} is not a #RRGGBB hex color.")
    return (
        int(text[1:3], 16) / 255.0,
        int(text[3:5], 16) / 255.0,
        int(text[5:7], 16) / 255.0,
        1.0,
    )


def _comp_as_dict(item: Any) -> dict[str, Any] | None:
    """Return dictionary representation of a component whether it is a dict or a model object."""
    if isinstance(item, dict):
        return item
    raw = getattr(item, "raw_data", None)
    if isinstance(raw, dict):
        return raw
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        res = to_dict()
        if isinstance(res, dict):
            return res
    return None


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


EnvelopeFunction = Callable[[dict[str, Any]], dict[str, Any] | None]

_ENVELOPES: dict[str, EnvelopeFunction] = {}


def register_envelope(component_type: str, fn: EnvelopeFunction) -> None:
    """Register the function deriving a debug component's envelope from its parameters.

    The envelope is expressed in the component's own frame.
    """
    _ENVELOPES[component_type] = fn


def no_envelope(_params: dict[str, Any]) -> None:
    """Envelope function of a primitive that has no volume, and therefore no envelope."""
    return None


def compute_debug_envelope(component: dict[str, Any]) -> dict[str, Any] | None:
    """Return the exact envelope of a debug primitive, or None when it has no volume."""
    ctype = str(component.get("type") or "")
    fn = _ENVELOPES.get(ctype)
    if fn is None:
        raise ValueError(f"No envelope function registered for component type {ctype!r}")
    params = component.get("parameters")
    return fn(dict(params) if isinstance(params, dict) else {})


def sync_debug_envelope(component: dict[str, Any]) -> bool:
    """Store the exact envelope on a debug primitive.

    Returns True if the stored envelope changed. A primitive without volume keeps
    whatever envelope it has.
    """
    envelope = compute_debug_envelope(component)
    if envelope is None or component.get("envelope") == envelope:
        return False
    component["envelope"] = envelope
    return True


def sync_debug_envelopes(project: Any) -> int:
    """Store the exact envelope on every debug primitive of the project.

    Returns the count of components whose envelope changed.
    """
    from setuav_studio.project.document import ProjectDocument

    project_data = project.data if isinstance(project, ProjectDocument) else project
    if not isinstance(project_data, dict):
        return 0
    comps = project_data.get("components")
    if not isinstance(comps, list):
        return 0
    return sum(
        1
        for comp in comps
        if isinstance(comp, dict)
        and str(comp.get("type") or "") in _ENVELOPES
        and sync_debug_envelope(comp)
    )


def update_component_in_viewport(
    viewport: ViewportProtocol,
    component: dict[str, Any],
    project: Any = None,
) -> None:
    """Update or add a single debug component in the 3D viewport."""
    comp_dict = _comp_as_dict(component)
    if comp_dict is None or viewport is None:
        return
    comp_id = str(comp_dict.get("id") or "")
    if not comp_id:
        return
    name = str(comp_dict.get("name") or comp_id)
    raw_params = comp_dict.get("parameters")
    params: dict[str, Any] = dict(raw_params) if isinstance(raw_params, dict) else {}

    from setuav_studio.project.document import ProjectDocument

    comps_by_id: dict[str, dict[str, Any]] = {}
    project_data = project.data if isinstance(project, ProjectDocument) else project
    if isinstance(project_data, dict):
        comps = project_data.get("components", [])
        if isinstance(comps, list):
            comps_by_id = {
                str(d["id"]): d
                for c in comps
                for d in [_comp_as_dict(c)]
                if d is not None and d.get("id")
            }
    if comp_id not in comps_by_id:
        comps_by_id[comp_id] = comp_dict

    world_pos, world_rot = resolve_world_transform(comp_id, comps_by_id)
    px, py, pz = world_pos
    envelope = comp_dict.get("envelope")
    ctype = str(comp_dict.get("type", ""))

    renderer = _RENDERERS.get(ctype)
    if renderer is not None:
        renderer(viewport, comp_id, name, params, px, py, pz, world_rot, envelope)

    # Re-render any child components attached to this component
    if comps_by_id:
        for other_id, other_comp in comps_by_id.items():
            if other_id == comp_id:
                continue
            parent = other_comp.get("parent")
            if parent and str(parent) == comp_id:
                update_component_in_viewport(viewport, other_comp, project)


def sync_debug_components_to_viewport(viewport: ViewportProtocol, project: Any) -> None:
    """Synchronize all debug components in the project with the viewport."""
    if viewport is None:
        return
    from setuav_studio.project.document import ProjectDocument

    project_data = project.data if isinstance(project, ProjectDocument) else project
    if not isinstance(project_data, dict):
        viewport.clear(layer=DEBUG_LAYER)
        return

    comps = project_data.get("components", [])
    if not isinstance(comps, list):
        viewport.clear(layer=DEBUG_LAYER)
        return

    debug_components: list[dict[str, Any]] = []
    for c in comps:
        d = _comp_as_dict(c)
        if d is not None and (
            str(d.get("type", "")).startswith("org.setuav.debug:")
            or str(d.get("type", "")) in _RENDERERS
        ):
            debug_components.append(d)

    active_ids = {str(c.get("id")) for c in debug_components}
    existing_ids = set(viewport.object_ids(layer=DEBUG_LAYER))

    for oid in existing_ids - active_ids:
        viewport.remove(oid)

    for comp in debug_components:
        update_component_in_viewport(viewport, comp, project)


class BaseDebugComponentEditor(BaseComponentEditor):
    """Base property editor for debug components with direct viewport updating and parent support."""

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

    def _create_custom_sections(self) -> None:
        layout = self._create_section("Parent", "fa6s.sitemap")
        self.parent_table = self._property_table(
            [
                ("parent", "Parent"),
            ]
        )
        layout.addWidget(self.parent_table)

    def _load_custom_data(self) -> None:
        table = getattr(self, "parent_table", None)
        if table is None:
            return
        options = self._get_parent_options()
        curr_parent = str(self._component.get("parent") or "")
        self._set_property_combo(
            table,
            "parent",
            curr_parent,
            options,
            self._on_parent_changed,
        )

    def _get_parent_options(self) -> list[tuple[str, str]]:
        options: list[tuple[str, str]] = [("", "None (World)")]
        project = self._api.project
        if project is None:
            return options

        self_id = str(self._component.get("id") or "")
        comps = project.data.get("components", [])
        if not isinstance(comps, list):
            return options

        comps_by_id = {
            str(d["id"]): d
            for c in comps
            for d in [_comp_as_dict(c)]
            if d is not None and d.get("id")
        }

        for c in comps:
            d = _comp_as_dict(c)
            if d is None:
                continue
            cid = str(d.get("id") or "")
            ctype = str(d.get("type") or "")
            if not cid or cid == self_id:
                continue
            if not (ctype in _RENDERERS or ctype.startswith("org.setuav.debug:")):
                continue

            # Prevent cyclic hierarchy: check if self_id is an ancestor of cid
            curr: str | None = cid
            is_cyclic = False
            visited: set[str] = set()
            while curr:
                if curr == self_id or curr in visited:
                    is_cyclic = True
                    break
                visited.add(curr)
                parent_comp = comps_by_id.get(curr)
                if not parent_comp:
                    break
                p = parent_comp.get("parent")
                curr = str(p) if p else None

            if not is_cyclic:
                cname = str(d.get("name") or cid)
                options.append((cid, cname))

        return options

    def _on_parent_changed(self, new_parent: str) -> None:
        if self._loading:
            return
        clean_parent = new_parent.strip() or None
        old_parent = self._component.get("parent")
        if old_parent == clean_parent:
            return

        self._api.reparent_component(
            self._component,
            clean_parent,
            preserve_world_transform=True,
        )
        self._committed_parent = clean_parent or ""
        self.update_viewport()

    def update_viewport(self) -> None:
        """Update this component's 3D representation directly in the viewport."""
        vp = self._api.viewport
        if vp is not None:
            update_component_in_viewport(vp, self._component, self._api.project)


def generate_unique_identity(api: StudioAPI, base_id: str, base_name: str) -> tuple[str, str]:
    """Generate a collision-free ID and human-friendly display name."""
    project = api.project
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
    project = api.project
    if project is None or project.read_only:
        api.show_status("Cannot add component to read-only project", "warning")
        return None

    comp_id, name = generate_unique_identity(api, base_id, base_name)
    comp = factory_fn(comp_id, name)
    raw = comp.raw_data if hasattr(comp, "raw_data") and isinstance(comp.raw_data, dict) else comp
    sync_debug_envelope(raw)

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
    vp = api.viewport
    if vp is not None:
        update_component_in_viewport(vp, created, project)

    api.set_selection(created)
    api.show_status(f"Added {name}", "success", 3000)
    return created


def clear_debug_components(api: StudioAPI) -> None:
    """Remove all debug primitive components from the active project."""
    project = api.project
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
    vp = api.viewport
    if vp is not None:
        vp.clear(layer=DEBUG_LAYER)

    api.set_selection(None)
    api.show_status(f"Removed {count} debug component(s)", "info", 3000)
