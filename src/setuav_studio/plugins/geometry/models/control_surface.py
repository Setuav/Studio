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

    @property
    def span_length(self) -> float:
        return max(self.span_end - self.span_start, 0.0)

    @property
    def eta_start(self) -> float:
        return float(self.geometry.get("eta_start", 0.0))

    @property
    def eta_end(self) -> float:
        return float(self.geometry.get("eta_end", 0.0))

    @property
    def eta_length(self) -> float:
        return max(self.eta_end - self.eta_start, 0.0)

    @property
    def area(self) -> float:
        """Area in dm^2."""
        from setuav_studio.plugins.geometry.editors.control_surface_values import (
            compute_control_surface_metrics,
        )

        metrics = compute_control_surface_metrics(
            self.geometry,
            semi_span=max(self.span_end, 400.0),
            root_chord=max(self.chord / max(self.chord_fraction, 0.01), 150.0),
        )
        return float(metrics.get("area_dm2", 0.0))

    @property
    def area_ratio(self) -> float:
        """Area percentage relative to parent wing."""
        from setuav_studio.plugins.geometry.editors.control_surface_values import (
            compute_control_surface_metrics,
        )

        metrics = compute_control_surface_metrics(
            self.geometry,
            semi_span=max(self.span_end, 400.0),
            root_chord=max(self.chord / max(self.chord_fraction, 0.01), 150.0),
        )
        return float(metrics.get("area_ratio", 0.0))

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update({
            "area": self.area,
            "area_ratio": self.area_ratio,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "span_length": self.span_length,
            "eta_start": self.eta_start,
            "eta_end": self.eta_end,
            "eta_length": self.eta_length,
            "chord": self.chord,
            "chord_fraction": self.chord_fraction,
            "deflection": self.deflection,
            "hinge_sweep": self.hinge_sweep,
        })
        return props
