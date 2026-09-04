"""Configuration management using a clean Delta (diff/overrides) model.

Configurations inherit all base project components and parameters, storing only:
- parameter_overrides: dictionary of path -> value (e.g. project.parameters.* or comp_id.parameters.*)
- excluded_components: list of component IDs removed in this configuration
- added_components: list of new component definitions added in this configuration
- component_overrides: dictionary of comp_id -> changed properties (name, transform, etc.)
"""

from __future__ import annotations

import contextlib
import copy
import re
from collections.abc import Callable
from typing import Any

from setuav_studio.model.parameter import ParameterResolver


class ConfigurationError(Exception):
    """Raised when configuration operations fail."""


def parse_path_segments(path: str) -> list[str | int]:
    """Parse a dot/bracket notation path into list of key/index segments."""
    tokens = re.findall(r"[^.\[\]]+|\[\d+\]", path)
    segments: list[str | int] = []
    for token in tokens:
        if token.startswith("[") and token.endswith("]"):
            segments.append(int(token[1:-1]))
        else:
            segments.append(token)
    return segments


def get_by_path(target: Any, path: str) -> Any:
    """Retrieve value from nested dict/list using dot/bracket path."""
    segments = parse_path_segments(path)
    curr = target
    for seg in segments:
        if isinstance(seg, int):
            if not isinstance(curr, (list, tuple)) or seg >= len(curr):
                raise IndexError(f"Index {seg} out of bounds in path '{path}'")
            curr = curr[seg]
        else:
            if not isinstance(curr, dict) or seg not in curr:
                raise KeyError(f"Key '{seg}' not found in path '{path}'")
            curr = curr[seg]
    return curr


def _ensure_intermediate_segment(curr: Any, seg: str | int, next_seg: str | int) -> Any:
    """Ensure intermediate list or dict container exists."""
    if isinstance(seg, int):
        if not isinstance(curr, list):
            raise TypeError("Expected list container")
        while len(curr) <= seg:
            curr.append({} if isinstance(next_seg, str) else [])
        return curr[seg]

    if not isinstance(curr, dict):
        raise TypeError("Expected dict container")
    if seg not in curr or not isinstance(curr[seg], (dict, list)):
        curr[seg] = [] if isinstance(next_seg, int) else {}
    return curr[seg]


def set_by_path(target: Any, path: str, value: Any) -> None:
    """Set value in nested dict/list using dot/bracket path."""
    segments = parse_path_segments(path)
    if not segments:
        return

    curr = target
    for i, seg in enumerate(segments[:-1]):
        curr = _ensure_intermediate_segment(curr, seg, segments[i + 1])

    last_seg = segments[-1]
    if isinstance(last_seg, int):
        if not isinstance(curr, list):
            raise TypeError(f"Expected list at final segment in path '{path}'")
        while len(curr) <= last_seg:
            curr.append(None)
        curr[last_seg] = value
    else:
        if not isinstance(curr, dict):
            raise TypeError(f"Expected dict at final segment in path '{path}'")
        curr[last_seg] = value


def _apply_component_overrides(
    components: list[dict[str, Any]], comp_overrides: dict[str, Any]
) -> None:
    """Apply top-level component property overrides in place."""
    for comp in components:
        cid = comp.get("id")
        if cid in comp_overrides:
            for k, v in comp_overrides[cid].items():
                comp[k] = copy.deepcopy(v)


def _apply_parameter_overrides(
    components: list[dict[str, Any]],
    parameters: dict[str, Any],
    param_overrides: dict[str, Any],
) -> None:
    """Apply project and component parameter overrides in place."""
    for path, value in param_overrides.items():
        if path.startswith("project.parameters."):
            param_key = path[len("project.parameters.") :]
            parameters[param_key] = copy.deepcopy(value)
        else:
            for comp in components:
                cid = str(comp.get("id") or "")
                if cid and path.startswith(f"{cid}."):
                    sub_path = path[len(cid) + 1 :]
                    with contextlib.suppress(Exception):
                        set_by_path(comp, sub_path, copy.deepcopy(value))
                    break


