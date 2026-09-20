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


def build_universal_scope(  # noqa: C901
    project_data: dict[str, Any],
    api: Any | None = None,
    config_id: str | None = None,
) -> dict[str, Any]:
    """Build the universal evaluation scope containing resolved parameters, models, and extensions."""
    from setuav_studio.model.component import GenericComponent
    from setuav_studio.model.parameter import ParameterResolver

    resolver = ParameterResolver()
    raw_params = project_data.get("parameters", {}) if isinstance(project_data, dict) else {}
    resolved_params = resolver.resolve_all(raw_params) if isinstance(raw_params, dict) else {}

    scope: dict[str, Any] = {}

    # 1. Project Global Parameters & Constants
    for k, v in resolved_params.items():
        clean_k = k.replace("-", "_")
        scope[k] = v
        if clean_k != k:
            scope[clean_k] = v

    # 2. Materialized & Resolved Components
    components = project_data.get("components", []) if isinstance(project_data, dict) else []
    models_list: list[Any] = []
    total_mass = 0.0

    if isinstance(components, list):
        for comp in components:
            if not isinstance(comp, dict):
                continue
            resolved_comp = resolver.evaluate_component_parameters(comp, resolved_params)
            if api is not None and hasattr(api, "create_component_model"):
                model = api.create_component_model(resolved_comp)
            else:
                model = GenericComponent(resolved_comp)
            models_list.append(model)

        # Link child models (e.g. control surfaces, attached motors) to their parent models
        model_by_id = {getattr(m, "id", ""): m for m in models_list if getattr(m, "id", "")}
        for model in models_list:
            raw_data = getattr(model, "raw_data", {})
            parent_id = getattr(model, "parent_id", None) or (
                raw_data.get("attach_to") or raw_data.get("parent")
                if isinstance(raw_data, dict)
                else None
            )
            if parent_id and parent_id in model_by_id:
                parent_model = model_by_id[parent_id]
                if hasattr(model, "set_parent_model"):
                    model.set_parent_model(parent_model)
                if hasattr(parent_model, "add_child_model"):
                    parent_model.add_child_model(model)

        # Register models directly into evaluation scope (No ScopeProxy wrapper!)
        for model in models_list:
            raw_cid = str(getattr(model, "id", "") or "")
            if not raw_cid:
                continue
            clean_cid = raw_cid.replace("-", "_")
            scope[clean_cid] = model
            if raw_cid != clean_cid:
                scope[raw_cid] = model

            # Short child alias registration (e.g. aileron -> main_wing.aileron)
            if hasattr(model, "children") and isinstance(model.children, dict):
                for child_name, child_model in model.children.items():
                    child_clean = child_name.replace("-", "_")
                    if child_clean not in scope:
                        scope[child_clean] = child_model

            # Flat property aliases for backward compatibility (e.g. main_wing_planform_area)
            if hasattr(model, "get_exposed_properties"):
                for prop_name, prop_val in model.get_exposed_properties().items():
                    if isinstance(prop_val, (int, float, bool, str)):
                        scope[f"{clean_cid}_{prop_name}"] = prop_val

            total_mass += getattr(model, "mass", 0.0)

    # 3. Generic Plugin Extensions (e.g. Manufacturing, Propulsion, Structures, etc.)
    extensions = project_data.get("extensions", {})
    if isinstance(extensions, dict):
        for ext_key, ext_val in extensions.items():
            if not isinstance(ext_val, dict):
                continue
            clean_ext_key = str(ext_key).replace("-", "_")
            ext_dot = to_dot_dict(ext_val)
            scope[clean_ext_key] = ext_dot
            if ext_key != clean_ext_key:
                scope[ext_key] = ext_dot

            # Features under extension (e.g. manufacturing spars, ribs, covers)
            features = ext_val.get("features")
            if isinstance(features, dict):
                for fid, feat in features.items():
                    if not isinstance(feat, dict) or feat.get("deleted") is True:
                        continue
                    clean_fid = str(feat.get("id") or fid).replace("-", "_")
                    feat_dot = to_dot_dict(feat)
                    scope[clean_fid] = feat_dot
                    scope[f"{clean_ext_key}_{clean_fid}"] = feat_dot
                    ext_dot[clean_fid] = feat_dot
                    if fid != clean_fid:
                        scope[fid] = feat_dot
                        ext_dot[fid] = feat_dot

            # Configuration under extension
            cfg = ext_val.get("configuration")
            if isinstance(cfg, dict):
                cfg_id = str(cfg.get("id") or f"{clean_ext_key}_configuration").replace("-", "_")
                cfg_dot = to_dot_dict(cfg)
                scope[cfg_id] = cfg_dot
                scope[f"{clean_ext_key}_configuration"] = cfg_dot
                ext_dot[cfg_id] = cfg_dot

    # 4. Project level totals
    scope["total_mass"] = total_mass
    scope["mtow"] = resolved_params.get("mtow", total_mass)

    return scope


__all__ = [
    "DotDict",
    "build_universal_scope",
    "to_dot_dict",
]
