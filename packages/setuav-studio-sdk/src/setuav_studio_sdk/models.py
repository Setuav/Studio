"""Data contracts exchanged between the application and plugins."""

from pathlib import Path
from typing import Any, Literal, Protocol


class ProjectDocument(Protocol):
    """Project data exposed to plugins by :class:`StudioAPI`.

    The application supplies the concrete document implementation. Plugins
    only depend on this structural contract and can therefore use the SDK
    without importing the application package.
    """

    path: Path
    kind: Literal["folder", "json", "archive"]
    data: dict[str, Any]
    modified: bool
    plugin_issues: list[str]
    read_only: bool

    @property
    def location(self) -> Path:
        """Filesystem location represented by the document."""
        ...

    @property
    def degraded(self) -> bool:
        """Whether loading the document reported plugin issues."""
        ...

    @property
    def vehicle(self) -> Any:
        """Domain Vehicle model representation."""
        ...

    def get_plugin_data(self, namespace: str, default: Any = None) -> Any:
        """Retrieve root-level plugin data."""
        ...

    def set_plugin_data(self, namespace: str, value: Any) -> None:
        """Set root-level plugin data."""
        ...

    def remove_plugin_data(self, namespace: str) -> None:
        """Remove root-level plugin data."""
        ...

    def get_component(self, comp_id: str) -> dict[str, Any] | None:
        """Find a component by ID."""
        ...

    def get_typed_component(self, comp_id: str) -> Any:
        """Find a component by ID and return typed domain component."""
        ...

    def get_component_plugin_data(self, comp_id: str, namespace: str, default: Any = None) -> Any:
        """Retrieve component-level plugin data."""
        ...

    def set_component_plugin_data(self, comp_id: str, namespace: str, value: Any) -> None:
        """Set component-level plugin data."""
        ...


__all__ = ["ProjectDocument"]