def apply_configuration_delta(
    base_components: list[dict[str, Any]],
    base_parameters: dict[str, Any],
    base_assemblies: list[dict[str, Any]],
    config_dict: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Materialize full components and parameters for a configuration by applying its delta to base."""
    if "components" in config_dict and isinstance(config_dict["components"], list):
        components = copy.deepcopy(config_dict["components"])
        parameters = copy.deepcopy(config_dict.get("parameters", base_parameters))
        assemblies = copy.deepcopy(config_dict.get("assemblies", base_assemblies))
        return components, parameters, assemblies

    components = copy.deepcopy(base_components)
    parameters = copy.deepcopy(base_parameters)
    assemblies = copy.deepcopy(base_assemblies)

    excluded_ids = set(config_dict.get("excluded_components", []))
    if excluded_ids:
        components = [c for c in components if c.get("id") not in excluded_ids]

    _apply_component_overrides(components, config_dict.get("component_overrides", {}))
    _apply_parameter_overrides(components, parameters, config_dict.get("parameter_overrides", {}))

    added_components = copy.deepcopy(config_dict.get("added_components", []))
    components.extend(added_components)

    return components, parameters, assemblies


def compute_configuration_delta(
    base_components: list[dict[str, Any]],
    base_parameters: dict[str, Any],
    current_components: list[dict[str, Any]],
    current_parameters: dict[str, Any],
) -> dict[str, Any]:
    """Compute the minimal delta (overrides, additions, exclusions) between base and current state."""
    base_comp_map = {c["id"]: c for c in base_components if isinstance(c, dict) and "id" in c}
    curr_comp_map = {c["id"]: c for c in current_components if isinstance(c, dict) and "id" in c}

    excluded_components = [cid for cid in base_comp_map if cid not in curr_comp_map]
    added_components = [c for cid, c in curr_comp_map.items() if cid not in base_comp_map]

    component_overrides: dict[str, Any] = {}
    parameter_overrides: dict[str, Any] = {}

    # Check project parameter differences
    _diff_dict_paths(
        base_parameters,
        current_parameters,
        prefix="project.parameters",
        out=parameter_overrides,
    )

    # Check common components
    for cid in base_comp_map:
        if cid not in curr_comp_map:
            continue
        base_c = base_comp_map[cid]
        curr_c = curr_comp_map[cid]

        # Check top-level properties
        overrides: dict[str, Any] = {}
        for prop in ("name", "parent", "attach_to", "transform", "mass"):
            if curr_c.get(prop) != base_c.get(prop):
                overrides[prop] = copy.deepcopy(curr_c.get(prop))
        if overrides:
            component_overrides[cid] = overrides

        # Check parameter differences
        _diff_dict_paths(
            base_c.get("parameters", {}),
            curr_c.get("parameters", {}),
            prefix=f"{cid}.parameters",
            out=parameter_overrides,
        )

    delta: dict[str, Any] = {
        "parameter_overrides": parameter_overrides,
        "excluded_components": excluded_components,
        "added_components": added_components,
        "component_overrides": component_overrides,
    }
    return delta


def _diff_dict_paths(base: Any, current: Any, prefix: str, out: dict[str, Any]) -> None:
    """Helper to find leaf differences between two dict structures."""
    if isinstance(base, dict) and isinstance(current, dict):
        all_keys = set(base.keys()) | set(current.keys())
        for k in all_keys:
            new_prefix = f"{prefix}.{k}"
            if k not in base:
                out[new_prefix] = current[k]
            elif k not in current:
                out[new_prefix] = None
            else:
                _diff_dict_paths(base[k], current[k], new_prefix, out)
    elif base != current:
        out[prefix] = current


class ConfigurationManager:
    """Manages project configurations using a clean Delta (diff/override) model."""

    def __init__(
        self,
        project_data: dict[str, Any],
        resolver: ParameterResolver | None = None,
    ) -> None:
        self.project_data = project_data
        self.resolver = resolver or ParameterResolver()
        self._active_id: str | None = None
        self._listeners: list[Callable[[], None]] = []

        # Snapshot of clean base state
        self._base_state: dict[str, Any] = {
            "components": copy.deepcopy(self.project_data.get("components", [])),
            "parameters": copy.deepcopy(self.project_data.get("parameters", {})),
            "assemblies": copy.deepcopy(self.project_data.get("assemblies", [])),
        }

    def add_change_listener(self, callback: Callable[[], None]) -> None:
        """Register a callback for configuration changes."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_change_listener(self, callback: Callable[[], None]) -> None:
        """Unregister a callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            with contextlib.suppress(Exception):
                cb()

    def get_configurations(self) -> list[dict[str, Any]]:
        """Return list of configuration dictionaries."""
        return self.project_data.setdefault("configurations", [])

    def get_configuration(self, config_id: str) -> dict[str, Any] | None:
        """Get configuration dictionary by its ID."""
        for cfg in self.get_configurations():
            if cfg.get("id") == config_id:
                return cfg
        return None

    def get_active_id(self) -> str | None:
        """Return currently active configuration ID, or None for base."""
        if self._active_id is not None and self.get_configuration(self._active_id) is None:
            self._active_id = None
        return self._active_id

    def get_active_configuration(self) -> dict[str, Any] | None:
        """Return currently active configuration dict, or None for base."""
        aid = self.get_active_id()
        if aid is None:
            return None
        return self.get_configuration(aid)

    def sync_current_state_to_active(self) -> None:
        """Sync working state back into the active configuration's delta or base snapshot."""
        current_components = self.project_data.get("components", [])
        current_parameters = self.project_data.get("parameters", {})
        current_assemblies = self.project_data.get("assemblies", [])

        active_id = self.get_active_id()
        if active_id is None:
            self._base_state = {
                "components": copy.deepcopy(current_components),
                "parameters": copy.deepcopy(current_parameters),
                "assemblies": copy.deepcopy(current_assemblies),
            }
        else:
            cfg = self.get_configuration(active_id)
            if cfg is not None:
                delta = compute_configuration_delta(
                    self._base_state["components"],
                    self._base_state["parameters"],
                    current_components,
                    current_parameters,
                )
                cfg["parameter_overrides"] = delta["parameter_overrides"]
                cfg["excluded_components"] = delta["excluded_components"]
                cfg["added_components"] = delta["added_components"]
                cfg["component_overrides"] = delta["component_overrides"]
                # Clean up legacy redundant full snapshots if present
                cfg.pop("components", None)
                cfg.pop("parameters", None)
                cfg.pop("assemblies", None)

    def set_active_id(self, config_id: str | None) -> None:
        """Switch active configuration, materializing the state from base + delta."""
        if config_id is not None and self.get_configuration(config_id) is None:
            raise KeyError(f"Configuration '{config_id}' does not exist.")

        if self._active_id == config_id:
            return

        # 1. Sync current working state
        self.sync_current_state_to_active()

        # 2. Materialize target configuration state
        if config_id is None:
            self.project_data["components"] = copy.deepcopy(self._base_state["components"])
            self.project_data["parameters"] = copy.deepcopy(self._base_state["parameters"])
            self.project_data["assemblies"] = copy.deepcopy(self._base_state.get("assemblies", []))
        else:
            target_cfg = self.get_configuration(config_id)
            if target_cfg is not None:
                comps, params, assems = apply_configuration_delta(
                    self._base_state["components"],
                    self._base_state["parameters"],
                    self._base_state.get("assemblies", []),
                    target_cfg,
                )
                self.project_data["components"] = comps
                self.project_data["parameters"] = params
                self.project_data["assemblies"] = assems

        self._active_id = config_id
        self._notify()

    def create_configuration(
        self,
        name: str,
        tag: str,
        description: str = "",
        is_default: bool = False,
        config_id: str | None = None,
        parameter_overrides: dict[str, Any] | None = None,
        excluded_components: list[str] | None = None,
        added_components: list[dict[str, Any]] | None = None,
        component_overrides: dict[str, Any] | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        """Create a new delta-based configuration."""
        self.sync_current_state_to_active()

        configs = self.get_configurations()
        cid = config_id or tag.lower().strip()
        if not cid:
            cid = f"config-{len(configs) + 1}"

        base_cid = cid
        counter = 1
        existing_ids = {c.get("id") for c in configs}
        while cid in existing_ids:
            cid = f"{base_cid}-{counter}"
            counter += 1

        if is_default:
            for c in configs:
                c["is_default"] = False

        new_config: dict[str, Any] = {
            "id": cid,
            "name": name,
            "tag": tag,
            "description": description,
            "parameter_overrides": dict(parameter_overrides or {}),
            "excluded_components": list(excluded_components or []),
            "added_components": list(added_components or []),
            "component_overrides": dict(component_overrides or {}),
            "is_default": is_default,
        }
        configs.append(new_config)
        self._notify()
        return new_config

    def update_configuration(self, config_id: str, **kwargs: Any) -> dict[str, Any]:
        """Update metadata fields of an existing configuration."""
        cfg = self.get_configuration(config_id)
        if cfg is None:
            raise KeyError(f"Configuration '{config_id}' not found.")

        if kwargs.get("is_default"):
            for c in self.get_configurations():
                c["is_default"] = False

        for k, v in kwargs.items():
            if k == "id":
                continue
            cfg[k] = v

        self._notify()
        return cfg

    def delete_configuration(self, config_id: str) -> bool:
        """Delete a configuration."""
        configs = self.get_configurations()
        idx = -1
        for i, c in enumerate(configs):
            if c.get("id") == config_id:
                idx = i
                break
        if idx != -1:
            configs.pop(idx)
            if self._active_id == config_id:
                self._active_id = None
                self.project_data["components"] = copy.deepcopy(self._base_state["components"])
                self.project_data["parameters"] = copy.deepcopy(self._base_state["parameters"])
                self.project_data["assemblies"] = copy.deepcopy(
                    self._base_state.get("assemblies", [])
                )
            self._notify()
            return True
        return False

    def get_overrides(self, config_id: str | None = None) -> dict[str, Any]:
        """Get overrides dictionary for given or active configuration."""
        cid = config_id if config_id is not None else self._active_id
        if cid is None:
            return {}
        cfg = self.get_configuration(cid)
        if cfg is None:
            return {}
        return cfg.setdefault("parameter_overrides", {})

    def set_override(self, config_id: str, path: str, value: Any) -> None:
        """Set a parameter override."""
        cfg = self.get_configuration(config_id)
        if cfg is None:
            raise KeyError(f"Configuration '{config_id}' not found.")
        overrides = cfg.setdefault("parameter_overrides", {})
        overrides[path] = value
        self._notify()

    def remove_override(self, config_id: str, path: str) -> bool:
        """Remove a parameter override."""
        cfg = self.get_configuration(config_id)
        if cfg is None:
            return False
        overrides = cfg.setdefault("parameter_overrides", {})
        if path in overrides:
            del overrides[path]
            self._notify()
            return True
        return False

    def is_overridden(self, path: str, config_id: str | None = None) -> bool:
        """Check if a path is overridden."""
        overrides = self.get_overrides(config_id)
        return path in overrides

    def get_effective_project_parameters(self, config_id: str | None = None) -> dict[str, Any]:
        """Compute resolved project parameters for the active configuration."""
        if config_id is not None and config_id != self._active_id:
            cfg = self.get_configuration(config_id)
            params = copy.deepcopy(self._base_state["parameters"])
            if cfg:
                for path, val in cfg.get("parameter_overrides", {}).items():
                    if path.startswith("project.parameters."):
                        k = path[len("project.parameters.") :]
                        if val is None:
                            params.pop(k, None)
                        else:
                            params[k] = copy.deepcopy(val)
        else:
            params = copy.deepcopy(self.project_data.get("parameters", {}))

        return self.resolver.resolve_all(params)

    def get_materialized_components(self, config_id: str | None = None) -> list[dict[str, Any]]:
        """Return the materialized component list for any configuration without switching active state."""
        if config_id is None or config_id == self._active_id:
            return self.project_data.get("components", [])
        cfg = self.get_configuration(config_id)
        if cfg is None:
            return copy.deepcopy(self._base_state.get("components", []))
        comps, _, _ = apply_configuration_delta(
            self._base_state.get("components", []),
            self._base_state.get("parameters", {}),
            self._base_state.get("assemblies", []),
            cfg,
        )
        return comps

    def get_resolved_component(
        self, component: dict[str, Any], config_id: str | None = None
    ) -> dict[str, Any]:
        """Return a deep copy of a component with inline expressions evaluated."""
        comp_copy = copy.deepcopy(component)
        effective_params = self.get_effective_project_parameters(config_id)

        if "parameters" in comp_copy and isinstance(comp_copy["parameters"], dict):
            comp_copy["parameters"] = self.resolver.evaluate_component_parameters(
                comp_copy["parameters"], effective_params
            )
            # Apply evaluated transform expressions to comp_copy["transform"]
            tf_exprs = comp_copy["parameters"].get("transform_expressions")
            if isinstance(tf_exprs, dict):
                tf = comp_copy.setdefault("transform", {})
                pos_dict = tf.setdefault("position", {})
                rot_dict = tf.setdefault("rotation", {})
                for k, v in tf_exprs.items():
                    if isinstance(v, (int, float)):
                        if k.startswith("pos."):
                            pos_dict[k[4:]] = float(v)
                        elif k.startswith("position."):
                            pos_dict[k[9:]] = float(v)
                        elif k.startswith("rot."):
                            rot_dict[k[4:]] = float(v)
                        elif k.startswith("rotation."):
                            rot_dict[k[9:]] = float(v)
            # Apply evaluated mass_expression to comp_copy["mass"]
            mass_expr = comp_copy["parameters"].get("mass_expression")
            if isinstance(mass_expr, (int, float)):
                comp_copy["mass"] = float(mass_expr)

        return comp_copy
