"""Extensible lifecycle hooks and event providers for plugins and core."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from typing import Any


class HookRegistry:
    """Central registry for extensible lifecycle callbacks without hardcoded plugin imports."""

    def __init__(self) -> None:
        self._on_before_project_save: list[Callable[[dict[str, Any]], None]] = []
        self._on_after_project_save: list[Callable[[dict[str, Any]], None]] = []
        self._on_project_closing: list[Callable[[dict[str, Any]], bool]] = []
        self._unsaved_changes_checkers: list[Callable[[], bool]] = []

    def register_before_save_hook(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback executed before project serialization."""
        if callback not in self._on_before_project_save:
            self._on_before_project_save.append(callback)

    def unregister_before_save_hook(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Unregister a before-save callback."""
        if callback in self._on_before_project_save:
            self._on_before_project_save.remove(callback)

    def trigger_before_save(self, project_data: dict[str, Any]) -> None:
        """Execute all registered before-save callbacks."""
        for cb in self._on_before_project_save:
            with suppress(Exception):
                cb(project_data)

    def register_after_save_hook(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback executed after successful project serialization."""
        if callback not in self._on_after_project_save:
            self._on_after_project_save.append(callback)

    def unregister_after_save_hook(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Unregister an after-save callback."""
        if callback in self._on_after_project_save:
            self._on_after_project_save.remove(callback)

    def trigger_after_save(self, project_data: dict[str, Any]) -> None:
        """Execute all registered after-save callbacks."""
        for cb in self._on_after_project_save:
            with suppress(Exception):
                cb(project_data)

    def register_unsaved_changes_checker(self, checker: Callable[[], bool]) -> None:
        """Register a predicate checking if an active plugin has unsaved work."""
        if checker not in self._unsaved_changes_checkers:
            self._unsaved_changes_checkers.append(checker)

    def unregister_unsaved_changes_checker(self, checker: Callable[[], bool]) -> None:
        if checker in self._unsaved_changes_checkers:
            self._unsaved_changes_checkers.remove(checker)

    def has_plugin_unsaved_changes(self) -> bool:
        """Check if any registered plugin checker reports unsaved modifications."""
        for checker in self._unsaved_changes_checkers:
            with suppress(Exception):
                if checker():
                    return True
        return False


__all__ = ["HookRegistry"]
