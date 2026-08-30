"""Configuration management for project variants (independent component sets & parameters)."""

from __future__ import annotations

import contextlib
import copy
import re
from collections.abc import Callable
from typing import Any

from setuav_studio.plugins.core.parameters import ParameterResolver


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


class ConfigurationManager:
    """Manages project configurations as distinct design variants.

    Each configuration has its own components, parameters, and assemblies,
    functioning like an independent variant within the same project file.
    """

    def __init__(
        self,
        project_data: dict[str, Any],
        resolver: ParameterResolver | None = None,
    ) -> None:
        self.project_data = project_data
        self.resolver = resolver or ParameterResolver()
        self._active_id: str | None = None
        self._listeners: list[Callable[[], None]] = []

        # Keep snapshot of base state
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
        return self._active_id

    def get_active_configuration(self) -> dict[str, Any] | None:
        """Return currently active configuration dict, or None for base."""
        if self._active_id is None:
            return None
        return self.get_configuration(self._active_id)

    def sync_current_state_to_active(self) -> None:
        """Save current working components/parameters into the active configuration or base snapshot."""
        current_components = copy.deepcopy(self.project_data.get("components", []))
        current_parameters = copy.deepcopy(self.project_data.get("parameters", {}))
        current_assemblies = copy.deepcopy(self.project_data.get("assemblies", []))

        if self._active_id is None:
            self._base_state = {
                "components": current_components,
                "parameters": current_parameters,
                "assemblies": current_assemblies,
            }
        else:
            cfg = self.get_configuration(self._active_id)
            if cfg is not None:
                cfg["components"] = current_components
                cfg["parameters"] = current_parameters
                cfg["assemblies"] = current_assemblies

    def set_active_id(self, config_id: str | None) -> None:
        """Switch active configuration and swap project components and parameters."""
        if config_id is not None and self.get_configuration(config_id) is None:
            raise KeyError(f"Configuration '{config_id}' does not exist.")

        if self._active_id == config_id:
            return

        # 1. Save current working state to previous active config/base
        self.sync_current_state_to_active()

        # 2. Load new active state into project_data
        if config_id is None:
            self.project_data["components"] = copy.deepcopy(self._base_state["components"])
            self.project_data["parameters"] = copy.deepcopy(self._base_state["parameters"])
            self.project_data["assemblies"] = copy.deepcopy(self._base_state.get("assemblies", []))
        else:
            target_cfg = self.get_configuration(config_id)
            if target_cfg is not None:
                if "components" not in target_cfg:
                    target_cfg["components"] = copy.deepcopy(self._base_state["components"])
                if "parameters" not in target_cfg:
                    target_cfg["parameters"] = copy.deepcopy(self._base_state["parameters"])
                if "assemblies" not in target_cfg:
                    target_cfg["assemblies"] = copy.deepcopy(self._base_state.get("assemblies", []))

                self.project_data["components"] = copy.deepcopy(target_cfg["components"])
                self.project_data["parameters"] = copy.deepcopy(target_cfg["parameters"])
                self.project_data["assemblies"] = copy.deepcopy(target_cfg["assemblies"])

        self._active_id = config_id
        self._notify()

    def create_configuration(
        self,
        name: str,
        tag: str,
        description: str = "",
        color: str = "#2196F3",
        is_default: bool = False,
        config_id: str | None = None,
        components: list[dict[str, Any]] | None = None,
        parameters: dict[str, Any] | None = None,
        assemblies: list[dict[str, Any]] | None = None,
        parameter_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new configuration variant, cloning the current working project state by default."""
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

        init_components = (
            copy.deepcopy(components)
            if components is not None
            else copy.deepcopy(self.project_data.get("components", []))
        )
        init_parameters = (
            copy.deepcopy(parameters)
            if parameters is not None
            else copy.deepcopy(self.project_data.get("parameters", {}))
        )
        init_assemblies = (
            copy.deepcopy(assemblies)
            if assemblies is not None
            else copy.deepcopy(self.project_data.get("assemblies", []))
        )

        new_config: dict[str, Any] = {
            "id": cid,
            "name": name,
            "tag": tag,
            "description": description,
            "color": color,
            "components": init_components,
            "parameters": init_parameters,
            "assemblies": init_assemblies,
            "parameter_overrides": dict(parameter_overrides or {}),
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
                # Switch back to base
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
            params = copy.deepcopy(cfg.get("parameters", {})) if cfg else {}
        else:
            params = copy.deepcopy(self.project_data.get("parameters", {}))

        return self.resolver.resolve_all(params)

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

        return comp_copy
