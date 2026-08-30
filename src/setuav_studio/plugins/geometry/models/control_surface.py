"""Control Surface domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.component_model import BaseComponentModel


class ControlSurfaceModel(BaseComponentModel):
    """Domain model for ControlSurface (Flap / Aileron / Elevator / Rudder)."""

    @property
    def geometry(self) -> dict[str, Any]:
        return self.parameters.setdefault("geometry", {})

    @property
    def span_start(self) -> float:
        return float(self.geometry.get("span_start", 0.0))

    @property
    def span_end(self) -> float:
        return float(self.geometry.get("span_end", 0.0))

    @property
    def chord(self) -> float:
        return float(self.geometry.get("chord", 0.0))

    @property
    def chord_fraction(self) -> float:
        return float(self.geometry.get("chord_fraction", 0.0))

    @property
    def deflection(self) -> float:
        return float(self.geometry.get("deflection", 0.0))

    @property
    def hinge_sweep(self) -> float:
        return float(self.geometry.get("hinge_sweep", 0.0))

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update({
            "span_start": self.span_start,
            "span_end": self.span_end,
            "chord": self.chord,
            "chord_fraction": self.chord_fraction,
            "deflection": self.deflection,
            "hinge_sweep": self.hinge_sweep,
        })
        return props
