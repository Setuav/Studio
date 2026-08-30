"""Configuration management for variant parameter overrides and switching."""

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
    """Manages project configurations, variant overrides, and parameter resolution."""

    def __init__(
        self,
        project_data: dict[str, Any],
        resolver: ParameterResolver | None = None,
    ) -> None:
        self.project_data = project_data
        self.resolver = resolver or ParameterResolver()
        self._active_id: str | None = None
        self._listeners: list[Callable[[], None]] = []

        # Initialize active_id to default config if one exists
        for cfg in self.get_configurations():
            if cfg.get("is_default"):
                self._active_id = cfg.get("id")
                break

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

    def set_active_id(self, config_id: str | None) -> None:
        """Set active configuration ID (None for base)."""
        if config_id is not None and self.get_configuration(config_id) is None:
            raise KeyError(f"Configuration '{config_id}' does not exist.")
        if self._active_id != config_id:
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
        parameter_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new configuration and add it to the project."""
        configs = self.get_configurations()
        cid = config_id or tag.lower().strip()
        if not cid:
            cid = f"config-{len(configs) + 1}"

        # Ensure ID uniqueness
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
            "color": color,
            "parameter_overrides": dict(parameter_overrides or {}),
            "is_default": is_default,
        }
        configs.append(new_config)
        self._notify()
        return new_config

    def update_configuration(self, config_id: str, **kwargs: Any) -> dict[str, Any]:
        """Update fields of an existing configuration."""
        cfg = self.get_configuration(config_id)
        if cfg is None:
            raise KeyError(f"Configuration '{config_id}' not found.")

        if kwargs.get("is_default"):
            for c in self.get_configurations():
                c["is_default"] = False

        for k, v in kwargs.items():
            if k == "id":
                continue  # immutable ID
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
        """Set a parameter override for a specific configuration."""
        cfg = self.get_configuration(config_id)
        if cfg is None:
            raise KeyError(f"Configuration '{config_id}' not found.")
        overrides = cfg.setdefault("parameter_overrides", {})
        overrides[path] = value
        self._notify()

    def remove_override(self, config_id: str, path: str) -> bool:
        """Remove a parameter override from a specific configuration."""
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
        """Check if a path is overridden in the specified or active configuration."""
        overrides = self.get_overrides(config_id)
        return path in overrides

    def get_effective_project_parameters(self, config_id: str | None = None) -> dict[str, Any]:
        """Compute resolved project parameters including any active overrides."""
        base_params = copy.deepcopy(self.project_data.get("parameters", {}))
        overrides = self.get_overrides(config_id)

        # Apply project.parameters.* overrides
        for path, val in overrides.items():
            if path.startswith("project.parameters."):
                param_key = path[len("project.parameters.") :]
                base_params[param_key] = val

        return self.resolver.resolve_all(base_params)

    def get_resolved_component(
        self, component: dict[str, Any], config_id: str | None = None
    ) -> dict[str, Any]:
        """Return a deep copy of a component with active overrides and expressions evaluated."""
        comp_copy = copy.deepcopy(component)
        comp_id = comp_copy.get("id", "")
        overrides = self.get_overrides(config_id)

        # Apply overrides targeted at this component (e.g. "wing-1.parameters.geometry.span")
        prefix = f"{comp_id}."
        for path, val in overrides.items():
            if path.startswith(prefix):
                rel_path = path[len(prefix) :]
                with contextlib.suppress(Exception):
                    set_by_path(comp_copy, rel_path, val)

        # Evaluate expressions inside component parameters using effective project parameters
        effective_params = self.get_effective_project_parameters(config_id)
        if "parameters" in comp_copy and isinstance(comp_copy["parameters"], dict):
            comp_copy["parameters"] = self.resolver.evaluate_component_parameters(
                comp_copy["parameters"], effective_params
            )

        return comp_copy
