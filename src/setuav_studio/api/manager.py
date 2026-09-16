from __future__ import annotations

import logging
import pkgutil
import sys
from importlib import import_module, metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import QSettings

from setuav_studio_sdk.plugin import StudioPlugin

from .installer import get_user_plugins_dir, install_plugin_archive
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
            plugin.activate(cast(Any, self._api))
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
        user_issues, user_candidates = self._collect_user_directory_candidates()
        issues = bundled_issues + entry_point_issues + user_issues
        candidates = bundled_candidates + entry_point_candidates + user_candidates
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

    def _collect_user_directory_candidates(
        self,
    ) -> tuple[list[PluginLoadIssue], list[tuple[int, str, object]]]:
        issues: list[PluginLoadIssue] = []
        candidates: list[tuple[int, str, object]] = []
        user_dir = get_user_plugins_dir()
        if not user_dir.is_dir():
            return issues, candidates

        user_dir_str = str(user_dir)
        if user_dir_str not in sys.path:
            sys.path.insert(0, user_dir_str)

        for item in sorted(user_dir.iterdir()):
            if item.name.startswith((".", "__")):
                continue
            try:
                candidate = None
                source_name = item.stem if item.is_file() else item.name
                if item.is_dir():
                    candidate = self._load_plugin_from_dir(item)
                elif item.is_file() and item.suffix == ".py":
                    candidate = self._load_plugin_from_file(item)

                if candidate is not None:
                    candidates.append(_candidate_sort_key(candidate, source_name))
            except Exception as exc:
                logger.warning("Failed to load user plugin from %s: %s", item.name, exc)
                issues.append(PluginLoadIssue(item.name, str(exc)))

        return issues, candidates

    def _load_plugin_from_dir(self, plugin_dir: Path) -> object | None:
        # 1. Check for pyproject.toml with entry-points
        pyproject_file = plugin_dir / "pyproject.toml"
        if pyproject_file.is_file():
            candidate = self._load_from_pyproject(plugin_dir, pyproject_file)
            if candidate is not None:
                return candidate

        # 2. Check if src/ exists and add to sys.path
        src_dir = plugin_dir / "src"
        if src_dir.is_dir() and str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        if str(plugin_dir) not in sys.path:
            sys.path.insert(0, str(plugin_dir))

        # 3. Check for standard package __init__.py
        init_file = plugin_dir / "__init__.py"
        if init_file.is_file():
            mod = import_module(plugin_dir.name)
            candidate = self._find_plugin_in_module(mod)
            if candidate is not None:
                return candidate
            if (plugin_dir / "plugin.py").is_file():
                submod = import_module(f"{plugin_dir.name}.plugin")
                candidate = self._find_plugin_in_module(submod)
                if candidate is not None:
                    return candidate

        # 4. Check for standalone plugin.py in the directory
        plugin_file = plugin_dir / "plugin.py"
        if plugin_file.is_file():
            return self._load_plugin_from_file(plugin_file, module_name=plugin_dir.name)

        return None

    def _load_from_pyproject(self, plugin_dir: Path, pyproject_file: Path) -> object | None:
        try:
            import tomllib

            data = tomllib.loads(pyproject_file.read_text("utf-8"))
            ep_group = (
                data.get("project", {}).get("entry-points", {}).get("setuav_studio.plugins", {})
            )
            if not isinstance(ep_group, dict) or not ep_group:
                return None

            src_dir = plugin_dir / "src"
            if src_dir.is_dir() and str(src_dir) not in sys.path:
                sys.path.insert(0, str(src_dir))
            if str(plugin_dir) not in sys.path:
                sys.path.insert(0, str(plugin_dir))

            for ep_str in ep_group.values():
                if isinstance(ep_str, str) and ":" in ep_str:
                    mod_name, attr_name = ep_str.split(":", 1)
                    mod = import_module(mod_name.strip())
                    candidate = getattr(mod, attr_name.strip(), None)
                    if candidate is not None:
                        return candidate
        except Exception as exc:
            logger.warning(
                "Could not load entry-points from pyproject.toml in %s: %s",
                plugin_dir.name,
                exc,
            )
        return None

    def _load_plugin_from_file(
        self, file_path: Path, module_name: str | None = None
    ) -> object | None:
        import importlib.util

        name = module_name or file_path.stem
        spec = importlib.util.spec_from_file_location(f"user_plugins.{name}", file_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return self._find_plugin_in_module(mod)
        return None

    @staticmethod
    def _find_plugin_in_module(module: Any) -> object | None:
        if hasattr(module, "PLUGIN"):
            return module.PLUGIN
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and obj.__name__ != "StudioPlugin"
                and hasattr(obj, "id")
                and hasattr(obj, "activate")
                and callable(obj.activate)
            ) or (
                not isinstance(obj, type)
                and hasattr(obj, "id")
                and hasattr(obj, "activate")
                and callable(obj.activate)
            ):
                return obj
        return None

    def install_archive(self, archive_path: Path | str) -> Path:
        """Extract and install a plugin archive into the user plugins directory, then discover."""
        installed = install_plugin_archive(archive_path, get_user_plugins_dir())
        self.discover()
        return installed

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
        plugin: Any = candidate() if isinstance(candidate, type) else candidate
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
