"""Fuselage domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.component_model import BaseComponentModel


class FuselageModel(BaseComponentModel):
    """Domain model for Fuselage with live length, dimensions, and shape metrics."""

    @property
    def geometry(self) -> dict[str, Any]:
        return self.parameters.setdefault("geometry", {})

    @property
    def segments(self) -> list[dict[str, Any]]:
        return self.geometry.get("segments") or []

    @property
    def length(self) -> float:
        segments = self.segments
        if not segments:
            return float(self.parameters.get("length", 0.0))
        seg = segments[0] if isinstance(segments[0], dict) else {}
        sections = seg.get("sections", [])
        if isinstance(sections, list) and sections:
            x_coords = [
                float(s.get("position", {}).get("x", 0.0))
                for s in sections
                if isinstance(s, dict)
            ]
            if x_coords:
                return float(max(x_coords) - min(x_coords))
        return float(self.parameters.get("length", 0.0))

    @property
    def max_width(self) -> float:
        segments = self.segments
        if not segments:
            return float(self.parameters.get("width", 0.0))
        seg = segments[0] if isinstance(segments[0], dict) else {}
        sections = seg.get("sections", [])
        if isinstance(sections, list) and sections:
            widths = [
                float(s.get("profile", {}).get("width", 0.0))
                for s in sections
                if isinstance(s, dict)
            ]
            if widths:
                return float(max(widths))
        return float(self.parameters.get("width", 0.0))

    @property
    def width(self) -> float:
        return self.max_width

    @property
    def max_height(self) -> float:
        segments = self.segments
        if not segments:
            return float(self.parameters.get("height", 0.0))
        seg = segments[0] if isinstance(segments[0], dict) else {}
        sections = seg.get("sections", [])
        if isinstance(sections, list) and sections:
            heights = [
                float(s.get("profile", {}).get("height", 0.0))
                for s in sections
                if isinstance(s, dict)
            ]
            if heights:
                return float(max(heights))
        return float(self.parameters.get("height", 0.0))

    @property
    def height(self) -> float:
        return self.max_height

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update({
            "length": self.length,
            "width": self.width,
            "height": self.height,
            "max_width": self.max_width,
            "max_height": self.max_height,
        })
        return props
