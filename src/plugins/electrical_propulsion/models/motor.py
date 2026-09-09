"""Electric Motor domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.model import Component


class MotorModel(Component):
    """Domain model for Electric Motor."""

    @property
    def kv(self) -> float:
        return float(self.parameters.get("kv", 0.0))

    @property
    def max_power(self) -> float:
        return float(self.parameters.get("max_power", 0.0))

    @property
    def max_thrust(self) -> float:
        return float(self.parameters.get("max_thrust", 0.0))

    @property
    def max_current(self) -> float:
        return float(self.parameters.get("max_current", 0.0))

    @property
    def no_load_current(self) -> float:
        return float(self.parameters.get("no_load_current", 0.0))

    @property
    def resistance(self) -> float:
        return float(self.parameters.get("resistance", 0.0))

    @property
    def mount(self) -> dict[str, Any]:
        """Mount configuration dictionary."""
        mount_dict = self.parameters.setdefault("mount", {})
        if not isinstance(mount_dict, dict):
            mount_dict = {}
            self.parameters["mount"] = mount_dict
        return mount_dict

    @property
    def mount_target_id(self) -> str:
        return str(self.mount.get("target_id", ""))

    @property
    def mount_position(self) -> str:
        return str(self.mount.get("position", "front"))

    @property
    def mount_offset(self) -> dict[str, float]:
        offset = self.mount.setdefault("offset", {"x": 0.0, "y": 0.0, "z": 0.0})
        if not isinstance(offset, dict):
            offset = {"x": 0.0, "y": 0.0, "z": 0.0}
            self.mount["offset"] = offset
        return offset

    @property
    def mount_orientation(self) -> dict[str, float]:
        ori = self.mount.setdefault("orientation", {"roll": 0.0, "pitch": 0.0, "yaw": 0.0})
        if not isinstance(ori, dict):
            ori = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
            self.mount["orientation"] = ori
        return ori

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update(
            {
                "kv": self.kv,
                "max_power": self.max_power,
                "max_thrust": self.max_thrust,
                "max_current": self.max_current,
                "no_load_current": self.no_load_current,
                "resistance": self.resistance,
                "mount": self.mount,
                "mount_target_id": self.mount_target_id,
                "mount_position": self.mount_position,
            }
        )
        return props
