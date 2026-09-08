"""Universal minimal State model for flight and operational dynamics."""

from __future__ import annotations

from typing import Any

from setuav_studio.model.data import Data
from setuav_studio.model.environment import Environment


class State(Data):
    """Core minimal State: Universal extensible container for dynamic operational states."""

    def __init__(
        self,
        id: str = "",
        name: str = "State",
        time_s: float = 0.0,
        environment: Environment | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self["id"] = id
        self["name"] = name
        self["time_s"] = float(time_s)
        self["environment"] = environment if environment is not None else Environment()

    @property
    def id(self) -> str:
        return str(self.get("id", ""))

    @id.setter
    def id(self, value: str) -> None:
        self["id"] = str(value)

    @property
    def name(self) -> str:
        return str(self.get("name", "State"))

    @name.setter
    def name(self, value: str) -> None:
        self["name"] = str(value)

    @property
    def time_s(self) -> float:
        return float(self.get("time_s", 0.0))

    @time_s.setter
    def time_s(self, value: float) -> None:
        self["time_s"] = float(value)

    @property
    def environment(self) -> Environment:
        env_val = self.get("environment")
        if isinstance(env_val, Environment):
            return env_val
        if isinstance(env_val, dict):
            env = Environment.from_dict(env_val)
            self["environment"] = env
            return env
        default_env = Environment()
        self["environment"] = default_env
        return default_env

    @environment.setter
    def environment(self, value: Environment) -> None:
        self["environment"] = value

    def to_dict(self) -> dict[str, Any]:
        """Convert state to a standard JSON-serializable dictionary."""
        d = super().to_dict()
        if isinstance(self.get("environment"), Environment):
            d["environment"] = self.environment.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> State:
        """Create a State instance from a dictionary."""
        instance = cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "State")),
            time_s=float(data.get("time_s", 0.0)),
        )
        for k, v in data.items():
            if k == "environment" and isinstance(v, dict):
                instance.environment = Environment.from_dict(v)
            else:
                instance[k] = Data._wrap(v)
        return instance


__all__ = ["State"]
