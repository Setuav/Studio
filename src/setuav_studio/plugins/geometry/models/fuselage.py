"""Fuselage domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.component_model import BaseComponentModel


class FuselageSectionModel:
    """Domain model for a single Fuselage cross-section."""

    def __init__(self, data: dict[str, Any], index: int = 0) -> None:
        self._data = data
        self._index = index

    @property
    def position(self) -> dict[str, float]:
        return self._data.setdefault("position", {})

    @property
    def x(self) -> float:
        return float(self.position.get("x", 0.0))

    @property
    def y(self) -> float:
        return float(self.position.get("y", 0.0))

    @property
    def z(self) -> float:
        return float(self.position.get("z", 0.0))

    @property
    def profile(self) -> dict[str, Any]:
        return self._data.setdefault("profile", {})

    @property
    def width(self) -> float:
        return float(self.profile.get("width", 0.0))

    @property
    def height(self) -> float:
        return float(self.profile.get("height", 0.0))

    @property
    def shape(self) -> str:
        return str(self.profile.get("type", "circle"))

    def get_exposed_properties(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "width": self.width,
            "height": self.height,
            "shape": self.shape,
        }

    def __getattr__(self, name: str) -> Any:
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"'FuselageSectionModel' object has no attribute '{name}'")


class FuselageModel(BaseComponentModel):
    """Domain model for Fuselage with live length, dimensions, and shape metrics."""

    @property
    def geometry(self) -> dict[str, Any]:
        return self.parameters.setdefault("geometry", {})

    @property
    def segments(self) -> list[dict[str, Any]]:
        return self.geometry.get("segments") or []

    @property
    def sections(self) -> list[FuselageSectionModel]:
        """List of typed domain models for each fuselage section."""
        segments = self.segments
        if not segments:
            return []
        seg = segments[0] if isinstance(segments[0], dict) else {}
        sections = seg.get("sections", [])
        if isinstance(sections, list):
            return [
                FuselageSectionModel(s, i) for i, s in enumerate(sections) if isinstance(s, dict)
            ]
        return []

    @property
    def nose_section(self) -> FuselageSectionModel | None:
        secs = self.sections
        return secs[0] if secs else None

    @property
    def tail_section(self) -> FuselageSectionModel | None:
        secs = self.sections
        return secs[-1] if secs else None

    @property
    def length(self) -> float:
        secs = self.sections
        if secs:
            x_coords = [s.x for s in secs]
            return float(max(x_coords) - min(x_coords))
        return float(self.parameters.get("length", 0.0))

    @property
    def max_width(self) -> float:
        secs = self.sections
        if secs:
            widths = [s.width for s in secs]
            return float(max(widths))
        return float(self.parameters.get("width", 0.0))

    @property
    def width(self) -> float:
        return self.max_width

    @property
    def max_height(self) -> float:
        secs = self.sections
        if secs:
            heights = [s.height for s in secs]
            return float(max(heights))
        return float(self.parameters.get("height", 0.0))

    @property
    def height(self) -> float:
        return self.max_height

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update(
            {
                "length": self.length,
                "width": self.width,
                "height": self.height,
                "max_width": self.max_width,
                "max_height": self.max_height,
            }
        )
        for i, sec in enumerate(self.sections):
            for sp_k, sp_v in sec.get_exposed_properties().items():
                props[f"section_{i}_{sp_k}"] = sp_v
        return props

    def __getattr__(self, name: str) -> Any:
        # Dynamic section access: section_0, section_1, etc.
        if name.startswith("section_"):
            try:
                idx = int(name.split("_", 1)[1])
                secs = self.sections
                if 0 <= idx < len(secs):
                    return secs[idx]
            except ValueError:
                pass
        return super().__getattr__(name)
