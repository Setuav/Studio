"""Universal Component model for UAV entities."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class Component:
    """Core domain entity model for a UAV component."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._raw_data: dict[str, Any] = data if data is not None else {}

    @property
    def raw_data(self) -> dict[str, Any]:
        """Underlying component dictionary."""
        return self._raw_data

    @property
    def id(self) -> str:
        return str(self._raw_data.get("id", ""))

    @id.setter
    def id(self, value: str) -> None:
        self._raw_data["id"] = value

    @property
    def name(self) -> str:
        return str(self._raw_data.get("name", self.id))

    @name.setter
    def name(self, value: str) -> None:
        self._raw_data["name"] = value

    @property
    def type(self) -> str:
        return str(self._raw_data.get("type", ""))

    @type.setter
    def type(self, value: str) -> None:
        self._raw_data["type"] = value

    @property
    def parent_id(self) -> str | None:
        """ID of the parent component to which this component attaches."""
        val = self._raw_data.get("parent") or self._raw_data.get("attach_to")
        return str(val) if val else None

    @parent_id.setter
    def parent_id(self, value: str | None) -> None:
        self._raw_data["parent"] = value
        self._raw_data["attach_to"] = value

    @property
    def mass(self) -> float:
        val = self._raw_data.get("mass", self.parameters.get("mass", 0.0))
        try:
            return float(val) if val is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    @mass.setter
    def mass(self, value: float) -> None:
        self._raw_data["mass"] = value

    @property
    def transform(self) -> dict[str, Any]:
        return self._raw_data.setdefault("transform", {})

    @property
    def position(self) -> dict[str, float]:
        return self.transform.setdefault("position", {"x": 0.0, "y": 0.0, "z": 0.0})

    @property
    def rotation(self) -> dict[str, float]:
        return self.transform.setdefault("rotation", {"roll": 0.0, "pitch": 0.0, "yaw": 0.0})

    @property
    def x(self) -> float:
        return float(self.position.get("x", 0.0))

    @x.setter
    def x(self, val: float) -> None:
        self.position["x"] = float(val)

    @property
    def y(self) -> float:
        return float(self.position.get("y", 0.0))

    @y.setter
    def y(self, val: float) -> None:
        self.position["y"] = float(val)

    @property
    def z(self) -> float:
        return float(self.position.get("z", 0.0))

    @z.setter
    def z(self, val: float) -> None:
        self.position["z"] = float(val)

    @property
    def roll(self) -> float:
        return float(self.rotation.get("roll", 0.0))

    @property
    def pitch(self) -> float:
        return float(self.rotation.get("pitch", 0.0))

    @property
    def yaw(self) -> float:
        return float(self.rotation.get("yaw", 0.0))

    @property
    def parameters(self) -> dict[str, Any]:
        return self._raw_data.setdefault("parameters", {})

    @property
    def plugins(self) -> dict[str, Any]:
        """Plugin-specific namespaced storage."""
        if "plugins" in self._raw_data and isinstance(self._raw_data["plugins"], dict):
            return self._raw_data["plugins"]
        if "extensions" in self._raw_data and isinstance(self._raw_data["extensions"], dict):
            return self._raw_data["extensions"]
        return self._raw_data.setdefault("plugins", {})

    @property
    def extensions(self) -> dict[str, Any]:
        """Backward compatibility alias for plugins storage."""
        return self.plugins

    def get_exposed_properties(self) -> dict[str, Any]:
        """Return a dictionary of all property names and their current values."""
        props: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "mass": self.mass,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "roll": self.roll,
            "pitch": self.pitch,
            "yaw": self.yaw,
        }
        for k, v in self.parameters.items():
            if isinstance(v, (int, float, str, bool)):
                props[k] = v
        return props

    def to_dict(self) -> dict[str, Any]:
        """Export lossless dictionary representation."""
        return deepcopy(self._raw_data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Component:
        """Instantiate model from dictionary."""
        return cls(data)

    def __getattr__(self, name: str) -> Any:
        if name in self.parameters:
            return self.parameters[name]
        if name in self._raw_data:
            return self._raw_data[name]
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute or parameter '{name}'"
        )

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __repr__(self) -> str:
        return f"<Component id='{self.id}' name='{self.name}' type='{self.type}'>"


class GenericComponent(Component):
    """Fallback component model for types with no specialized domain class."""

    pass


__all__ = [
    "Component",
    "GenericComponent",
]
