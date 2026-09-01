"""Universal dynamic hierarchical container (Data) supporting dot and dict access."""

from __future__ import annotations

import copy
from typing import Any


class Data(dict[str, Any]):
    """Universal dynamic hierarchical container supporting both attribute (dot) and dictionary access."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        for k, v in dict(*args, **kwargs).items():
            self[k] = self._wrap(v)

    @classmethod
    def _wrap(cls, value: Any) -> Any:
        if isinstance(value, dict) and not isinstance(value, Data):
            return Data(value)
        if isinstance(value, list):
            return [cls._wrap(v) for v in value]
        return value

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{name}'"
            ) from None

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self[name] = self._wrap(value)

    def __delattr__(self, name: str) -> None:
        try:
            del self[name]
        except KeyError:
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{name}'"
            ) from None

    def to_dict(self) -> dict[str, Any]:
        """Convert container to a pure, deeply copied Python dictionary."""
        result: dict[str, Any] = {}
        for k, v in self.items():
            if isinstance(v, Data):
                result[k] = v.to_dict()
            elif isinstance(v, list):
                result[k] = [
                    item.to_dict() if isinstance(item, Data) else copy.deepcopy(item) for item in v
                ]
            else:
                result[k] = copy.deepcopy(v)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Data:
        """Create a Data container from a dictionary."""
        return cls(data)


__all__ = ["Data"]
