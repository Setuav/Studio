"""Universal Scope Proxy and Scope Context Builder for Setuav Studio.

Provides transparent dotted attribute and index access across JSON dictionaries,
typed component domain models, lists, and plugin extensions, enabling seamless
expression evaluation conforming directly to the underlying JSON hierarchy and
user-friendly shortcuts.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ScopeProxy:
    """Transparent proxy wrapping dictionaries, lists, or domain models.

    Enables:
    - Hierarchical dotted access mirroring JSON: ``main_wing.parameters.geometry.span``
    - Ergonomic shortcuts: ``main_wing.span``, ``main_wing.position.x``, ``main_wing.x``
    - Section/profile indexing: ``main_wing.section_1.x``, ``main_wing.sections[1].position.x``
    - Child component access: ``main_wing.aileron.chord``
    - Automatic hyphen-to-underscore normalization: ``main-wing`` <-> ``main_wing``
    """

    __slots__ = ("_path", "_target")

    def __init__(self, target: Any, path: str = "") -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_path", path)

    @classmethod
    def wrap(cls, val: Any, path: str = "") -> Any:
        """Wrap containers in ScopeProxy while returning numeric/string primitives directly."""
        if isinstance(val, (int, float, bool, str)) or val is None:
            return val
        if isinstance(val, ScopeProxy):
            return val
        return cls(val, path)

    @property
    def __class__(self) -> Any:
        return self._target.__class__

    def unwrap(self) -> Any:
        """Return the underlying unwrapped object or dictionary."""
        return self._target

    def __getattr__(self, name: str) -> Any:  # noqa: C901
        # Ignore dunder methods to avoid interfering with Python runtime protocols
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)

        target = self._target
        clean_name = name.lower()
        hyphen_name = name.replace("_", "-").lower()

        # 1. Direct attribute on wrapped object (e.g. typed Component properties)
        if hasattr(target, name):
            val = getattr(target, name)
            if not callable(val):
                return ScopeProxy.wrap(val, f"{self._path}.{name}")
            return val

        # 2. Check child components (e.g. main_wing.aileron)
        children = getattr(target, "children", None)
        if isinstance(children, dict):
            if clean_name in children:
                return ScopeProxy.wrap(children[clean_name], f"{self._path}.{name}")
            if hyphen_name in children:
                return ScopeProxy.wrap(children[hyphen_name], f"{self._path}.{name}")
            for ck, cv in children.items():
                if ck.lower() == clean_name or ck.lower().replace("-", "_") == clean_name:
                    return ScopeProxy.wrap(cv, f"{self._path}.{name}")

        # 3. Check exposed domain properties (e.g. planform_area, wingspan, mac)
        if hasattr(target, "get_exposed_properties") and callable(target.get_exposed_properties):
            try:
                exposed = target.get_exposed_properties()
                if isinstance(exposed, dict):
                    if name in exposed:
                        return ScopeProxy.wrap(exposed[name], f"{self._path}.{name}")
                    if clean_name in exposed:
                        return ScopeProxy.wrap(exposed[clean_name], f"{self._path}.{name}")
                    if hyphen_name in exposed:
                        return ScopeProxy.wrap(exposed[hyphen_name], f"{self._path}.{name}")
            except Exception:
                pass

        # 4. Dictionary inspection (raw_data of Component or direct dict)
        d = getattr(target, "raw_data", None)
        if not isinstance(d, dict) and isinstance(target, dict):
            d = target

        if isinstance(d, dict):
            # Direct key in dictionary
            if name in d:
                return ScopeProxy.wrap(d[name], f"{self._path}.{name}")
            if hyphen_name in d:
                return ScopeProxy.wrap(d[hyphen_name], f"{self._path}.{name}")
            for k, v in d.items():
                if k.lower() == clean_name or k.lower().replace("-", "_") == clean_name:
                    return ScopeProxy.wrap(v, f"{self._path}.{name}")

            # Smart Shortcuts (1-A): Search inside standard containers
            # A) parameters
            params = d.get("parameters")
            if isinstance(params, dict):
                if name in params:
                    return ScopeProxy.wrap(params[name], f"{self._path}.{name}")
                if hyphen_name in params:
                    return ScopeProxy.wrap(params[hyphen_name], f"{self._path}.{name}")
                for k, v in params.items():
                    if k.lower() == clean_name or k.lower().replace("-", "_") == clean_name:
                        return ScopeProxy.wrap(v, f"{self._path}.{name}")

                # Nested parameters.geometry
                geom = params.get("geometry")
                if isinstance(geom, dict):
                    if name in geom:
                        return ScopeProxy.wrap(geom[name], f"{self._path}.{name}")
                    if hyphen_name in geom:
                        return ScopeProxy.wrap(geom[hyphen_name], f"{self._path}.{name}")
                    for k, v in geom.items():
                        if k.lower() == clean_name or k.lower().replace("-", "_") == clean_name:
                            return ScopeProxy.wrap(v, f"{self._path}.{name}")

            # B) transform (position / rotation) or direct position / rotation
            pos = d.get("position")
            if not isinstance(pos, dict) and isinstance(d.get("transform"), dict):
                pos = d["transform"].get("position")
            if isinstance(pos, dict):
                if name in pos:
                    return ScopeProxy.wrap(pos[name], f"{self._path}.{name}")
                if clean_name in pos:
                    return ScopeProxy.wrap(pos[clean_name], f"{self._path}.{name}")

            rot = d.get("rotation")
            if not isinstance(rot, dict) and isinstance(d.get("transform"), dict):
                rot = d["transform"].get("rotation")
            if isinstance(rot, dict):
                if name in rot:
                    return ScopeProxy.wrap(rot[name], f"{self._path}.{name}")
                if clean_name in rot:
                    return ScopeProxy.wrap(rot[clean_name], f"{self._path}.{name}")

            # C) Generic features / configuration (e.g. extension features)
            features = d.get("features")
            if isinstance(features, dict):
                if name in features:
                    return ScopeProxy.wrap(features[name], f"{self._path}.{name}")
                if clean_name in features:
                    return ScopeProxy.wrap(features[clean_name], f"{self._path}.{name}")
                if hyphen_name in features:
                    return ScopeProxy.wrap(features[hyphen_name], f"{self._path}.{name}")

            cfg = d.get("configuration")
            if isinstance(cfg, dict):
                if name in cfg:
                    return ScopeProxy.wrap(cfg[name], f"{self._path}.{name}")
                if clean_name in cfg:
                    return ScopeProxy.wrap(cfg[clean_name], f"{self._path}.{name}")
                if hyphen_name in cfg:
                    return ScopeProxy.wrap(cfg[hyphen_name], f"{self._path}.{name}")

        # 5. Section / Profile list aliases on components
        if clean_name in ("sections", "profiles"):
            if hasattr(target, "sections"):
                return ScopeProxy.wrap(target.sections, f"{self._path}.{name}")
            if hasattr(target, "profiles"):
                return ScopeProxy.wrap(target.profiles, f"{self._path}.{name}")
            if isinstance(d, dict):
                profs = (
                    d.get("parameters", {}).get("geometry", {}).get("profiles")
                    or d.get("parameters", {}).get("geometry", {}).get("sections")
                    or d.get("geometry", {}).get("profiles")
                    or d.get("geometry", {}).get("sections")
                    or d.get("sections")
                    or d.get("profiles")
                )
                if profs is not None:
                    return ScopeProxy.wrap(profs, f"{self._path}.{name}")

        # 6. Dynamic station / profile / item indexing (e.g. section_0, profile_1)
        if name.startswith("section_") or name.startswith("profile_") or name.startswith("item_"):
            try:
                idx = int(name.split("_")[-1])
                secs = getattr(target, "sections", None)
                if secs is not None and 0 <= idx < len(secs):
                    return ScopeProxy.wrap(secs[idx], f"{self._path}.{name}")

                if isinstance(d, dict):
                    profs = (
                        d.get("parameters", {}).get("geometry", {}).get("profiles")
                        or d.get("parameters", {}).get("geometry", {}).get("sections")
                        or d.get("sections")
                    )
                    if isinstance(profs, (list, tuple)) and 0 <= idx < len(profs):
                        return ScopeProxy.wrap(profs[idx], f"{self._path}.{name}")
            except (ValueError, IndexError):
                pass

        raise AttributeError(
            f"'{target.__class__.__name__}' object has no attribute or parameter '{name}'"
        )

    def __getitem__(self, item: Any) -> Any:
        target = self._target
        if isinstance(target, (list, tuple)):
            return ScopeProxy.wrap(target[item], f"{self._path}[{item}]")
        if isinstance(target, dict):
            if item in target:
                return ScopeProxy.wrap(target[item], f"{self._path}[{item!r}]")
            if isinstance(item, str):
                hyphen = item.replace("_", "-")
                if hyphen in target:
                    return ScopeProxy.wrap(target[hyphen], f"{self._path}[{hyphen!r}]")
        return getattr(self, str(item))

    def __len__(self) -> int:
        return len(self._target)

    def __iter__(self) -> Any:
        for i, item in enumerate(self._target):
            yield ScopeProxy.wrap(item, f"{self._path}[{i}]")

    def __contains__(self, item: Any) -> bool:
        if isinstance(self._target, (dict, list, tuple, set)):
            return item in self._target
        return hasattr(self._target, str(item))

    def __float__(self) -> float:
        return float(self._target)

    def __int__(self) -> int:
        return int(self._target)

    def __bool__(self) -> bool:
        return bool(self._target)

    def __repr__(self) -> str:
        return f"<ScopeProxy({self._path or self._target!r})>"


def build_universal_scope(  # noqa: C901
    project_data: dict[str, Any],
    api: Any | None = None,
    config_id: str | None = None,
) -> dict[str, Any]:
    """Build the universal evaluation scope containing resolved parameters, models, and extensions.

    Single source of truth used for runtime expression evaluation and UI symbol discovery.
    """
    from setuav_studio.model.component import GenericComponent
    from setuav_studio.model.configuration import ConfigurationManager
    from setuav_studio.model.parameter import ParameterResolver

    resolver = ParameterResolver()
    cfg_mgr = ConfigurationManager(project_data, resolver=resolver)

    scope: dict[str, Any] = {}

    # 1. Project Global Parameters & Constants
    resolved_params = cfg_mgr.get_effective_project_parameters(config_id)
    for k, v in resolved_params.items():
        clean_k = k.replace("-", "_")
        scope[k] = v
        if clean_k != k:
            scope[clean_k] = v

    # 2. Materialized & Resolved Components
    components = cfg_mgr.get_materialized_components(config_id)
    models_list: list[Any] = []
    total_mass = 0.0

    if isinstance(components, list):
        for comp in components:
            if not isinstance(comp, dict):
                continue
            resolved_comp = cfg_mgr.get_resolved_component(comp, config_id)
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

        # Register models and proxies into evaluation scope
        for model in models_list:
            raw_cid = str(getattr(model, "id", "") or "")
            if not raw_cid:
                continue
            clean_cid = raw_cid.replace("-", "_")
            proxy = ScopeProxy.wrap(model, clean_cid)

            scope[clean_cid] = proxy
            if raw_cid != clean_cid:
                scope[raw_cid] = proxy

            # Short child alias registration (e.g. aileron -> main_wing.aileron)
            if hasattr(model, "children") and isinstance(model.children, dict):
                for child_name, child_model in model.children.items():
                    child_clean = child_name.replace("-", "_")
                    if child_clean not in scope:
                        scope[child_clean] = ScopeProxy.wrap(child_model, child_clean)

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
            scope[clean_ext_key] = ScopeProxy.wrap(ext_val, clean_ext_key)
            if ext_key != clean_ext_key:
                scope[ext_key] = ScopeProxy.wrap(ext_val, str(ext_key))

            # Features under extension (e.g. manufacturing spars, ribs, covers)
            features = ext_val.get("features")
            if isinstance(features, dict):
                for fid, feat in features.items():
                    if not isinstance(feat, dict) or feat.get("deleted") is True:
                        continue
                    clean_fid = str(feat.get("id") or fid).replace("-", "_")
                    feat_proxy = ScopeProxy.wrap(feat, clean_fid)
                    scope[clean_fid] = feat_proxy
                    scope[f"{clean_ext_key}_{clean_fid}"] = feat_proxy
                    if fid != clean_fid:
                        scope[fid] = feat_proxy

            # Configuration under extension
            cfg = ext_val.get("configuration")
            if isinstance(cfg, dict):
                cfg_id = str(cfg.get("id") or f"{clean_ext_key}_configuration").replace("-", "_")
                cfg_proxy = ScopeProxy.wrap(cfg, cfg_id)
                scope[cfg_id] = cfg_proxy
                scope[f"{clean_ext_key}_configuration"] = cfg_proxy

    # 4. Project level totals
    scope["total_mass"] = total_mass
    scope["mtow"] = resolved_params.get("mtow", total_mass)

    return scope
