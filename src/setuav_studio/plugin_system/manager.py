from __future__ import annotations

import logging
import pkgutil
from importlib import import_module, metadata
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QSettings

from setuav_studio_sdk.plugin import StudioPlugin

from .requirements import (
    PluginLoadIssue,
    _candidate_sort_key,
    _plugin_sort_key,
    _version_satisfies,
)

if TYPE_CHECKING:
    from .api import StudioAPI

logger = logging.getLogger(__name__)
_DISABLED_PLUGINS_KEY = "plugins/disabled"


class PluginManager:
    def __init__(self, api: StudioAPI) -> None:
        self._api = api
        self._plugins: dict[str, StudioPlugin] = {}
        self._candidates: dict[str, StudioPlugin] = {}
        self._disabled_plugins = self._load_disabled_plugins()
        self._load_issues: list[PluginLoadIssue] = []
        self._providers: dict[str, str] = {}
        self._plugin_providers: dict[str, dict[str, str]] = {}
        api._host.bind_project_requirement_checker(self.check_project_requirements)

    @property
    def active_plugins(self) -> tuple[StudioPlugin, ...]:
        """Return active plugins ordered by priority and plugin ID."""
        return tuple(
            sorted(
                self._plugins.values(),
                key=_plugin_sort_key,
            )
        )

    @property
    def load_issues(self) -> tuple[PluginLoadIssue, ...]:
        """Return issues from the most recent discovery pass."""
        return tuple(self._load_issues)

    @property
    def known_plugins(self) -> tuple[StudioPlugin, ...]:
        """Return discovered plugin candidates ordered by priority and ID."""
        return tuple(sorted(self._candidates.values(), key=_plugin_sort_key))

    def is_active(self, plugin_id: str) -> bool:
        """Return whether a plugin is currently active."""
        return plugin_id in self._plugins

    def is_disabled(self, plugin_id: str) -> bool:
        """Return whether a plugin was explicitly disabled by the user."""
        return plugin_id in self._disabled_plugins

    def activate(self, plugin: StudioPlugin) -> None:
        if plugin.id in self._plugins:
            raise ValueError(f"Plugin is already active: {plugin.id}")
        was_disabled = plugin.id in self._disabled_plugins
        self._candidates[plugin.id] = plugin
        self._disabled_plugins.discard(plugin.id)
        logger.info("Activating plugin: %s", plugin.id)
        try:
            plugin.activate(self._api)
        except Exception:
            if was_disabled:
                self._disabled_plugins.add(plugin.id)
            raise
        self._plugins[plugin.id] = plugin
        if was_disabled:
            self._save_disabled_plugins()
        provides = getattr(plugin, "provides", {})
        if isinstance(provides, dict):
            provided = {str(plugin_id): str(version) for plugin_id, version in provides.items()}
            self._providers.update(provided)
            self._plugin_providers[plugin.id] = provided

    def deactivate(self, plugin_id: str) -> None:
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise ValueError(f"Plugin is not active: {plugin_id}")
        logger.info("Deactivating plugin: %s", plugin_id)
        deactivate = getattr(plugin, "deactivate", None)
        if not callable(deactivate):
            raise TypeError(f"Plugin does not implement deactivate(api): {plugin_id}")
        deactivate(self._api)
        self._plugins.pop(plugin_id, None)
        self._disabled_plugins.add(plugin_id)
        self._save_disabled_plugins()
        for provided_id in self._plugin_providers.pop(plugin_id, {}):
            self._providers.pop(provided_id, None)

    def discover(self) -> list[PluginLoadIssue]:
        logger.info("Discovering plugins")
        bundled_issues, bundled_candidates = self._collect_bundled_candidates()
        entry_point_issues, entry_point_candidates = self._collect_entry_point_candidates()
        issues = bundled_issues + entry_point_issues
        candidates = bundled_candidates + entry_point_candidates
        candidates.sort(key=lambda item: (item[0], item[1]))
        self._activate_candidates(candidates, issues)
        self._load_issues = issues
        return issues

    def check_project_requirements(self, data: dict[str, Any]) -> list[str]:
        requirements = data.get("plugins", [])
        if not isinstance(requirements, list):
            return []

        issues: list[str] = []
        for requirement in requirements:
            if not isinstance(requirement, dict):
                continue
            plugin_id = requirement.get("id")
            requested = requirement.get("version")
            if not isinstance(plugin_id, str):
                continue
            installed = self._providers.get(plugin_id)
            if installed is None:
                issues.append(f"Missing plugin: {plugin_id}")
            elif isinstance(requested, str) and not _version_satisfies(installed, requested):
                issues.append(
                    f"Incompatible plugin: {plugin_id} {installed} (requires {requested})"
                )
        return issues

    def _discover_bundled(self) -> list[PluginLoadIssue]:
        issues, candidates = self._collect_bundled_candidates()
        self._activate_candidates(candidates, issues)
        return issues

    def _collect_bundled_candidates(
        self,
    ) -> tuple[list[PluginLoadIssue], list[tuple[int, str, object]]]:
        issues: list[PluginLoadIssue] = []
        candidates: list[tuple[int, str, object]] = []
        try:
            package = import_module("plugins")
            for module_info in pkgutil.iter_modules(package.__path__):
                source = f"plugins.{module_info.name}"
                try:
                    module = import_module(source)
                    candidate = getattr(module, "PLUGIN", None)
                    if candidate is not None:
                        candidates.append(_candidate_sort_key(candidate, source))
                except Exception as exc:
                    logger.warning("Failed to load bundled plugin %s: %s", source, exc)
                    issues.append(PluginLoadIssue(source, str(exc)))
        except Exception as exc:
            logger.warning("Failed to load plugins package: %s", exc)
            issues.append(PluginLoadIssue("plugins", str(exc)))
        return issues, candidates

    def _discover_entry_points(self) -> list[PluginLoadIssue]:
        issues, candidates = self._collect_entry_point_candidates()
        self._activate_candidates(candidates, issues)
        return issues

    def _collect_entry_point_candidates(
        self,
    ) -> tuple[list[PluginLoadIssue], list[tuple[int, str, object]]]:
        issues: list[PluginLoadIssue] = []
        candidates: list[tuple[int, str, object]] = []
        for entry_point in metadata.entry_points(group="setuav_studio.plugins"):
            try:
                logger.info("Loading entry-point plugin: %s", entry_point.name)
                candidates.append(_candidate_sort_key(entry_point.load(), entry_point.name))
            except Exception as exc:
                logger.warning("Failed to load entry-point plugin %s: %s", entry_point.name, exc)
                issues.append(PluginLoadIssue(entry_point.name, str(exc)))
        return issues, candidates

    def _activate_candidates(
        self,
        candidates: list[tuple[int, str, object]],
        issues: list[PluginLoadIssue],
    ) -> None:
        candidates.sort(key=lambda item: (item[0], item[1]))
        for _, _, candidate in candidates:
            try:
                self._activate_candidate(candidate)
            except Exception as exc:
                logger.warning("Failed to activate plugin: %s", exc)
                issues.append(PluginLoadIssue("plugin", str(exc)))

    def _activate_candidate(self, candidate: object) -> None:
        plugin = candidate() if isinstance(candidate, type) else candidate
        plugin_id = getattr(plugin, "id", None)
        if isinstance(plugin_id, str) and plugin_id in self._plugins:
            return
        if isinstance(plugin_id, str):
            if plugin_id in self._disabled_plugins and plugin_id in self._candidates:
                return
            self._candidates[plugin_id] = plugin
            if plugin_id in self._disabled_plugins:
                return
        if not hasattr(plugin, "activate") or not isinstance(plugin_id, str):
            raise TypeError("Plugin entry must provide id and activate(api)")
        self.activate(plugin)

    @staticmethod
    def _load_disabled_plugins() -> set[str]:
        stored = QSettings().value(_DISABLED_PLUGINS_KEY, [])
        if isinstance(stored, str):
            return {stored}
        if isinstance(stored, (list, tuple, set)):
            return {str(plugin_id) for plugin_id in stored if str(plugin_id)}
        return set()

    def _save_disabled_plugins(self) -> None:
        QSettings().setValue(_DISABLED_PLUGINS_KEY, sorted(self._disabled_plugins))

    def activate_plugin(self, plugin_id: str) -> None:
        """Activate a previously discovered plugin by ID."""
        plugin = self._candidates.get(plugin_id)
        if plugin is None:
            raise ValueError(f"Plugin is not discovered: {plugin_id}")
        self.activate(plugin)


__all__ = ["PluginManager"]
