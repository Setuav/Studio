"""Control Surface domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.model import Component


class ControlSurfaceModel(Component):
    """Domain model for ControlSurface (Flap / Aileron / Elevator / Rudder)."""

    def _surface_profiles(self) -> list[dict[str, Any]] | None:
        """The profile stations of the lifting surface the control surface is cut from."""
        target = self._attach_target_model
        profiles = getattr(target, "profiles", None) if target is not None else None
        return profiles if isinstance(profiles, list) and len(profiles) >= 2 else None

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

    def _metrics(self) -> dict[str, float]:
        """Area and area ratio on the lifting surface; raises without one."""
        from ..engine.control_surface_geometry import compute_control_surface_metrics

        profiles = self._surface_profiles()
        if profiles is None:
            raise ValueError(f"Control surface {self.id} is not attached to a lifting surface")
        return compute_control_surface_metrics(dict(self.geometry), profiles)

    @property
    def area(self) -> float:
        """Area of one side in dm²."""
        return float(self._metrics()["area_dm2"])

    @property
    def area_ratio(self) -> float:
        """Area as a percentage of one side of the lifting surface."""
        return float(self._metrics()["area_ratio"])

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update(
            {
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
        if self._surface_profiles() is not None:
            metrics = self._metrics()
            props["area"] = float(metrics["area_dm2"])
            props["area_ratio"] = float(metrics["area_ratio"])
        return props
