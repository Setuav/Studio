"""Fuselage domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.model import Component

from ..engine.fuselage_geometry import compute_section_metrics, sample_profile


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
        """Width of the profile outline in mm; raises ``ValueError`` for an invalid profile."""
        return compute_section_metrics(sample_profile(self.profile))["width"]

    @property
    def height(self) -> float:
        """Height of the profile outline in mm; raises ``ValueError`` for an invalid profile."""
        return compute_section_metrics(sample_profile(self.profile))["height"]

    @property
    def shape(self) -> str:
        return str(self.profile.get("type", "circle"))

    def get_exposed_properties(self) -> dict[str, Any]:
        props: dict[str, Any] = {"x": self.x, "y": self.y, "z": self.z, "shape": self.shape}
        # An invalid profile has no outline: formulas that use its size get an error.
        try:
            metrics = compute_section_metrics(sample_profile(self.profile))
        except ValueError:
            return props
        props["width"] = metrics["width"]
        props["height"] = metrics["height"]
        return props

    def __getattr__(self, name: str) -> Any:
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"'FuselageSectionModel' object has no attribute '{name}'")


class FuselageModel(Component):
    """Domain model for Fuselage with live length, dimensions, and shape metrics."""

    @property
    def geometry(self) -> dict[str, Any]:
        return self.parameters.setdefault("geometry", {})

    @property
    def segments(self) -> list[dict[str, Any]]:
        return self.geometry.get("segments") or []

    @property
    def sections(self) -> list[FuselageSectionModel]:
        """List of typed domain models for each fuselage section across all segments."""
        all_sections: list[FuselageSectionModel] = []
        idx = 0
        for seg in self.segments:
            if isinstance(seg, dict):
                secs = seg.get("sections", [])
                if isinstance(secs, list):
                    for s in secs:
                        if isinstance(s, dict):
                            all_sections.append(FuselageSectionModel(s, idx))
                            idx += 1
        return all_sections

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
        props["length"] = self.length
        section_props = [section.get_exposed_properties() for section in self.sections]
        for i, section in enumerate(section_props):
            for sp_k, sp_v in section.items():
                props[f"section_{i}_{sp_k}"] = sp_v
        # The overall size needs every section outline.
        if section_props and all("width" in section for section in section_props):
            props["width"] = props["max_width"] = max(s["width"] for s in section_props)
            props["height"] = props["max_height"] = max(s["height"] for s in section_props)
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
