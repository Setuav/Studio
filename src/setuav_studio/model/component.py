"""Universal Component model for UAV entities."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class Component:
    """Core domain entity model for a UAV component."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._raw_data: dict[str, Any] = data if data is not None else {}
        self._children: dict[str, Any] = {}
        self._child_list: list[Any] = []

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
        val = self._raw_data.get("mass", 0.0)
        try:
            return float(val) if val is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    @mass.setter
    def mass(self, value: float) -> None:
        self._raw_data["mass"] = float(value)

    @property
    def local_cg(self) -> dict[str, float]:
        """Local center of gravity offset in mm relative to component origin."""
        val = self._raw_data.get("local_cg_mm") or self._raw_data.get("local_cg")
        if not isinstance(val, dict):
            ext = self.extensions.get("org.setuav.weight-balance")
            if isinstance(ext, dict) and isinstance(ext.get("local_cg_mm"), dict):
                val = ext["local_cg_mm"]
        if not isinstance(val, dict):
            val = self._raw_data.setdefault("local_cg_mm", {"x": 0.0, "y": 0.0, "z": 0.0})
        return val

    @local_cg.setter
    def local_cg(self, value: dict[str, float]) -> None:
        self._raw_data["local_cg_mm"] = {
            "x": float(value.get("x", 0.0) or 0.0),
            "y": float(value.get("y", 0.0) or 0.0),
            "z": float(value.get("z", 0.0) or 0.0),
        }

    @property
    def inertia(self) -> dict[str, float]:
        """Local inertia tensor moments and products in kg·m²."""
        val = self._raw_data.get("inertia_kg_m2") or self._raw_data.get("inertia")
        if not isinstance(val, dict):
            ext = self.extensions.get("org.setuav.weight-balance")
            if isinstance(ext, dict) and isinstance(ext.get("inertia_kg_m2"), dict):
                val = ext["inertia_kg_m2"]
            elif isinstance(self.parameters.get("inertia"), dict):
                val = self.parameters["inertia"]
        if not isinstance(val, dict):
            val = self._raw_data.setdefault(
                "inertia_kg_m2",
                {"ixx": 0.0, "iyy": 0.0, "izz": 0.0, "ixy": 0.0, "ixz": 0.0, "iyz": 0.0},
            )
        return val

    @inertia.setter
    def inertia(self, value: dict[str, float]) -> None:
        self._raw_data["inertia_kg_m2"] = {
            "ixx": float(value.get("ixx", 0.0) or 0.0),
            "iyy": float(value.get("iyy", 0.0) or 0.0),
            "izz": float(value.get("izz", 0.0) or 0.0),
            "ixy": float(value.get("ixy", 0.0) or 0.0),
            "ixz": float(value.get("ixz", 0.0) or 0.0),
            "iyz": float(value.get("iyz", 0.0) or 0.0),
        }

    @property
    def inertia_tensor(self) -> Any:
        from setuav_studio.model.mass import InertiaTensor

        return InertiaTensor.from_dict(self.inertia)

    @property
    def transform(self) -> dict[str, Any]:
        return self._raw_data.setdefault("transform", {})

    @property
    def envelope(self) -> dict[str, Any]:
        return self._raw_data.setdefault("envelope", {})

    @envelope.setter
    def envelope(self, value: dict[str, Any]) -> None:
        self._raw_data["envelope"] = value

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
        cg = self.local_cg
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
            "cg_x": float(cg.get("x", 0.0) or 0.0),
            "cg_y": float(cg.get("y", 0.0) or 0.0),
            "cg_z": float(cg.get("z", 0.0) or 0.0),
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

    def add_child_model(self, child: Any) -> None:
        """Register a child component model attached to this component."""
        if child not in self._child_list:
            self._child_list.append(child)

        child_id = getattr(child, "id", "")
        if child_id:
            clean_id = child_id.replace("-", "_").lower()
            self._children[clean_id] = child

            parent_clean = self.id.replace("-", "_").lower()
            if clean_id.startswith(f"{parent_clean}_"):
                short_name = clean_id[len(parent_clean) + 1 :]
                if short_name:
                    self._children[short_name] = child
            elif "-" in child_id:
                short_name = child_id.split("-")[-1].replace("-", "_").lower()
                if short_name:
                    self._children[short_name] = child

        raw = getattr(child, "raw_data", {})
        if isinstance(raw, dict):
            geom = raw.get("parameters", {}).get("geometry", {})
            if isinstance(geom, dict):
                tag = str(geom.get("tag") or "").replace("-", "_").lower()
                if tag:
                    self._children[tag] = child
                ctype = str(geom.get("type") or "").replace("-", "_").lower()
                if ctype:
                    self._children[ctype] = child
            c_name = str(raw.get("name") or "").replace("-", "_").replace(" ", "_").lower()
            if c_name:
                self._children[c_name] = child

    @property
    def children(self) -> dict[str, Any]:
        """Dictionary of child component models indexed by identifier / tag."""
        return self._children

    @property
    def child_components(self) -> list[Any]:
        """Ordered list of unique child component models."""
        return list(self._child_list)

    def __getattr__(self, name: str) -> Any:
        name_lower = name.lower()
        if hasattr(self, "_children") and name_lower in self._children:
            return self._children[name_lower]
        if name in self.parameters:
            return self.parameters[name]
        geom = self.parameters.get("geometry")
        if isinstance(geom, dict) and name in geom:
            return geom[name]
        if name in self._raw_data:
            return self._raw_data[name]
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute, child, or parameter '{name}'"
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
