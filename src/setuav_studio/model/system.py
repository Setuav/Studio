"""Universal Subsystem grouping model for UAV components."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from setuav_studio.model.component import Component
from setuav_studio.model.data import Data


@dataclass
class System:
    """A functional subsystem group of UAV components (e.g., Propulsion, Aerostructure)."""

    id: str
    name: str
    system_type: str = "custom"  # "aerostructure", "propulsion", "avionics", "payload", "custom"
    components: list[Component] = field(default_factory=list)
    parameters: Data = field(default_factory=Data)
    plugins: Data = field(default_factory=Data)

    def add_component(self, component: Component) -> None:
        """Add a component to this subsystem."""
        self.components.append(component)

    def remove_component(self, component_id: str) -> Component | None:
        """Remove and return component by ID."""
        for i, c in enumerate(self.components):
            if c.id == component_id:
                return self.components.pop(i)
        return None

    def get_component(self, component_id: str) -> Component | None:
        """Retrieve component by ID."""
        for c in self.components:
            if c.id == component_id:
                return c
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert system to a serializable dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "system_type": self.system_type,
            "components": [c.to_dict() for c in self.components],
            "parameters": self.parameters.to_dict(),
            "plugins": self.plugins.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> System:
        """Create a System instance from dictionary."""
        raw_components = data.get("components", [])
        components = [Component.from_dict(c) if isinstance(c, dict) else c for c in raw_components]
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "System")),
            system_type=str(data.get("system_type", "custom")),
            components=components,
            parameters=Data.from_dict(data.get("parameters", {})),
            plugins=Data.from_dict(data.get("plugins", {})),
        )


__all__ = ["System"]
