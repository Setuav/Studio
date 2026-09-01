"""Control Surface domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.component_model import BaseComponentModel


class ControlSurfaceModel(BaseComponentModel):
    """Domain model for ControlSurface (Flap / Aileron / Elevator / Rudder)."""

    def __init__(
        self,
        data: dict[str, Any] | None = None,
        parent_model: Any | None = None,
    ) -> None:
        super().__init__(data)
        self._parent_model = parent_model

    def set_parent_model(self, parent_model: Any | None) -> None:
        self._parent_model = parent_model

    def _get_parent_dimensions(self) -> tuple[float, float, float, float | None]:
        """Return (semi_span, root_chord, tip_chord, parent_area_dm2)."""
        if self._parent_model is not None:
            pm = self._parent_model
            root_sec = getattr(pm, "root_section", None)
            tip_sec = getattr(pm, "tip_section", None)
            root_chord = float(root_sec.chord) if root_sec is not None else 150.0
            tip_chord = float(tip_sec.chord) if tip_sec is not None else root_chord
            span = float(getattr(pm, "span", 800.0))
            is_mirror = bool(getattr(pm, "mirror", False))
            semi_span = span / 2.0 if is_mirror else span
            area = getattr(pm, "area", None)
            parent_area = float(area) if area is not None else None
            return max(semi_span, 1.0), max(root_chord, 1.0), max(tip_chord, 1.0), parent_area

        semi_span = max(self.span_end, 400.0)
        root_chord = max(self.chord / max(self.chord_fraction, 0.01), 150.0)
        return semi_span, root_chord, root_chord, None

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
        from plugins.geometry.editors.control_surface_values import (
            compute_control_surface_metrics,
        )

        semi_span, root_chord, tip_chord, parent_area = self._get_parent_dimensions()
        metrics = compute_control_surface_metrics(
            self.geometry,
            semi_span=semi_span,
            root_chord=root_chord,
            tip_chord=tip_chord,
            parent_wing_area=parent_area,
        )
        return float(metrics.get("area_dm2", 0.0))

    @property
    def area_ratio(self) -> float:
        """Area percentage relative to parent wing."""
        from plugins.geometry.editors.control_surface_values import (
            compute_control_surface_metrics,
        )

        semi_span, root_chord, tip_chord, parent_area = self._get_parent_dimensions()
        metrics = compute_control_surface_metrics(
            self.geometry,
            semi_span=semi_span,
            root_chord=root_chord,
            tip_chord=tip_chord,
            parent_wing_area=parent_area,
        )
        return float(metrics.get("area_ratio", 0.0))

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update(
            {
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
            }
        )
        return props
