"""Universal Component domain model for UAV entities and plugin components."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from setuav_studio.api.contributions import ParameterField


class Component:
    """Core domain entity model for a UAV component."""

    COMPONENT_TYPE: str = ""

    def __init__(
        self,
        data: dict[str, Any] | None = None,
        *,
        id: str = "",
        name: str = "",
        type: str = "",
        mass: float = 0.0,
        parent: str | None = None,
        **kwargs: Any,
    ) -> None:
        if (
            data is not None
            and "parameters" not in data
            and "kind" not in data
            and "id" not in data
        ):
            self._raw_data: dict[str, Any] = {"parameters": dict(data)}
        else:
            self._raw_data = data if data is not None else {}

        self._raw_data.setdefault("kind", "component")
        self._raw_data.setdefault(
            "transform",
            {
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            },
        )
        self._raw_data.setdefault("parameters", {})
        self._children: dict[str, Any] = {}
        self._child_list: list[Any] = []

        # 1. Class-level component type default
        class_type = getattr(self.__class__, "COMPONENT_TYPE", "")
        if class_type and not self._raw_data.get("type"):
            self._raw_data["type"] = class_type

        # 2. Populate parameter defaults from class field descriptors
        fields = self.get_fields()
        params = self._raw_data.setdefault("parameters", {})
        for f in fields:
            if f.key and f.key not in params:
                params[f.key] = f.default

        if id:
            self.id = id
        if name:
            self.name = name
        if type:
            self.type = type
        if mass:
            self.mass = mass
        if parent:
            self.parent_id = parent

        for k, v in kwargs.items():
            if hasattr(self.__class__, k):
                setattr(self, k, v)
            else:
                self.parameters[k] = v

    @classmethod
    def get_fields(cls) -> tuple[ParameterField, ...]:
        """Return all ParameterField descriptors defined on this component class."""
        from setuav_studio.api.contributions import ParameterField

        fields: list[ParameterField] = []
        for base in reversed(cls.__mro__):
            for v in base.__dict__.values():
                if isinstance(v, ParameterField) and v not in fields:
                    fields.append(v)
        return tuple(fields)

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
    def component_type(self) -> str:
        return str(self._raw_data.get("type", ""))

    @component_type.setter
    def component_type(self, value: str) -> None:
        self._raw_data["type"] = value

    # Compatibility property for comp.type
    @property
    def type(self) -> str:
        return str(self._raw_data.get("type") or getattr(self.__class__, "COMPONENT_TYPE", ""))

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

    def reparent(
        self,
        new_parent_id: str | None,
        comps_or_project: Any = None,
        *,
        preserve_world_transform: bool = True,
    ) -> None:
        """Reparent this component, preserving its world coordinates and visual position."""
        from setuav_studio.utilities.transform import reparent_component

        reparent_component(
            self._raw_data,
            new_parent_id,
            comps_or_project,
            preserve_world_transform=preserve_world_transform,
        )

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
            ext = self.extensions.get("org.setuav.weight-balance", {})
            if isinstance(ext, dict):
                val = ext.get("local_cg_mm") or ext.get("local_cg")
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
            ext = self.extensions.get("org.setuav.weight-balance", {})
            if isinstance(ext, dict):
                val = ext.get("inertia_kg_m2") or ext.get("inertia")
        if not isinstance(val, dict) and isinstance(self.parameters.get("inertia"), dict):
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
        from setuav_studio.model.scope import to_dot_dict

        tf = self._raw_data.get("transform")
        if not isinstance(tf, dict) or not hasattr(tf, "__getattr__"):
            tf = to_dot_dict(tf if isinstance(tf, dict) else {})
            self._raw_data["transform"] = tf
        return cast(dict[str, Any], tf)

    @property
    def envelope(self) -> dict[str, Any]:
        return self._raw_data.setdefault("envelope", {})

    @envelope.setter
    def envelope(self, value: dict[str, Any]) -> None:
        self._raw_data["envelope"] = value

    @property
    def position(self) -> dict[str, float]:
        from setuav_studio.model.scope import to_dot_dict

        pos = self.transform.get("position")
        if not isinstance(pos, dict) or not hasattr(pos, "__getattr__"):
            pos = to_dot_dict(pos if isinstance(pos, dict) else {"x": 0.0, "y": 0.0, "z": 0.0})
            self.transform["position"] = pos
        return cast(dict[str, float], pos)

    @property
    def rotation(self) -> dict[str, float]:
        from setuav_studio.model.scope import to_dot_dict

        rot = self.transform.get("rotation")
        if not isinstance(rot, dict) or not hasattr(rot, "__getattr__"):
            rot = to_dot_dict(
                rot if isinstance(rot, dict) else {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
            )
            self.transform["rotation"] = rot
        return cast(dict[str, float], rot)

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
        from setuav_studio.model.scope import to_dot_dict

        p = self._raw_data.get("parameters")
        if not isinstance(p, dict) or not hasattr(p, "__getattr__"):
            p = to_dot_dict(p if isinstance(p, dict) else {})
            self._raw_data["parameters"] = p
        return cast(dict[str, Any], p)

    @property
    def extensions(self) -> dict[str, Any]:
        """Extension namespaced data storage for plugin contributions."""
        if "extensions" in self._raw_data and isinstance(self._raw_data["extensions"], dict):
            return self._raw_data["extensions"]
        if "plugins" in self._raw_data and isinstance(self._raw_data["plugins"], dict):
            return self._raw_data["plugins"]
        return self._raw_data.setdefault("extensions", {})

    @property
    def plugins(self) -> dict[str, Any]:
        """Backward compatibility alias for extensions storage."""
        return self.extensions

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
            ctype = str(raw.get("type") or "").replace("-", "_").lower()
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

    def get_parameter(self, key: str, default: Any = None) -> Any:
        """Retrieve a parameter value by key, returning default if absent."""
        return self.parameters.get(key, default)

    def set_parameter(self, key: str, value: Any) -> None:
        """Set a parameter value by key."""
        self.parameters[key] = value

    @property
    def sections(self) -> list[Any]:
        """List of station profile dictionaries/models."""
        from setuav_studio.model.scope import to_dot_dict

        profs = (
            self.parameters.get("geometry", {}).get("profiles")
            or self.parameters.get("profiles")
            or []
        )
        return [to_dot_dict(x) for x in profs] if isinstance(profs, list) else []

    def __getattr__(self, name: str) -> Any:
        if name in self.parameters:
            return self.parameters[name]
        geom = self.parameters.get("geometry")
        if isinstance(geom, dict) and name in geom:
            return geom[name]
        name_lower = name.lower()
        if hasattr(self, "_children") and name_lower in self._children:
            return self._children[name_lower]
        if name.startswith("section_") or name.startswith("profile_"):
            try:
                idx = int(name.split("_")[-1])
                secs = self.sections
                if 0 <= idx < len(secs):
                    return secs[idx]
            except (ValueError, IndexError):
                pass
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute or parameter '{name}'"
        )

    def __repr__(self) -> str:
        return f"<Component id='{self.id}' name='{self.name}' type='{self.type}'>"


class GenericComponent(Component):
    """Fallback component model for types with no specialized domain class."""

    pass


__all__ = [
    "Component",
    "GenericComponent",
]
