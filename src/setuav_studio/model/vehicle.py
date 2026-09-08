"""Universal Vehicle model for UAV platforms."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from setuav_studio.model.component import Component
from setuav_studio.model.data import Data
from setuav_studio.model.state import State
from setuav_studio.model.system import System


@dataclass
class Vehicle:
    """Universal Vehicle entity model representing a UAV platform."""

    id: str
    name: str = "Unnamed Vehicle"
    type: str = "org.setuav.core:vehicle"
    systems: list[System] = field(default_factory=list)
    configurations: list[dict[str, Any]] = field(default_factory=list)
    states: list[State] = field(default_factory=list)
    parameters: Data = field(default_factory=Data)
    plugins: Data = field(default_factory=Data)

    def all_components(self) -> list[Component]:
        """Return a flat list of all components across all systems."""
        components: list[Component] = []
        for sys in self.systems:
            components.extend(sys.components)
        return components

    def get_component(self, component_id: str) -> Component | None:
        """Find a component by ID across all systems."""
        for sys in self.systems:
            comp = sys.get_component(component_id)
            if comp is not None:
                return comp
        return None

    def get_system(self, system_id: str) -> System | None:
        """Find a system by ID."""
        for sys in self.systems:
            if sys.id == system_id:
                return sys
        return None

    def get_or_create_system(
        self,
        system_id: str,
        system_type: str = "custom",
        name: str | None = None,
    ) -> System:
        """Retrieve existing system or create and append a new one."""
        existing = self.get_system(system_id)
        if existing is not None:
            return existing
        new_sys = System(
            id=system_id,
            name=name or system_id.replace("_", " ").title(),
            system_type=system_type,
        )
        self.systems.append(new_sys)
        return new_sys

    def get_state(self, state_id: str) -> State | None:
        """Find an operational state by ID."""
        for s in self.states:
            if s.id == state_id:
                return s
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert vehicle model to a complete JSON-serializable dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "systems": [s.to_dict() for s in self.systems],
            "configurations": list(self.configurations),
            "states": [s.to_dict() for s in self.states],
            "parameters": self.parameters.to_dict(),
            "plugins": self.plugins.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Vehicle:
        """Construct a Vehicle model from dictionary data."""
        # 1. Parse Systems & Components
        systems: list[System] = []
        if "systems" in data and isinstance(data["systems"], list):
            systems = [System.from_dict(s) if isinstance(s, dict) else s for s in data["systems"]]
        elif "components" in data and isinstance(data["components"], list):
            # Backward compatibility: wrap flat components list in a default system
            default_sys = System(
                id="main",
                name="Main Components",
                system_type="custom",
                components=[
                    Component.from_dict(c) if isinstance(c, dict) else c for c in data["components"]
                ],
            )
            systems = [default_sys]

        # 2. Parse States
        raw_states = data.get("states", [])
        states = [
            State.from_dict(s) if isinstance(s, dict) else s
            for s in raw_states
            if isinstance(s, (dict, State))
        ]

        # 3. Parse Configurations
        configs = list(data.get("configurations", []))

        # 4. Plugins / Extensions storage
        plugins_data = data.get("plugins") or data.get("extensions") or {}

        return cls(
            id=str(data.get("id", "vehicle")),
            name=str(data.get("name", "Unnamed Vehicle")),
            type=str(data.get("type", "org.setuav.core:vehicle")),
            systems=systems,
            configurations=configs,
            states=states,
            parameters=Data.from_dict(data.get("parameters", {})),
            plugins=Data.from_dict(plugins_data if isinstance(plugins_data, dict) else {}),
        )


__all__ = ["Vehicle"]
