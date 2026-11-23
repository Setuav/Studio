"""Universal Evaluation Scope and Expression Context Builder for Setuav Studio.

Constructs the symbol dictionary used by the expression evaluation engine,
exposing component domain models, parameters, and plugin extensions.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DotDict(dict):
    """Dictionary supporting dot-notation attribute access for nested keys."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        if name in self:
            return self[name]
        clean = name.replace("-", "_").lower()
        hyphen = name.replace("_", "-").lower()
        if clean in self:
            return self[clean]
        if hyphen in self:
            return self[hyphen]
        for k, v in self.items():
            if str(k).replace("-", "_").lower() == clean:
                return v
        pos = self.get("position")
        if isinstance(pos, dict) and clean in pos:
            return pos[clean]
        geom = self.get("geometry")
        if isinstance(geom, dict) and clean in geom:
            return geom[clean]
        params = self.get("parameters")
        if isinstance(params, dict):
            if clean in params:
                return params[clean]
            pgeom = params.get("geometry")
            if isinstance(pgeom, dict) and clean in pgeom:
                return pgeom[clean]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute or key '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __getitem__(self, key: Any) -> Any:
        try:
            return super().__getitem__(key)
        except KeyError:
            if isinstance(key, str):
                hyphen = key.replace("_", "-")
                if hyphen in self:
                    return super().__getitem__(hyphen)
                clean = key.replace("-", "_").lower()
                for k, v in self.items():
                    if str(k).replace("-", "_").lower() == clean:
                        return v
            raise


def to_dot_dict(val: Any) -> Any:
    """Recursively convert dictionaries and lists to DotDict."""
    if isinstance(val, dict) and not isinstance(val, DotDict):
        return DotDict({k: to_dot_dict(v) for k, v in val.items()})
    if isinstance(val, (list, tuple)):
        return [to_dot_dict(x) for x in val]
    return val


def build_project_base_scope(
    project_data: dict[str, Any] | Any,
    api: Any | None = None,
) -> dict[str, Any]:
    """Build the non-parameter project scope (components, extensions, features, mass totals)."""
    from setuav_studio.model.symbol import build_component_models
    from setuav_studio.project.document import ProjectDocument
    from setuav_studio.utilities.mass_balance import resolve_aircraft_total_mass_g

    raw_data = project_data.data if isinstance(project_data, ProjectDocument) else project_data
    p_dict: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}

    scope: dict[str, Any] = {}

    # 1. Materialized Components (reading stored evaluated values directly)
    components = p_dict.get("components", [])
    models_list = build_component_models(components, api)
    for model in models_list:
        raw_cid = model.id
        if not raw_cid:
            continue
        clean_cid = raw_cid.replace("-", "_")
        scope[clean_cid] = model
        if raw_cid != clean_cid:
            scope[raw_cid] = model

        # Short child names (e.g. aileron -> main_wing.aileron)
        for child_name, child_model in model.children.items():
            child_clean = child_name.replace("-", "_")
            if child_clean not in scope:
                scope[child_clean] = child_model

        # Flat property names (e.g. main_wing_planform_area)
        for prop_name, prop_val in model.get_exposed_properties().items():
            if isinstance(prop_val, (int, float, bool, str)):
                scope[f"{clean_cid}_{prop_name}"] = prop_val

    # 2. Generic Plugin Extensions (e.g. Propulsion, Structures, etc.)
    extensions = p_dict.get("extensions", {})
    if isinstance(extensions, dict):
        for ext_key, ext_val in extensions.items():
            if not isinstance(ext_val, dict):
                continue
            clean_ext_key = str(ext_key).replace("-", "_")
            ext_dot = to_dot_dict(ext_val)
            scope[clean_ext_key] = ext_dot
            if ext_key != clean_ext_key:
                scope[ext_key] = ext_dot

            # Configuration under extension
            cfg = ext_val.get("configuration")
            if isinstance(cfg, dict):
                cfg_id = str(cfg.get("id") or f"{clean_ext_key}_configuration").replace("-", "_")
                cfg_dot = to_dot_dict(cfg)
                scope[cfg_id] = cfg_dot
                scope[f"{clean_ext_key}_configuration"] = cfg_dot
                ext_dot[cfg_id] = cfg_dot

    # 3. Plugin features stored on components (e.g. structural skins and ribs)
    for _component_id, feature in extension_features(components):
        feature_id = str(feature["id"])
        feature_dot = to_dot_dict(feature["parameters"])
        scope[feature_id.replace("-", "_")] = feature_dot
        scope[feature_id] = feature_dot

    # 4. Project level mass totals (single source of truth from mass_balance)
    total_mass = resolve_aircraft_total_mass_g(p_dict)
    scope["total_mass"] = total_mass
    scope["mtow"] = total_mass

    return scope


def build_universal_scope_with_diagnostics(
    project_data: dict[str, Any] | Any,
    api: Any | None = None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Build the universal evaluation scope and return any global-parameter diagnostics."""
    from setuav_studio.model.parameter import ParameterResolver
    from setuav_studio.project.document import ProjectDocument

    raw_data = project_data.data if isinstance(project_data, ProjectDocument) else project_data
    p_dict: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}

    scope = build_project_base_scope(p_dict, api=api)

    resolver = ParameterResolver()
    raw_params = p_dict.get("parameters", {})
    if isinstance(raw_params, dict):
        resolution = resolver.resolve_all(raw_params, base_scope=scope)
        resolved_params = resolution.values
        diagnostics = resolution.diagnostics
    else:
        resolved_params = {}
        diagnostics = []

    for k, v in resolved_params.items():
        clean_k = k.replace("-", "_")
        scope[k] = v
        if clean_k != k:
            scope[clean_k] = v

    return scope, diagnostics


def build_universal_scope(
    project_data: dict[str, Any] | Any,
    api: Any | None = None,
) -> dict[str, Any]:
    """Build the universal evaluation scope containing resolved parameters, models, and extensions."""
    scope, _ = build_universal_scope_with_diagnostics(project_data, api=api)
    return scope


def extension_features(components: Any) -> list[tuple[str, dict[str, Any]]]:
    """Plugin features stored on components, as ``(component_id, feature)`` pairs.

    A plugin keeps them in ``component["extensions"][<namespace>]["features"]``, a list
    of mappings with an ``id`` and their ``parameters``.
    """
    found: list[tuple[str, dict[str, Any]]] = []
    for component in components if isinstance(components, list) else []:
        extensions = component.get("extensions") if isinstance(component, dict) else None
        if not isinstance(extensions, dict):
            continue
        for data in extensions.values():
            features = data.get("features") if isinstance(data, dict) else None
            for feature in features if isinstance(features, list) else []:
                if (
                    isinstance(feature, dict)
                    and feature.get("id")
                    and isinstance(feature.get("parameters"), dict)
                ):
                    found.append((str(component["id"]), feature))
    return found


__all__ = [
    "DotDict",
    "build_project_base_scope",
    "build_universal_scope",
    "build_universal_scope_with_diagnostics",
    "extension_features",
    "to_dot_dict",
]
